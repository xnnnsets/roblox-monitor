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

STOP_FILE = os.path.expanduser("~/.roblox-monitor.stop")

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
AUTO_FLOAT = bool(config.get("auto_float", config.get("auto_float_grid", True)))
AUTO_GRID = bool(config.get("auto_grid", config.get("auto_float_grid", True)))
FLOAT_START_DELAY = int(config.get("float_start_delay_seconds", 3))
MULTI_LAUNCH_DELAY = int(config.get("multi_launch_delay_seconds", 30))
FLOAT_ORIENTATION_MODE = str(config.get("float_orientation_mode", "system")).lower()
GRID_LAYOUT_PRESET = str(config.get("grid_layout_preset", "balanced")).lower()

# ANSI color codes
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
RESET = "\033[0m"

DEVICE_PROFILE = {
    "checked": False,
    "sdk": 0,
    "density": 0,
    "scale": 1.0,
    "width": 1080,
    "height": 2400,
    "safe_inset_x": 24,
    "safe_inset_y": 32,
}


def term_cols() -> int:
    return max(30, shutil.get_terminal_size(fallback=(60, 24)).columns)


def short_code(text: str, head: int = 8) -> str:
    value = str(text or "").strip()
    if not value:
        return "-"
    if len(value) <= head:
        return value
    return value[:head] + "..."

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


def enable_freeform_compat_settings():
    """Best-effort compatibility toggles for freeform on mixed ROMs/cloud devices."""
    commands = [
        "settings put global enable_freeform_support 1",
        "settings put global force_resizable_activities 1",
        "settings put global enable_non_resizable_multi_window 1",
        "settings put global development_settings_enabled 1",
        "settings put global freeform_window_management 1",
        "settings put secure freeform_window_management 1",
        "setprop persist.sys.fflag.override.settings_enable_freeform_support true",
        "setprop persist.sys.debug.multi_window true",
        "setprop persist.sys.freeform_window 1",
    ]
    for cmd in commands:
        run_su(cmd, timeout=4)


def should_stop_monitor():
    return os.path.exists(STOP_FILE)


def clear_stop_file():
    try:
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)
    except OSError:
        pass


def get_device_profile():
    if DEVICE_PROFILE["checked"]:
        return DEVICE_PROFILE

    DEVICE_PROFILE["checked"] = True

    try:
        sdk_raw = subprocess.run(["sh", "-c", "getprop ro.build.version.sdk"], capture_output=True, text=True, timeout=3).stdout.strip()
        DEVICE_PROFILE["sdk"] = int(sdk_raw or "0")
    except Exception:
        DEVICE_PROFILE["sdk"] = 0

    width, height = get_screen_size()
    DEVICE_PROFILE["width"] = width
    DEVICE_PROFILE["height"] = height

    density = 0
    code, density_out = run_su("wm density 2>/dev/null")
    if code == 0:
        density_matches = re.findall(r"(\d+)", density_out)
        if density_matches:
            density = int(density_matches[-1])
    if density <= 0:
        try:
            raw = subprocess.run(["sh", "-c", "getprop ro.sf.lcd_density"], capture_output=True, text=True, timeout=3).stdout.strip()
            density = int(raw or "0")
        except Exception:
            density = 0
    if density <= 0:
        density = 420

    scale = max(1.0, density / 160.0)
    DEVICE_PROFILE["density"] = density
    DEVICE_PROFILE["scale"] = scale

    # Density-aware safe insets from screen edges (edge-to-edge safety)
    DEVICE_PROFILE["safe_inset_x"] = max(16, int(10 * scale), width // 48)
    DEVICE_PROFILE["safe_inset_y"] = max(20, int(14 * scale), height // 50)
    return DEVICE_PROFILE


def extract_task_id_from_text(text):
    if not text:
        return None
    patterns = [
        r"[Tt]ask\s+id[:\s]+([1-9]\d*)",      # "Task id: 67" - from am start output
        r"mTaskId\s*=\s*([1-9]\d*)",            # mTaskId=67 from dumpsys window
        r"taskId=([1-9]\d*)",
        r"Task\{[^#\n]*#([1-9]\d*)",
        r"\bTaskRecord\{[^#\n]*#([1-9]\d*)",
        r"\bt(\d{1,5})\b",
        r"\bid=(\d{1,5})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                value = int(m.group(1))
                if value > 0:
                    return value
            except Exception:
                pass
    return None

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
    pkg = package
    commands = [
        "dumpsys activity activities 2>/dev/null",
        "dumpsys activity recents 2>/dev/null",
        "cmd activity tasks 2>/dev/null",
        "am task list 2>/dev/null",
    ]

    for cmd in commands:
        _, output = run_su(cmd, timeout=6)
        if not output:
            continue

        lines = output.splitlines()
        candidates = []
        for idx, line in enumerate(lines):
            if pkg not in line:
                continue
            start = max(0, idx - 3)
            end = min(len(lines), idx + 4)
            context = "\n".join(lines[start:end])
            task_id = extract_task_id_from_text(context)
            if task_id is not None:
                candidates.append(task_id)

        if candidates:
            return max(candidates)
    return None


def find_task_candidates(package):
    """Return ordered unique taskId candidates related to package."""
    pkg = package
    commands = [
        "dumpsys activity activities 2>/dev/null",
        "dumpsys activity recents 2>/dev/null",
        "dumpsys window windows 2>/dev/null",   # reliable mTaskId= source
        "cmd activity tasks 2>/dev/null",
        "am task list 2>/dev/null",
        "dumpsys activity top 2>/dev/null",
    ]

    ids = []
    seen = set()

    def push(task_id):
        if task_id is None:
            return
        if task_id in seen:
            return
        seen.add(task_id)
        ids.append(task_id)

    for cmd in commands:
        _, output = run_su(cmd, timeout=6)
        if not output:
            continue

        lines = output.splitlines()
        for idx, line in enumerate(lines):
            if pkg not in line:
                continue

            # Parse same line first.
            push(extract_task_id_from_text(line))

            # Then parse a wider context around the package line.
            start = max(0, idx - 12)
            end = min(len(lines), idx + 13)
            context = "\n".join(lines[start:end])
            push(extract_task_id_from_text(context))

    # Last fallback: existing single best finder
    push(find_task_id(package))
    return ids


def try_apply_float_commands(task_id, left, top, right, bottom, apply_float=True, apply_grid=True):
    commands = [
        *(
            [
                f"cmd activity task set-windowing-mode {task_id} 5",
                f"cmd activity set-windowing-mode {task_id} 5",
                f"am stack move-task {task_id} 2 true",
                f"cmd activity move-task {task_id} 2 true",
            ]
            if apply_float
            else []
        ),
        *(
            [
                f"am task resize {task_id} {left} {top} {right} {bottom}",
                f"cmd activity task set-bounds {task_id} {left} {top} {right} {bottom}",
                f"cmd activity task resize {task_id} {left} {top} {right} {bottom}",
                f"am stack resize 2 {left} {top} {right} {bottom}",
            ]
            if apply_grid
            else []
        ),
    ]

    success = False
    for cmd in commands:
        code, output = run_su(cmd, timeout=5)
        out = (output or "").lower()
        if code == 0 and "error" not in out and "unknown" not in out and "exception" not in out:
            success = True
    return success


def clamp_bounds(left, top, right, bottom, width, height, safe_left, safe_top, safe_right, safe_bottom, min_w, min_h):
    max_left = max(safe_left, safe_right - min_w)
    max_top = max(safe_top, safe_bottom - min_h)

    left = max(safe_left, min(left, max_left))
    top = max(safe_top, min(top, max_top))
    right = min(safe_right, max(right, left + min_w))
    bottom = min(safe_bottom, max(bottom, top + min_h))

    if right - left < min_w:
        left = max(safe_left, right - min_w)
    if bottom - top < min_h:
        top = max(safe_top, bottom - min_h)

    return int(left), int(top), int(right), int(bottom)

def get_grid_bounds(index, total, width, height):
    total = max(1, total)
    profile = get_device_profile()
    scale = profile["scale"]
    dpi = profile["density"]
    edge_x = profile["safe_inset_x"]
    edge_y = profile["safe_inset_y"]
    gap = max(8, int(6 * scale), min(width, height) // 120)
    top_offset = max(58, edge_y + int(10 * scale))
    bottom_margin = max(12, edge_y)

    if FLOAT_ORIENTATION_MODE == "landscape":
        is_landscape = True
    elif FLOAT_ORIENTATION_MODE == "portrait":
        is_landscape = False
    else:
        is_landscape = width > height

    # Density-aware safe rectangle from edge-to-edge screen.
    safe_left = edge_x
    safe_right = width - edge_x
    safe_top = top_offset
    safe_bottom = height - bottom_margin

    available_total_w = max(240, safe_right - safe_left)
    available_total_h = max(260, safe_bottom - safe_top)

    # Dock region near right side with conservative ratio to avoid offside.
    dock_ratio = 0.40 if is_landscape else 0.32
    if profile["sdk"] >= 34:
        dock_ratio = 0.36 if is_landscape else 0.30
    if GRID_LAYOUT_PRESET == "wide":
        dock_ratio += 0.04
    elif GRID_LAYOUT_PRESET == "ultra-compact":
        dock_ratio -= 0.03

    dock_ratio = max(0.26, min(0.56, dock_ratio))
    dock_width = max(int(220 * scale), int(available_total_w * dock_ratio))
    dock_width = min(available_total_w, dock_width)

    dock_left = safe_right - dock_width
    available_w = max(180, dock_width - (gap * 2))
    available_h = max(220, available_total_h - gap)

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
    floor_w = max(int(64 * scale), min_w - int(44 * scale))
    floor_h = max(int(78 * scale), min_h - int(48 * scale))
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
    start_x = safe_right - used_w
    min_left = safe_left if is_landscape else dock_left + gap
    if start_x < min_left:
        start_x = min_left

    left = start_x + col * (cell_w + gap)
    top = safe_top + row * (cell_h + gap)
    right = min(safe_right, left + cell_w)
    bottom = min(safe_bottom, top + cell_h)

    min_bound_w = max(int(76 * scale), width // 11)
    min_bound_h = max(int(92 * scale), height // 11)
    return clamp_bounds(
        left,
        top,
        right,
        bottom,
        width,
        height,
        safe_left,
        safe_top,
        safe_right,
        safe_bottom,
        min_bound_w,
        min_bound_h,
    )

def apply_float_grid(package, grid_index, grid_total, task_id_hint=None):
    if not AUTO_FLOAT and not AUTO_GRID:
        return

    if AUTO_FLOAT:
        enable_freeform_compat_settings()

    # NOTE: Jangan paksa rotasi sistem di sini.
    # Di beberapa device/ROM (terutama virtual), ini memutar seluruh UI Termux
    # dan justru bikin tampilan monitor berantakan.

    time.sleep(FLOAT_START_DELAY)

    success = False
    candidates = []
    if task_id_hint is not None:
        candidates.append(task_id_hint)

    profile = get_device_profile()
    pass_delays = [0.0, 0.7, 1.3, 2.2]
    if profile["sdk"] >= 34:
        pass_delays.append(3.2)

    for extra_delay in pass_delays:
        if extra_delay > 0:
            time.sleep(extra_delay)

        width, height = get_screen_size()
        left, top, right, bottom = get_grid_bounds(grid_index, grid_total, width, height)

        discovered = find_task_candidates(package)
        for task_id in discovered:
            if task_id not in candidates:
                candidates.append(task_id)

        for task_id in candidates:
            if try_apply_float_commands(task_id, left, top, right, bottom, apply_float=AUTO_FLOAT, apply_grid=AUTO_GRID):
                success = True
                break

        if success:
            break

    if success:
        print(f"[✓] Float grid applied: {package} -> [{left},{top},{right},{bottom}]")
    else:
        hint = f" candidates={candidates}" if candidates else ""
        print(f"[!] Float gagal untuk {package}.{hint}")

def join_server(package, activity_name, grid_index=0, grid_total=1):
    package_code = get_server_code_for_package(package)
    link = f"roblox://navigation/share_links?code={package_code}&type=Server"
    print(f"[+] Joining server code: {short_code(package_code)}")
    print(f"[+] Package: {package}")

    launch_bounds = ""
    if AUTO_GRID:
        width, height = get_screen_size()
        left, top, right, bottom = get_grid_bounds(grid_index, grid_total, width, height)
        launch_bounds = f"{left},{top},{right},{bottom}"
    
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

    launched_task_id = None
    
    for activity in activities_to_try:
        print(f"[*] Trying: -n {package}/{activity}")
        # Always try --windowingMode 5 first.
        # If unsupported by ROM, command will fail and fallback launch is used.
        start_commands = []
        if AUTO_FLOAT:
            if AUTO_GRID and launch_bounds:
                start_commands.append(
                    f"am start --windowingMode 5 --activity-launch-bounds {launch_bounds} -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'"
                )
            start_commands.append(
                f"am start --windowingMode 5 -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'"
            )
        elif AUTO_GRID and launch_bounds:
            start_commands.append(
                f"am start --activity-launch-bounds {launch_bounds} -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'"
            )
        start_commands.append(
            f"am start -n '{package}/{activity}' -a android.intent.action.VIEW -d '{link}'"
        )

        for start_cmd in start_commands:
            code, out = run_su(start_cmd, timeout=8)
            out_lower = out.lower()
            bad = 'error: ' in out_lower or 'unknown option' in out_lower or 'exception' in out_lower
            if code == 0 and not bad:
                launched_task_id = extract_task_id_from_text(out)
                print(f"[✓] Launched via {activity}")
                launched = True
                break
        if launched:
            if launched_task_id is not None:
                print(f"[*] taskId detected: {launched_task_id}")
            break
    
    if not launched:
        print("[!] All explicit failed, fallback implicit...")
        run_su(f"am start -a android.intent.action.VIEW -d '{link}'", timeout=6)

    apply_float_grid(package, grid_index, grid_total, task_id_hint=launched_task_id)

def display_dashboard(packages_info, memory_info, check_count):
    """Ultra-compact dashboard — safe down to ~30 column Termux screens."""
    total, free, pct = memory_info
    term_cols = max(30, shutil.get_terminal_size(fallback=(60, 24)).columns)

    def fit_text(text, width):
        text = str(text)
        if width <= 0:
            return ""
        return text if len(text) <= width else text[: max(0, width - 1)] + "…"

    sep = "-" * min(40, term_cols)
    os.system('clear')
    print(sep)
    print(fit_text("ROBLOX MONITOR", term_cols))
    print(sep)

    n = len(packages_info)
    for idx, (pkg, username, running) in enumerate(packages_info, start=1):
        status_text = "ON" if running else "OFF"
        status_col = GREEN if running else RED
        short_pkg = pkg.replace("com.roblox.", "rblx.")
        uname = username if username != "unknown" else "?"
        prefix = f"{idx}."
        avail = term_cols - len(prefix) - 1 - len(status_text) - 1
        label = fit_text(f"{short_pkg}({uname})", max(8, avail))
        print(f"{prefix} {label} {status_col}{status_text}{RESET}")

    print(sep)
    mem_line = f"RAM:{free}MB({pct}%) [{check_count}/{max(1,n)}]"
    print(fit_text(mem_line, term_cols))
    print(sep)


def apply_float_grid_to_running_targets(target_packages, grid_index_map, grid_total):
    if not AUTO_FLOAT and not AUTO_GRID:
        return
    any_running = False
    for pkg in target_packages:
        _, running = is_package_running(pkg)
        if not running:
            continue
        any_running = True
        print(f"[*] Apply float startup: {pkg}")
        apply_float_grid(pkg, grid_index_map[pkg], grid_total)
        time.sleep(0.4)

    # Pass kedua: beberapa ROM baru expose task setelah beberapa detik.
    if any_running:
        time.sleep(1.2)
        for pkg in target_packages:
            _, running = is_package_running(pkg)
            if not running:
                continue
            apply_float_grid(pkg, grid_index_map[pkg], grid_total)
            time.sleep(0.35)
    if any_running:
        print("[v] Float startup sync selesai.")

def monitor():
    clear_stop_file()
    os.system('clear')
    print("==========================================")
    print("   ROBLOX LOG-HUNTER (STABLE ROOT)")
    print("==========================================")

    if not check_root_permission():
        print("\n[!!!] ERROR: PYTHON GAGAL MENGAKSES ROOT [!!!]")
        print("Cek kembali izin Termux di aplikasi Superuser lu.")
        sys.exit(1)

    get_device_profile()

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

    # Pastikan app yang sudah running juga otomatis di-float (tanpa nunggu crash/rejoin).
    apply_float_grid_to_running_targets(target_packages, grid_index_map, grid_total)

    check_count = 0
    while True:
        if should_stop_monitor():
            clear_stop_file()
            print("\n[!] Monitor dihentikan via stop file.")
            os._exit(0)

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
    def _hard_exit(signum, frame):
        # Use os._exit to guarantee termination even if subprocess.run is blocking.
        print("\n[!] Monitor dihentikan.")
        os._exit(0)

    signal.signal(signal.SIGINT, _hard_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _hard_exit)
    if hasattr(signal, "SIGTSTP"):
        signal.signal(signal.SIGTSTP, _hard_exit)
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n[!] Monitor dihentikan user (Ctrl+C).")
        os._exit(0)