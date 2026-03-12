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
AFK_TIMEOUT_MIN = config.get("afk_timeout_minutes", 20)

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

def check_game_status(since_dt=None):
    """Check for critical error patterns dalam logcat (crash, kick, ban, etc)."""
    # Get recent logs (last 2000 lines to cover 20 min at high volume)
    cmd = 'su -c "logcat -d -t 2000 2>/dev/null"'
    logs = os.popen(cmd).read()
    
    # Cari keywords: kick, ban, removed, error code, connection lost
    keywords = [
        ("Error Code: 26[0-9]", "AFK Timeout"),
        ("Error Code: 27[0-9]", "Connection Error"),
        (r"you.*kicked|was.*kicked", "Kicked"),
        (r"you.*banned|was.*banned", "Banned"),
        (r"removed from|server full", "Removed"),
        (r"Connection.*lost|Disconnect", "Disconnected"),
    ]
    
    for pattern, reason in keywords:
        if re.search(pattern, logs, re.IGNORECASE):
            return True, reason
    
    return False, None

def is_package_running(package):
    pid = os.popen(f'su -c "pidof {package}" 2>/dev/null').read().strip()
    return pid, bool(pid)

def get_last_roblox_log_time(package):
    """Return timestamp of last Roblox log output, or None if no recent logs."""
    # Get last 50 Roblox logs dengan timestamp
    cmd = f'su -c "logcat -d -t 1000 2>/dev/null | grep -E \'Roblox|{package}\' | tail -10"'
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
        return False, None
    
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
        return True, f"AFK {int(time_since_activity.total_seconds() / 60)} min"
    
    return False, None

def kill_roblox(package):
    print(f"[!] Killing {package} & Cleaning Logs...")
    os.system(f'su -c "am force-stop {package}"')
    os.system('su -c "logcat -c"')

def join_server(package):
    link = f"roblox://navigation/share_links?code={CODE}&type=Server"
    print(f"[+] Launching: {link}")
    os.system(f'su -c "am start -a android.intent.action.VIEW -d \'{link}\'"')
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

    print("[v] Membaca username Roblox...")
    usernames = {}
    for pkg in packages:
        usernames[pkg] = get_roblox_username(pkg)
        print(f"    {pkg} -> {usernames[pkg]}")

    print("[v] Menghapus log lama...")
    os.system('su -c "logcat -c"')
    time.sleep(1)

    # Track join time dan last activity time per package
    pkg_state = {pkg: {'join_time': datetime.now(), 'last_activity': datetime.now()} for pkg in packages}
    check_count = 0
    while True:
        check_count = (check_count % len(packages)) + 1
        is_error, reason = check_game_status()

        packages_info = []
        for pkg in packages:
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
                join_server(pkg)
                pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                usernames[pkg] = get_roblox_username(pkg)

        # Check AFK timeout (game freezed, no activity)
        for pkg, username, running in packages_info:
            if running and pkg not in crashed:
                is_afk, afk_reason = check_afk_timeout(pkg, pkg_state[pkg]['join_time'], pkg_state[pkg]['last_activity'])
                if is_afk:
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⏱️  AFK Detected: {afk_reason} [{pkg}]")
                    send_discord(f"⏱️ {pkg} AFK/Freezed! {afk_reason}. Reconnecting...")
                    kill_roblox(pkg)
                    join_server(pkg)
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
                    join_server(pkg)
                    pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                    usernames[pkg] = get_roblox_username(pkg)
                    break  # one reconnect per check cycle

        time.sleep(INTERVAL)

if __name__ == "__main__":
    monitor()