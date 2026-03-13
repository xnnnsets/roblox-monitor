import os
import re
import time
import json
import subprocess
import math
import shutil
import signal
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
SERVER_MODE = str(config.get("server_mode", "all")).lower()
SERVER_CODE_BY_PACKAGE = config.get("server_code_by_package", {})
CONFIG_PACKAGE = config.get("package", "")
PACKAGE_MODE = str(config.get("package_mode", "auto")).lower()
MANUAL_PACKAGES = config.get("manual_packages", [])
MONITOR_SELECTION = str(config.get("monitor_selection", "")).lower()
SELECTED_PACKAGES = config.get("selected_packages", [])
AFK_TIMEOUT_MIN = float(config.get("afk_timeout_minutes", 20))
LOG_SCAN_LINES = int(config.get("log_scan_lines", 4000))
AUTO_FLOAT_GRID = bool(config.get("auto_float_grid", True))
FLOAT_START_DELAY = int(config.get("float_start_delay_seconds", 3))
MULTI_LAUNCH_DELAY = int(config.get("multi_launch_delay_seconds", 30))
FLOAT_ORIENTATION_MODE = str(config.get("float_orientation_mode", "system")).lower()
GRID_LAYOUT_PRESET = str(config.get("grid_layout_preset", "balanced")).lower()

# ANSI color codes
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
RESET = "\033[0m"

def send_discord(msg):
    if WEBHOOK:
        try: requests.post(WEBHOOK, json={"content": msg}, timeout=5)
        except: pass

def get_server_code_for_package(package):
    if SERVER_MODE == "per_package" and isinstance(SERVER_CODE_BY_PACKAGE, dict):
        code = str(SERVER_CODE_BY_PACKAGE.get(package, "")).strip()
        if code:
            return code
    return CODE

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

def normalize_package_list(items):
    unique = []
    seen = set()
    for item in items:
        pkg = str(item).strip()
        if not pkg or pkg in seen:
            continue
        seen.add(pkg)
        unique.append(pkg)
    return unique

def resolve_target_packages(installed_packages):
    """Resolve package targets from config: auto/manual + all/selected."""
    installed = normalize_package_list(installed_packages)
    manual = normalize_package_list(MANUAL_PACKAGES if isinstance(MANUAL_PACKAGES, list) else [])
    selected = normalize_package_list(SELECTED_PACKAGES if isinstance(SELECTED_PACKAGES, list) else [])

    if CONFIG_PACKAGE:
        manual = normalize_package_list(manual + [CONFIG_PACKAGE])

    if PACKAGE_MODE == "manual":
        source = manual if manual else installed
    else:
        source = installed if installed else manual

    if MONITOR_SELECTION == "selected" and selected:
        ordered = [pkg for pkg in source if pkg in selected]
        extras = [pkg for pkg in selected if pkg not in ordered]
        target = normalize_package_list(ordered + extras)
        return target if target else source

    return source

def get_deeplink_activity(package):
    """Cari activity yang punya intent-filter untuk roblox:// scheme via pm dump."""
    # pm dump shows the Activity Resolver Table with scheme filters
    cmd = f"su -c \"pm dump {package} 2>/dev/null | grep -A3 'roblox:'\""
    output = os.popen(cmd).read()
    # Format output: com.roblox.client/.ActivityNativeMain atau com.pkg/full.Class.Name
    m = re.search(rf"{re.escape(package)}/\.?([A-Za-z0-9_.]+)", output)
    if m:
        activity = m.group(1)
        # Jika nama pendek (misal ActivityNativeMain), expand dengan com.roblox.client prefix
        if "." not in activity:
            return f"com.roblox.client.{activity}"
        return activity
    return None

def get_activity_name(package):
    """Detect main launcher activity name for a package, with fallbacks."""
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
    """Fast username detection via recent logcat only (avoid heavy root file scan)."""
    safe_pkg = re.escape(package)
    code, logcat = run_su(
        f"logcat -d -t 220 2>/dev/null | grep -Ei 'username|playername|{safe_pkg}' | tail -40",
        timeout=3,
    )
    if code != 0:
        return "unknown"
    for pattern in [
        r'"[Uu]ser[Nn]ame"\s*[=:]\s*"([A-Za-z0-9_]{3,20})"',
        r'[Uu]ser[Nn]ame["\s=:]+([A-Za-z0-9_]{3,20})',
    ]:
        m = re.search(pattern, logcat)
        if m and m.group(1).lower() not in ('null', 'true', 'false', 'string'):
            return m.group(1)
    return "unknown"

def save_username_cache(usernames):
    """Persist detected usernames into config.json for config_wizard labels."""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            latest_config = json.load(f)
    except Exception:
        return

    current_map = latest_config.get("package_usernames", {})
    if not isinstance(current_map, dict):
        current_map = {}

    changed = False
    for pkg, username in (usernames or {}).items():
        name = str(username or "").strip()
        if not name or name.lower() == "unknown":
            continue
        if current_map.get(pkg) != name:
            current_map[pkg] = name
            changed = True

    if not changed:
        return

    latest_config["package_usernames"] = current_map
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(latest_config, f, indent=2)
            f.write("\n")
    except Exception:
        return

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
        f"logcat -d -t {LOG_SCAN_LINES} 2>/dev/null"
        f" | grep -Ei 'Roblox  :|rbx\\.|com\\.roblox\\.client'"
        f" | tail -250"
    )
    code, output = run_su(cmd, timeout=5)
    if code != 0:
        return ""
    return output


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
    code, output = run_su(f"pidof {package} 2>/dev/null", timeout=3)
    pid = output.strip() if code == 0 else ""
    return pid, bool(pid)

def get_last_roblox_log_time(package):
    """Return timestamp of last Roblox log output, or None if no recent logs."""
    # Get recent Roblox logs with timestamp
    cmd = (
        f"logcat -d -t {LOG_SCAN_LINES} 2>/dev/null"
        f" | grep -Ei 'Roblox  :|rbx\\.|{package}'"
        f" | tail -20"
    )
    code, output = run_su(cmd, timeout=5)
    if code != 0:
        return None
    logs = output.strip().split('\n')
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

def run_su(command, timeout=8):
    try:
        result = subprocess.run(["su", "-c", command], capture_output=True, text=True, timeout=timeout)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode, output
    except Exception as e:
        return 1, str(e)

def get_screen_size():
    code, output = run_su("wm size 2>/dev/null")
    if code == 0:
        matches = re.findall(r"(\d+)x(\d+)", output)
        if matches:
            # Prefer baris terakhir (override size jika ada)
            w, h = matches[-1]
            return int(w), int(h)
    return 1080, 2400

def find_task_id(package):
    commands = [
        f"am task list 2>/dev/null | grep -Ei '{package}|task' | head -3",
        f"cmd activity tasks 2>/dev/null | grep -Ei '{package}|task' | head -3",
        f"dumpsys activity activities 2>/dev/null | grep -E 'taskId=[0-9]+.*{package}/' | head -1",
        f"dumpsys activity recents 2>/dev/null | grep -E 'taskId=[0-9]+.*{package}/' | head -1",
        f"am stack list 2>/dev/null | grep -E 'taskId=[0-9]+.*{package}/' | head -1",
    ]
    for cmd in commands:
        _, output = run_su(cmd)
        patterns = [r"taskId=(\d+)", r"\bid=(\d+)\b", r"Task\s*(?:id\s*)?#?(\d+)"]
        for pattern in patterns:
            m = re.search(pattern, output, re.IGNORECASE)
            if m:
                return int(m.group(1))
    return None


def clamp_bounds(left, top, right, bottom, width, height, top_offset=0):
    safe = max(14, min(width, height) // 35)
    min_w = max(78, width // 10)
    min_h = max(96, height // 10)

    max_left = max(safe, width - safe - min_w)
    max_top = max(max(top_offset, safe), height - safe - min_h)

    left = max(safe, min(left, max_left))
    top = max(max(top_offset, safe), min(top, max_top))
    right = min(width - safe, max(right, left + min_w))
    bottom = min(height - safe, max(bottom, top + min_h))

    if right - left < min_w:
        left = max(safe, right - min_w)
    if bottom - top < min_h:
        top = max(max(top_offset, safe), bottom - min_h)

    return int(left), int(top), int(right), int(bottom)

def get_grid_bounds(index, total, width, height):
    total = max(1, total)
    gap = max(8, min(width, height) // 110)
    top_offset = 58
    bottom_margin = 12
    if FLOAT_ORIENTATION_MODE == "landscape":
        is_landscape = True
    elif FLOAT_ORIENTATION_MODE == "portrait":
        is_landscape = False
    else:
        is_landscape = width > height

    # Dock semua jendela ke sisi kanan layar
    dock_ratio = 0.56 if is_landscape else 0.50
    dock_width = max(260, int(width * dock_ratio))
    dock_left = max(0, width - dock_width)

    available_w = max(200, dock_width - (gap * 2))
    available_h = max(260, height - top_offset - bottom_margin - gap)

    # Cell size + column count berdasarkan preset layout
    preset = GRID_LAYOUT_PRESET
    if preset == "ultra-compact":
        max_w = 160 if is_landscape else 135
        max_h = 155 if is_landscape else 170
        min_w = 90 if is_landscape else 85
        min_h = 110 if is_landscape else 115
        cols = (5 if total >= 12 else 4 if total >= 6 else 3) if is_landscape \
            else (4 if total >= 8 else 3 if total >= 3 else 2)
    elif preset == "compact":
        max_w = 225 if is_landscape else 175
        max_h = 190 if is_landscape else 210
        min_w = 105 if is_landscape else 98
        min_h = 125 if is_landscape else 130
        cols = (4 if total >= 8 else 3 if total >= 4 else 2) if is_landscape \
            else (3 if total >= 6 else 2 if total > 1 else 1)
    elif preset == "wide":
        max_w = 370 if is_landscape else 275
        max_h = 285 if is_landscape else 315
        min_w = 150 if is_landscape else 130
        min_h = 165 if is_landscape else 175
        cols = (3 if total >= 7 else 2 if total >= 3 else 1) if is_landscape \
            else (2 if total >= 4 else 1)
    else:  # balanced (default)
        max_w = 280 if is_landscape else 210
        max_h = 220 if is_landscape else 250
        min_w = 120 if is_landscape else 110
        min_h = 140 if is_landscape else 145
        cols = (4 if total >= 10 else 3 if total >= 4 else 2) if is_landscape \
            else (3 if total >= 7 else 2 if total > 1 else 1)

    cols = max(1, min(cols, total))

    # Cari kombinasi kolom/baris terbaik agar fit layar dan tidak offside
    pref_cols = cols
    floor_w = max(72, min_w - 46)
    floor_h = max(86, min_h - 52)
    best = None
    for cand_cols in range(1, total + 1):
        cand_rows = max(1, math.ceil(total / cand_cols))
        raw_w = (available_w - (gap * (cand_cols - 1))) // cand_cols
        raw_h = (available_h - (gap * (cand_rows - 1))) // cand_rows
        if raw_w < floor_w or raw_h < floor_h:
            continue
        score = (raw_w * raw_h) - abs(cand_cols - pref_cols) * 90
        if best is None or score > best[0]:
            best = (score, cand_cols, cand_rows, raw_w, raw_h)

    if best is None:
        rows = max(1, math.ceil(total / cols))
        raw_w = max(70, (available_w - (gap * (cols - 1))) // cols)
        raw_h = max(82, (available_h - (gap * (rows - 1))) // rows)
    else:
        _, cols, rows, raw_w, raw_h = best

    cell_w = max(floor_w, min(raw_w, max_w))
    cell_h = max(floor_h, min(raw_h, max_h))

    row = index // cols
    col = index % cols

    used_w = cols * cell_w + (cols - 1) * gap
    start_x = width - gap - used_w
    min_left = 0 if is_landscape else dock_left + gap
    if start_x < min_left:
        start_x = min_left

    left = start_x + col * (cell_w + gap)
    top = top_offset + gap + row * (cell_h + gap)
    right = min(width - gap, left + cell_w)
    bottom = min(height - gap, top + cell_h)

    return clamp_bounds(left, top, right, bottom, width, height, top_offset=top_offset)

def apply_float_grid(package, grid_index, grid_total):
    if not AUTO_FLOAT_GRID or grid_total <= 1:
        return

    run_su("settings put global enable_freeform_support 1")
    run_su("settings put global force_resizable_activities 1")

    # Paksa orientasi dulu, lalu baru hitung ukuran layar agar koordinat akurat.
    if FLOAT_ORIENTATION_MODE == "landscape":
        run_su("settings put system user_rotation 1")
        run_su("settings put system accelerometer_rotation 0")
        time.sleep(0.35)
    elif FLOAT_ORIENTATION_MODE == "portrait":
        run_su("settings put system user_rotation 0")
        run_su("settings put system accelerometer_rotation 0")
        time.sleep(0.35)

    time.sleep(FLOAT_START_DELAY)
    task_id = None
    for _ in range(4):
        task_id = find_task_id(package)
        if task_id is not None:
            break
        time.sleep(0.7)
    if task_id is None:
        print(f"[!] Float skip: task id tidak ditemukan untuk {package}")
        return

    width, height = get_screen_size()
    left, top, right, bottom = get_grid_bounds(grid_index, grid_total, width, height)

    float_commands = [
        f"cmd activity task set-windowing-mode {task_id} 5",
        f"am stack move-task {task_id} 2 true",
        f"cmd activity move-task {task_id} 2 true",
        f"am task resize {task_id} {left} {top} {right} {bottom}",
        f"cmd activity task resize {task_id} {left} {top} {right} {bottom}",
        f"am stack resize 2 {left} {top} {right} {bottom}",
    ]

    success = False
    for cmd in float_commands:
        code, output = run_su(cmd)
        if code == 0 and "error" not in output.lower() and "unknown" not in output.lower():
            success = True

    if success:
        print(f"[✓] Float grid applied: {package} -> [{left},{top},{right},{bottom}]")
    else:
        print(f"[!] Float grid tidak didukung penuh di ROM ini ({package})")

def join_server(package, activity_name, grid_index=0, grid_total=1):
    package_code = get_server_code_for_package(package)
    link = f"roblox://navigation/share_links?code={package_code}&type=Server"
    print(f"[+] Joining: {link}")
    print(f"[+] Package: {package}")
    
    launched = False
    
    # Step 1: Cari activity yang handle roblox:// scheme dari pm dump
    resolved = get_deeplink_activity(package)
    if resolved:
        print(f"[*] Deeplink activity ditemukan: {resolved}")
    
    # Daftar activity untuk dicoba (hindari splash)
    activities_to_try = []
    for act in [
        resolved,
        "com.roblox.client.ActivityNativeMain",
        f"{package}.ActivityNativeMain",
        "com.roblox.client.RobloxActivity",
    ]:
        if act and act not in activities_to_try and 'splash' not in act.lower():
            activities_to_try.append(act)
    
    for activity in activities_to_try:
        print(f"[*] Trying: -n {package}/{activity}")
        start_commands = []
        if AUTO_FLOAT_GRID:
            start_commands.append(
                f"am start --windowingMode 5 -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'"
            )
        start_commands.append(
            f"am start -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'"
        )

        for start_cmd in start_commands:
            code, out = run_su(start_cmd, timeout=6)
            print(f"    {out[:100]}")
            if code == 0 and 'error' not in out.lower() and 'unknown option' not in out.lower():
                print(f"[✓] Launched via {activity}")
                launched = True
                break
        if launched:
            break
    
    if not launched:
        print("[!] All explicit failed, fallback implicit...")
        run_su(f"am start -a android.intent.action.VIEW -d '{link}'", timeout=6)

    apply_float_grid(package, grid_index, grid_total)

def display_dashboard(packages_info, memory_info, check_count):
    """Render a bordered table: PACKAGE (username) | STATUS, plus a memory row."""
    total, free, pct = memory_info

    term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    table_width = max(40, min(110, term_cols - 2))
    col2 = max(12, min(20, table_width // 3))
    col1 = max(22, table_width - col2)
    sep  = f"+{'-' * col1}+{'-' * col2}+"

    def fit_text(text, width):
        text = str(text)
        if width <= 1:
            return text[:width]
        return text if len(text) <= width else text[: width - 1] + "…"

    os.system('clear')
    print(sep)
    header_pkg = f" {fit_text('PACKAGE', col1 - 2):<{col1 - 2}} "
    header_st  = f" {fit_text('STATUS', col2 - 2):<{col2 - 2}} "
    print(f"|{CYAN}{header_pkg}{RESET}|{CYAN}{header_st}{RESET}|")
    print(sep)

    for pkg, username, running in packages_info:
        label       = fit_text(f"{pkg} ({username})", col1 - 2)
        status_text = "Online" if running else "Offline"
        status_col  = GREEN if running else RED
        # Build padded fields (colour codes are zero-width for alignment purposes)
        pkg_field = f" {label:<{col1 - 2}} "
        st_field  = f" {fit_text(status_text, col2 - 2):<{col2 - 2}} "
        print(f"|{pkg_field}|{status_col}{st_field}{RESET}|")

    # Memory row
    print(sep)
    mem_label  = fit_text(" System Memory", col1)
    n          = len(packages_info)
    mem_status = fit_text(f"Checking [{check_count}/{n}] Free: {free}MB ({pct}%)", col2 - 2)
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
    installed_packages = find_roblox_packages()
    target_packages = resolve_target_packages(installed_packages)
    if not target_packages:
        target_packages = installed_packages
    if not target_packages:
        target_packages = ["com.roblox.client"]

    # Validasi server code per-package jika mode per_package
    if SERVER_MODE == "per_package":
        missing_codes = [
            pkg for pkg in target_packages
            if not str(SERVER_CODE_BY_PACKAGE.get(pkg, "")).strip()
        ]
        if missing_codes:
            print(f"[!] WARNING: {len(missing_codes)} package tidak punya server code per-package:")
            for pkg in missing_codes:
                print(f"    - {pkg}")
            if CODE.strip():
                print(f"[!] Fallback ke global server code: {CODE[:22]}..." if len(CODE) > 22 else f"[!] Fallback ke global server code: {CODE}")
            else:
                print("[!] GLOBAL FALLBACK JUGA KOSONG! Package tsb tidak akan join private server.")

    print(f"[v] Installed: {len(installed_packages)} paket: {', '.join(installed_packages)}")
    print(f"[v] Target monitor: {len(target_packages)} paket: {', '.join(target_packages)}")

    # Get activity names for each package
    print("[v] Mendeteksi activity names...")
    activity_map = {}
    for pkg in target_packages:
        activity_map[pkg] = get_activity_name(pkg)
        print(f"    {pkg} -> {activity_map[pkg]}")

    print("[v] Membaca username Roblox...")
    usernames = {}
    for pkg in target_packages:
        usernames[pkg] = get_roblox_username(pkg)
        print(f"    {pkg} -> {usernames[pkg]}")
    save_username_cache(usernames)

    # Fallback interactive menu only if config has no explicit selection mode
    if len(target_packages) > 1 and MONITOR_SELECTION not in ("all", "selected"):
        print("\n" + "="*50)
        print("Pilihan Monitor:")
        print("1. Monitor SEMUA Roblox apps")
        for i, pkg in enumerate(target_packages, start=2):
            print(f"{i}. Monitor hanya {pkg} ({usernames[pkg]})")
        print("="*50)
        choice = input("Pilih nomor (default 1): ").strip() or "1"
        try:
            choice_idx = int(choice) - 1
            if choice_idx == 0:
                print(f"✓ Monitor SEMUA ({len(target_packages)} apps)")
            elif 0 < choice_idx < len(target_packages) + 1:
                target_packages = [target_packages[choice_idx - 1]]
                print(f"✓ Monitor hanya: {target_packages[0]} ({usernames[target_packages[0]]})")
            else:
                print("❌ Pilihan invalid, default ke monitor semua.")
                pass
        except ValueError:
            print("❌ Input invalid, default ke monitor semua.")
            pass

    print("[v] Menghapus log lama...")
    os.system('su -c "logcat -c"')
    time.sleep(1)

    # Track join time dan last activity time per package
    pkg_state = {pkg: {'join_time': datetime.now(), 'last_activity': datetime.now()} for pkg in target_packages}
    grid_index_map = {pkg: idx for idx, pkg in enumerate(target_packages)}
    grid_total = len(target_packages)
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
        crashed_pkgs = [pkg for pkg, username, running in packages_info if not running]
        for i, pkg in enumerate(crashed_pkgs):
            crashed.add(pkg)
            print(f"\n[{time.strftime('%H:%M:%S')}] ❌ {pkg} Crash/Mati")
            send_discord(f"❌ {pkg} Crash! Membuka ulang...")
            kill_roblox(pkg)
            join_server(pkg, activity_map[pkg], grid_index_map[pkg], grid_total)
            pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
            usernames[pkg] = get_roblox_username(pkg)
            save_username_cache({pkg: usernames[pkg]})
            # Jeda antar app jika ada lebih dari 1 yang harus dibuka
            if i < len(crashed_pkgs) - 1:
                print(f"[*] Menunggu {MULTI_LAUNCH_DELAY} detik sebelum membuka app berikutnya...")
                time.sleep(MULTI_LAUNCH_DELAY)

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
                    join_server(pkg, activity_map[pkg], grid_index_map[pkg], grid_total)
                    pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                    usernames[pkg] = get_roblox_username(pkg)
                    save_username_cache({pkg: usernames[pkg]})
                    break

        # Handle global disconnect / error detected in logcat (reconnect one package)
        if is_error:
            for pkg, username, running in packages_info:
                if running and pkg not in crashed:
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⚠️  Error: {reason} [{pkg}]")
                    send_discord(f"⚠️ {pkg} Terputus! Alasan: {reason}. Rejoining...")
                    kill_roblox(pkg)
                    join_server(pkg, activity_map[pkg], grid_index_map[pkg], grid_total)
                    pkg_state[pkg] = {'join_time': datetime.now(), 'last_activity': datetime.now()}
                    usernames[pkg] = get_roblox_username(pkg)
                    save_username_cache({pkg: usernames[pkg]})
                    break  # one reconnect per check cycle

        time.sleep(INTERVAL)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    if hasattr(signal, "SIGTSTP"):
        signal.signal(signal.SIGTSTP, signal.default_int_handler)
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n[!] Monitor dihentikan user (Ctrl+C).")
        sys.exit(0)