# roblox-monitor (beta-2024.06.02)

Roblox monitor script for Termux (rooted Android) to:
- **Auto rejoin** when app crashes/disconnects/dies with instant detection.
- **Detect disconnect/error** patterns from logcat with full coverage (code 273, 277, etc).
- **Manage multiple Roblox packages** (official + clones) with safe handling.
- **Apply auto float/grid** window behavior on A12+ and A10.
- **Auto-run on reboot** via Termux:Boot.

Main runtime is in `main.lua`.
`start.sh` is used as bootstrap/update + dependency installer, then it runs `main.lua`.

---

## 0) Changelog Latest (v2024.06.02)

**Disconnect Detection Improvements:**
- Detect universal disconnect codes: 273, 277, 26x, 27x, and variants
- Pattern coverage: "Sending disconnect", "Disconnection Notification", "Lost connection", timeout/error
- Status check every cycle (instant detection, not N-cycle delay)
- Auto kill + rejoin + cache clear in one operation

**Cache & Resource Improvements:**
- Kill app now includes automatic cache clearing (`/data/data/pkg/cache/*`)
- Cache clearing consistent between startup and error handler

**Boot Autorun Improvements:**
- Setup boot via Termux:Boot (`~/.termux/boot/roblox-monitor.sh`)
- Autorun log written to `~/.termux/boot/roblox-monitor.log`
- Setup is available directly from `Misc` menu

**Safety Improvements:**
- Prevent double-execute with `crashed[pkg]` state flag
- Multi-app rejoin staggered with config delay
- Guard condition in error handler: `if running and not crashed[pkg]`

---

## 1) Requirements

Required before use:
- Android device is **rooted** (`su` works).
- Termux is installed.
- Internet is available.
- At least 1 Roblox package is installed.

Important notes:
- This tool executes root commands (`su -c ...`). If root fails, monitor behavior will not be normal.
- Avoid aggressive battery saver while monitoring.

---

## 2) Step-by-Step Installation (Beginner)

### Step A — First run

Run this in Termux:

```sh
curl -L -o start.sh https://raw.githubusercontent.com/xnnnsets/roblox-monitor/refs/heads/main/start.sh && chmod +x start.sh && ./start.sh
```

Quick explanation:
- `-O start.sh` keeps the file name consistent (prevents `start.sh.1`, `start.sh.2`, etc).
- Script will check/install dependencies (`lua54`, `git`, `curl`, etc).
- After that, it opens the monitor main menu.

### Step B — Daily run (after setup)

```sh
~/roblox-monitor/start.sh
```

---

## 3) How `start.sh` Works

Current behavior:
- If launched from outside repo (`~/roblox-monitor`), script does a fresh clone of latest repo.
- If launched from inside repo, script runs `fetch` then `reset --hard origin/main`.

Meaning:
- Updates are always clean and up to date.
- Manual edits inside repo folder may be overwritten.

Why config stays safe:
- Config is stored at `../config.json` (outside repo folder), so it is not removed during repo refresh.

Typical path example:
- Repo: `~/roblox-monitor`
- Config: `~/config.json`

---

## 4) Main Menu Flow (Safest for New Users)

After script starts:

1. Choose language.
2. Choose **Setup configuration (First Run Needed)**.
3. Follow prompts until config preview appears.
4. Save (`y`).
5. Return to main menu.
6. Choose **Optimize + Launch Apps** to start monitoring.

Main menu options:
- `1. Setup configuration` = quick first-time setup.
- `2. Edit config` = adjust detailed settings anytime.
- `3. Optimize + Launch Apps` = start monitor.
- `4. Misc` = reboot auto-run + repo update.

### 4.5) Hotkeys While Monitoring (NEW)

When monitor is running, you can use these hotkeys:
- `q` = quit script fully.
- `s` or `Ctrl+Z` = stop monitor and return to main menu.
- `p` = pause/resume auto-rejoin (monitor display keeps running).

Note:
- Pause mode only disables auto-rejoin; monitor output still updates.

### 4.6) CLI Modes (NEW)

`main.lua` supports non-interactive modes:

```sh
lua main.lua --mode setup
lua main.lua --mode edit
lua main.lua --mode monitor
lua main.lua --mode get-target-packages
lua main.lua --mode get-cache-packages
lua main.lua --lang en
lua main.lua --autorun
```

Quick meaning:
- `--mode setup` = open quick setup wizard.
- `--mode edit` = open edit config menu directly.
- `--mode monitor` = start monitoring directly.
- `--mode get-target-packages` = print monitor target packages.
- `--mode get-cache-packages` = print cache-clear target packages.
- `--lang id|en` = override language.
- `--autorun` = autorun mode (used by boot script).

---

## 5) `Edit config` Menu Explained

Inside `Edit config`, you now have:
- **View current config**: shows active config values.
- Options to change private server, package targets, cache mode, and more.
- New behavior settings using **yes/no logic**.

### Yes/No Logic (Important)

For `(y/n)` prompts:
- `y` / `yes` / enter on default yes = feature enabled.
- `n` / `no` = feature disabled.

Examples:
- `Launch missing apps immediately on start? (y/n)`
  - `y` = packages that are not running are launched immediately when monitor starts.
  - `n` = no immediate launch; monitor follows normal grace/crash flow.

- `Aggressive username detection? (y/n)`
  - `y` = retries + extra scan sources (stronger detection, slightly heavier).
  - `n` = normal scan only (lighter, but more chance to get `unknown`).

---

## 5.5) Disconnect Detection Explanation (NEW)

Monitor now auto-detects disconnect with comprehensive pattern coverage:

**"Sending disconnect" format:**
```
Sending disconnect with reason: 273 (game joined elsewhere)
Sending disconnect with reason: 277 (server maintenance)
Sending disconnect with reason: 26x (AFK timeout)
```

**"Disconnection Notification" format:**
```
Disconnection Notification. Reason: 273
Disconnection Notification. Reason: 277
```

**"Lost connection" format:**
```
Lost connection with reason : Lost connection to the game server
Connection lost
ID_CONNECTION_LOST
```

**Timeout/Error format:**
```
AckTimeout
Session Transition FSM: Error Occurred
SignalRCoreError.*Disconnected
```

**Behavior when disconnect detected:**
1. Log event with timestamp
2. Force-stop package
3. Auto clear cache
4. Clear logcat buffer
5. Rejoin server
6. Fetch username
7. Resume normal monitoring next cycle

Detection runs **every cycle** (not N-cycle), so response is **instant**.

---

## 6) Full Config Reference + Meaning

Config file location: `../config.json`

### A. Language & Package

- `language`
  - `id` or `en`.
  - Menu language.

- `package_mode`
  - `auto` = auto scan Roblox packages.
  - `manual` = manual package list.

- `manual_packages`
  - Manual Roblox package list.
  - Used when `package_mode = manual`.

- `monitor_selection`
  - `all` = monitor all available packages.
  - `selected` = monitor selected packages only.

- `selected_packages`
  - Target packages used when `monitor_selection = selected`.

### B. Private Server

- `server_mode`
  - `all` = one server code for all packages.
  - `per_package` = different server code per package.

- `server_code`
  - Global/fallback private server code.

- `server_code_by_package`
  - Per-package server code mapping.

### C. Monitoring Interval

- `check_interval`
  - Monitor loop delay in seconds.
  - Lower value = faster response, higher resource usage.

- `log_check_every_cycles`
  - Check logs every N loops.
  - `1` = check every loop (fastest, heavier).

- `startup_grace_seconds`
  - Grace time after join before app is considered crashed/dead.

### D. Cache / AFK / Notifications

- `clear_cache_mode`
  - `all` = clear cache for all Roblox packages.
  - `target` = clear cache for monitor target packages only.

- `afk_timeout_minutes`
  - AFK timeout in minutes.

- `discord_webhook`
  - Optional. Fill this for Discord notifications.

### E. Float / Grid Window Behavior

- `auto_float`
  - `true` = enable freeform/float behavior.
  - `false` = disable float behavior.

- `auto_grid`
  - `true` = enable auto grid resize/position.
  - `false` = disable grid behavior.

- `auto_float_grid`
  - Compatibility derived value (`auto_float && auto_grid`).

- `float_start_delay_seconds`
  - Delay before float step starts.

- `a10_launch_delay_seconds`
  - Extra launch delay for Android 10 flow.

- `multi_launch_delay_seconds`
  - Delay between normal app launches.

- `float_orientation_mode`
  - `system`, `landscape`, or `portrait`.

- `grid_layout_preset`
  - `balanced`, `compact`, `ultra-compact`, `wide`.

### F. Monitor Output

- `monitor_ui_mode`
  - `safe` = compact/stable output.
  - `live` = more detailed snapshot output.

- `package_usernames`
  - Username cache per package to reduce repeated `unknown`.

### G. New Behavior Keys (Yes/No-Based)

- `enable_immediate_launch` (boolean)
  - `true` = immediately launch non-running apps when monitor starts.
  - `false` = skip immediate launch.

- `initial_launch_gap_seconds` (number)
  - Delay between initial launches when immediate launch is enabled.

- `aggressive_username_detection` (boolean)
  - `true` = aggressive mode (retries + extra scanning).
  - `false` = normal mode.

- `username_fetch_delay_seconds` (number)
  - Delay after join before username fetch.
  - Useful when username often appears as `unknown` too early.

Note:
- If these new keys are missing in your existing `config.json`, they will use internal defaults and be written after save.

---

## 7) Safe Starter `config.json` Example

Beginner-friendly baseline (adjust as needed):

```json
{
  "language": "en",
  "package_mode": "auto",
  "monitor_selection": "all",
  "check_interval": 10,
  "server_mode": "all",
  "server_code": "PUT_YOUR_SERVER_CODE_HERE",
  "clear_cache_mode": "target",
  "auto_float": true,
  "auto_grid": true,
  "float_start_delay_seconds": 3,
  "multi_launch_delay_seconds": 30,
  "float_orientation_mode": "system",
  "grid_layout_preset": "compact",
  "monitor_ui_mode": "live",
  "log_check_every_cycles": 3,
  "enable_immediate_launch": true,
  "initial_launch_gap_seconds": 8,
  "aggressive_username_detection": true,
  "username_fetch_delay_seconds": 5
}
```

---

## 8) Boot Autorun Troubleshooting

### Setup Boot Autorun
1. Main menu → `Misc` → `Setup auto exec after reboot`
2. Script creates:
   - `/data/data/com.termux/files/home/.termux/boot/roblox-monitor.sh`
3. Reboot device
4. Monitor runs automatically

### Debug Boot Autorun
**Termux:Boot log:**
```sh
tail -n 120 ~/.termux/boot/roblox-monitor.log
```

### If Boot Doesn't Run
1. Ensure Termux:Boot is installed (Google Play / Aptoide)
2. Open Termux:Boot app once (to register daemon)
3. Run setup boot again
4. Ensure `~/.termux/boot/roblox-monitor.sh` is executable
5. Check the log path above

---

## 9) Quick FAQ

### Q: Why is username still `unknown`?

A:
- Increase `username_fetch_delay_seconds` (for example `8` to `12`).
- Ensure `aggressive_username_detection = true`.
- Let monitor run for several cycles so username cache can fill.

### Q: Why are apps not launching immediately at monitor start?

A:
- Check `enable_immediate_launch` is `true`.
- Check target package selection (auto/manual + all/selected).

### Q: Why does my config survive repo update/re-clone?

A:
- Because config is stored at `../config.json` (outside repo folder).

---

## 10) Super Short Version (For New Users)

If you just want to run fast:
1. Run `./start.sh`.
2. Open `Setup configuration`.
3. Fill server code.
4. Save with `y`.
5. Choose `Optimize + Launch Apps`.

Done. If something feels off, open `Edit config` and use **View current config** to verify active values.