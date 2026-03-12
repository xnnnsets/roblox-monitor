import os
import re
import time
import json
import subprocess
from datetime import datetime, timedelta
import requests
import sys

# Load Config
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    print("Error: config.json tidak ditemukan!")
    sys.exit(1)

INTERVAL = config.get("check_interval", 10)
WEBHOOK = config.get("discord_webhook", "")
CODE = config.get("server_code", "")
CONFIG_PACKAGE = config.get("package", "")
AFK_TIMEOUT_MIN = float(config.get("afk_timeout_minutes", 20))
LOG_SCAN_LINES = int(config.get("log_scan_lines", 4000))

# ANSI color codes
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
RESET = "\033[0m"

def send_discord(msg):
    if WEBHOOK:
        try: requests.post(WEBHOOK, json={"content": msg}, timeout=5)
        except: pass

def check_root_permission():
    try:
        result = subprocess.run(["su", "-c", "id"], capture_output=True, text=True, timeout=5)
        return "uid=0(root)" in result.stdout
    except:
        return False

def find_roblox_packages():
    """Auto-detect all installed Roblox packages via pm list packages."""
    result = os.popen('pm list packages 2>/dev/null | grep -i roblox').read().strip()
    packages = []
    for line in result.splitlines():
        pkg = line.replace("package:", "").strip()
        if pkg:
            packages.append(pkg)
    if packages:
        return packages
    # Fallback to config or default
    return [CONFIG_PACKAGE or "com.roblox.client"]

def get_activity_name(package):
    """Detect main activity name for a package, with fallbacks."""
    # Try to get from pm dump
    cmd = f"su -c \"pm dump {package} 2>/dev/null | grep -E 'android.intent.action.MAIN|android.intent.category.LAUNCHER' -A1 | grep 'cmp=' | head -1\""
    result = os.popen(cmd).read().strip()
    
    # Parse: cmp=com.pkg/com.pkg.Activity
    if "cmp=" in result:
        try:
            cmp_value = result.split("cmp=")[1].split()[0]
            if "/" in cmp_value:
                return cmp_value.split("/")[1]
        except:
            pass
    
    # Fallback: try common activity names in order
    common_activities = [
        f"{package}.ActivityNativeMain",
        f"{package}.RobloxActivity",
        f"{package}.MainActivity",
        "com.roblox.client.ActivityNativeMain",
        "com.roblox.client.RobloxActivity",
        "com.roblox.client.MainActivity",
    ]
    
    for activity in common_activities:
        # Test if activity might exist by checking if package name matches
        if activity.startswith(package):
            return activity
    
    # Default fallback
    return f"{package}.ActivityNativeMain"

def get_roblox_username(package):
    """Scan all app data files then logcat for the Roblox username."""
    # Method 1: search all JSON/XML files in app data directory
    raw = os.popen(
        f'su -c "find /data/data/{package} -type f \\( -name \'*.json\' -o -name \'*.xml\' \\) 2>/dev/null'
        f' | xargs grep -hi \'username\' 2>/dev/null | head -30"'
    ).read()
    for pattern in [
        r'"[Uu]ser[Nn]ame"\s*:\s*"([A-Za-z0-9_]{3,20})"',
        r'name="[Uu]ser[Nn]ame"[^>]*>([A-Za-z0-9_]{3,20})<',
        r'[Uu]ser[Nn]ame["\s]*[:=>]+["\s]*([A-Za-z0-9_]{3,20})',
    ]:
        m = re.search(pattern, raw)
        if m and m.group(1).lower() not in ('null', 'true', 'false', 'string'):
            return m.group(1)
    # Method 2: logcat — Roblox logs username on login
    logcat = os.popen(
        f'su -c "logcat -d -t 500 2>/dev/null | grep -Ei \'username|playername\' | tail -20"'
    ).read()
    for pattern in [
        r'"[Uu]ser[Nn]ame"\s*[=:]\s*"([A-Za-z0-9_]{3,20})"',
        r'[Uu]ser[Nn]ame["\s=:]+([A-Za-z0-9_]{3,20})',
    ]:
        m = re.search(pattern, logcat)
        if m and m.group(1).lower() not in ('null', 'true', 'false', 'string'):
            return m.group(1)
    return "unknown"

def get_memory_info():
    """Return (total_mb, free_mb, free_percent) from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            data = f.read()
        total_match = re.search(r'MemTotal:\s+(\d+)', data)
        free_match  = re.search(r'MemAvailable:\s+(\d+)', data)
        if not total_match or not free_match:
            return 0, 0, 0
        total = int(total_match.group(1)) // 1024
        free  = int(free_match.group(1)) // 1024
        pct   = int(free / total * 100) if total else 0
        return total, free, pct
    except Exception:
        return 0, 0, 0

def read_recent_roblox_logs():
    """Return recent Roblox-focused logcat lines so disconnect logs are not buried by system noise."""
    cmd = (
        f"su -c \"logcat -d -t {LOG_SCAN_LINES} 2>/dev/null"
        f" | grep -Ei 'Roblox  :|rbx\\.|com\\.roblox\\.client'"
        f" | tail -250\""
    )
    return os.popen(cmd).read()


def check_game_status():
    """Check Roblox-specific disconnect patterns from recent logcat output."""
    logs = read_recent_roblox_logs()
    if not logs.strip():
        return False, None

    patterns = [
        (r"Sending disconnect with reason:\s*277", "Disconnect reason 277"),
        (r"Sending disconnect with reason:\s*26[0-9]", "AFK disconnect"),
        (r"Lost connection with reason\s*:\s*Lost connection to the game server", "Lost connection to game server"),
        (r"\[FLog::Network\]\s+Connection lost", "Connection lost"),
        (r"ID_CONNECTION_LOST", "ID_CONNECTION_LOST"),
        (r"AckTimeout", "AckTimeout"),
        (r"SignalRCoreError.*Disconnected", "SignalR disconnected"),
        (r"Session Transition FSM:\s*Error Occurred", "Session transition error"),
    ]

    for pattern, reason in patterns:
        if re.search(pattern, logs, re.IGNORECASE):
            return True, reason

    return False, None

def is_package_running(package):
    pid = os.popen(f'su -c "pidof {package}" 2>/dev/null').read().strip()
    return pid, bool(pid)

def get_last_roblox_log_time(package):
    """Return timestamp of last Roblox log output, or None if no recent logs."""
    # Get recent Roblox logs with timestamp
    cmd = (
        f"su -c \"logcat -d -t {LOG_SCAN_LINES} 2>/dev/null"
        f" | grep -Ei 'Roblox  :|rbx\\.|{package}'"
        f" | tail -20\""
    )
    logs = os.popen(cmd).read().strip().split('\n')
    if not logs or not logs[0]:
        return None
    # Extract timestamp dari baris terakhir (format: MM-DD HH:MM:SS.mmm)
    last_line = logs[-1]
    match = re.search(r'(\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})', last_line)
    if match:
        time_str = match.group(1)
        try:
            return datetime.strptime(time_str, "%m-%d %H:%M:%S")
        except:
            return None
    return None

def check_afk_timeout(package, join_time, last_activity_time):
    """
    Deteksi AFK freeze: 
    - Process running tapi tidak ada log activity > AFK_TIMEOUT_MIN
    - Berarti game freezed/idle terlalu lama
    """
    pid, is_running = is_package_running(package)
    if not is_running:
        return False, None, last_activity_time
    
    # Update last activity time jika ada log baru
    last_log = get_last_roblox_log_time(package)
    if last_log and (not last_activity_time or last_log > last_activity_time):
        last_activity_time = last_log
    
    # Jika tidak ada activity record, anggap sekarang
    if not last_activity_time:
        last_activity_time = datetime.now()
    
    time_since_activity = datetime.now() - last_activity_time
    timeout_delta = timedelta(minutes=AFK_TIMEOUT_MIN)
    
    if time_since_activity > timeout_delta:
        return True, f"AFK {int(time_since_activity.total_seconds() / 60)} min", last_activity_time
    
    return False, None, last_activity_time

def kill_roblox(package):
    print(f"[!] Killing {package} & Cleaning Logs...")
    os.system(f'su -c "am force-stop {package}"')
    os.system('su -c "logcat -c"')

def join_server(package, activity_name):
    link = f"roblox://navigation/share_links?code={CODE}&type=Server"
    print(f"[+] Deep Link: {link}")
    print(f"[+] Package: {package}")
    
    launched = False
    
    # Try explicit activity names (AVOID implicit intent yang trigger chooser dialog)
    activities_to_try = [activity_name]
    for act in [
        f"{package}.ActivityNativeMain",
        f"{package}.RobloxActivity",
        f"{package}.MainActivity",
        "com.roblox.client.ActivityNativeMain",
    ]:
        if act not in activities_to_try:
            activities_to_try.append(act)
    
    for activity in activities_to_try:
        # IMPORTANT: Wrap link dalam single quote agar URL tidak corrupt
        cmd = f"su -c \"am start -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'\""
        print(f"[*] Trying: {activity}")
        print(f"    CMD: {cmd}")
        result = os.popen(cmd).read()
        print(f"    RESULT: {result[:100]}")
        
        if "Error" not in result and "error" not in result:
            print(f"[✓] SUCCESS via {activity}")
            launched = True
            break
        else:
            print(f"[✗] Failed")
    
    if not launched:
        print("[!] All activities failed, trying implicit as last resort...")
        cmd = f'su -c "am start -a android.intent.action.VIEW -d \'{link}\'"'
        print(f"    CMD: {cmd}")
        os.system(cmd)
    
    print("[*] Menunggu game loading untuk auto-tap...")
    time.sleep(20)
    print("[+] Melakukan Auto-Tap agar tidak idle...")
    os.system('su -c "input tap 500 1000"')
    time.sleep(2)
    os.system('su -c "input tap 500 1000"')

def display_dashboard(packages_info, memory_info, check_count):
    """Render a bordered table: PACKAGE (username) | STATUS, plus a memory row."""
    total, free, pct = memory_info
    col1 = 42
    col2 = 18
    sep  = f"+{'-' * col1}+{'-' * col2}+"

    os.system('clear')
    print(sep)
    header_pkg = f" {'PACKAGE':<{col1 - 2}} "
    header_st  = f" {'STATUS':<{col2 - 2}} "
    print(f"|{CYAN}{header_pkg}{RESET}|{CYAN}{header_st}{RESET}|")
    print(sep)

    for pkg, username, running in packages_info:
        label       = f"{pkg} ({username})"
        status_text = "Online" if running else "Offline"
        status_col  = GREEN if running else RED
        # Build padded fields (colour codes are zero-width for alignment purposes)
        pkg_field = f" {label:<{col1 - 2}} "
        st_field  = f" {status_text:<{col2 - 2}} "
        print(f"|{pkg_field}|{status_col}{st_field}{RESET}|")

    # Memory row
    print(sep)
    mem_label  = " System Memory"
    n          = len(packages_info)
    mem_status = f"Checking [{check_count}/{n}] Free: {free}MB ({pct}%)"
    print(f"|{CYAN}{mem_label:<{col1}}{RESET}| {mem_status:<{col2 - 2}} |")
    print(sep)

def monitor():
    os.system('clear')
    print("==========================================")
    print("   ROBLOX LOG-HUNTER (STABLE ROOT)")
    print("==========================================")

    if not check_root_permission():
        print("\n[!!!] ERROR: PYTHON GAGAL MENGAKSES ROOT [!!!]")
        print("Cek kembali izin Termux di aplikasi Superuser lu.")
        sys.exit(1)

    print("[v] Mendeteksi paket Roblox yang terinstall...")
    packages = find_roblox_packages()
    print(f"[v] Ditemukan {len(packages)} paket: {', '.join(packages)}")

    # Get activity names for each package
    print("[v] Mendeteksi activity names...")
    activity_map = {}
    for pkg in packages:
        activity_map[pkg] = get_activity_name(pkg)
        print(f"    {pkg} -> {activity_map[pkg]}")

    print("[v] Membaca username Roblox...")
    usernames = {}
    for pkg in packages:
        usernames[pkg] = get_roblox_username(pkg)
        print(f"    {pkg} -> {usernames[pkg]}")

    # Ask user: monitor all or select one
    target_packages = packages
    if len(packages) > 1:
        print("\n" + "="*50)
        print("Pilihan Monitor:")
        print("1. Monitor SEMUA Roblox apps")
        for i, pkg in enumerate(packages, start=2):
            print(f"{i}. Monitor hanya {pkg} ({usernames[pkg]})")
        print("="*50)
        choice = input("Pilih nomor (default 1): ").strip() or "1"
        try:
            choice_idx = int(choice) - 1
            if choice_idx == 0:
                target_packages = packages
                print(f"✓ Monitor SEMUA ({len(packages)} apps)")
            elif 0 < choice_idx < len(packages) + 1:
                target_packages = [packages[choice_idx - 1]]
                print(f"✓ Monitor hanya: {target_packages[0]} ({usernames[target_packages[0]]})")
            else:
                print("❌ Pilihan invalid, default ke monitor semua.")
                target_packages = packages
        except ValueError:
            print("❌ Input invalid, default ke monitor semua.")
            target_packages = packages

    print("[v] Menghapus log lama...")
    os.system('su -c "logcat -c"')
    time.sleep(1)

    # Track join time dan last activity time per package
    pkg_state = {pkg: {'join_time': datetime.now(), 'last_activity': datetime.now()} for pkg in target_packages}
    check_count = 0
    while True:
        check_count = (check_count % len(target_packages)) + 1
        is_error, reason = check_game_status()

        packages_info = []
        for pkg in target_packages:
            pid, running = is_package_running(pkg)
            packages_info.append((pkg, usernames[pkg], running))

        memory_info = get_memory_info()
        display_dashboard(packages_info, memory_info, check_count)

        # Handle crashed (not running) packages first
        crashed = set()
        for pkg, username, running in packages_info:
            if not running:
                crashed.add(pkg)
                print(f"\n[{time.strftime('%H:%M:%S')}] ❌ {pkg} Crash/Mati")
                send_discord(f"❌ {pkg} Crash! Membuka ulang...")
                kill_roblox(pkg)
                join_server(pkg, activity_map[pkg])
                pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                usernames[pkg] = get_roblox_username(pkg)

        # Check AFK timeout (game freezed, no activity)
        for pkg, username, running in packages_info:
            if running and pkg not in crashed:
                is_afk, afk_reason, last_activity = check_afk_timeout(
                    pkg,
                    pkg_state[pkg]['join_time'],
                    pkg_state[pkg]['last_activity'],
                )
                pkg_state[pkg]['last_activity'] = last_activity
                if is_afk:
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⏱️  AFK Detected: {afk_reason} [{pkg}]")
                    send_discord(f"⏱️ {pkg} AFK/Freezed! {afk_reason}. Reconnecting...")
                    kill_roblox(pkg)
                    join_server(pkg, activity_map[pkg])
                    pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                    usernames[pkg] = get_roblox_username(pkg)
                    break

        # Handle global disconnect / error detected in logcat (reconnect one package)
        if is_error:
            for pkg, username, running in packages_info:
                if running and pkg not in crashed:
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⚠️  Error: {reason} [{pkg}]")
                    send_discord(f"⚠️ {pkg} Terputus! Alasan: {reason}. Rejoining...")
                    kill_roblox(pkg)
                    join_server(pkg, activity_map[pkg])
                    pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                    usernames[pkg] = get_roblox_username(pkg)
                    break  # one reconnect per check cycle

        time.sleep(INTERVAL)

if __name__ == "__main__":
    monitor()