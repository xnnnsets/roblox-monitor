# roblox-monitor

Roblox monitor script for Termux (rooted Android) to:
- Auto rejoin when the app crashes/dies.
- Detect disconnect/error patterns from logcat.
- Manage multiple Roblox packages (official + clones).
- Apply auto float/grid window behavior based on config.

Main runtime is in `main.lua`.
`start.sh` is used as bootstrap/update + dependency installer, then it runs `main.lua`.

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

## 8) Quick FAQ

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

## 9) Super Short Version (For New Users)

If you just want to run fast:
1. Run `./start.sh`.
2. Open `Setup configuration`.
3. Fill server code.
4. Save with `y`.
5. Choose `Optimize + Launch Apps`.

Done. If something feels off, open `Edit config` and use **View current config** to verify active values.