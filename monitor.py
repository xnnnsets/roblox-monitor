import os
import re
import time
import json
import subprocess
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
    """Try to get the Roblox username stored in the package's shared preferences."""
    # Try reading from shared_prefs XML files
    raw = os.popen(
        f'su -c "grep -r \'username\\|Username\\|robloxUsername\' '
        f'/data/data/{package}/shared_prefs/ 2>/dev/null | head -10"'
    ).read()
    match = re.search(r'name="[Uu]ser[Nn]ame"[^>]*>([^<\s]+)<', raw)
    if match:
        return match.group(1)
    # Broader key scan
    match = re.search(r'[Uu]ser[Nn]ame["\s]*[:=>]+["\s]*([A-Za-z0-9_]+)', raw)
    if match:
        return match.group(1)
    # Try logcat as last resort
    logcat = os.popen(
        f'su -c "logcat -d -t 100 2>/dev/null | grep -i \'username\' | tail -5"'
    ).read()
    match = re.search(r'[Uu]ser[Nn]ame[\'"]?\s*[:=]\s*[\'"]?([A-Za-z0-9_]+)', logcat)
    if match:
        return match.group(1)
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

def check_game_status():
    cmd = 'su -c "logcat -d -t 200 2>/dev/null | grep -Ei \'com.roblox|Disconnect|Error Code:|Connection lost|appStopped=true|kick\'"'
    logs = os.popen(cmd).read()
    triggers = [
        "Error Code: 277", "Error Code: 279", "Connection lost",
        "Disconnected from server", "appStopped=true", "was kicked"
    ]
    for trigger in triggers:
        if trigger.lower() in logs.lower():
            return True, trigger
    return False, None

def is_package_running(package):
    pid = os.popen(f'su -c "pidof {package}" 2>/dev/null').read().strip()
    return pid, bool(pid)

def kill_roblox(package):
    print(f"[!] Killing {package} & Cleaning Logs...")
    os.system(f'su -c "am force-stop {package}"')
    os.system('su -c "logcat -c"')

def join_server(package):
    link = f"https://www.roblox.com/share?code={CODE}&type=Server"
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
                usernames[pkg] = get_roblox_username(pkg)

        # Handle global disconnect / error detected in logcat (reconnect one package)
        if is_error:
            for pkg, username, running in packages_info:
                if running and pkg not in crashed:
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⚠️  Error: {reason} [{pkg}]")
                    send_discord(f"⚠️ {pkg} Terputus! Alasan: {reason}. Rejoining...")
                    kill_roblox(pkg)
                    join_server(pkg)
                    usernames[pkg] = get_roblox_username(pkg)
                    break  # one reconnect per check cycle

        time.sleep(INTERVAL)

if __name__ == "__main__":
    monitor()