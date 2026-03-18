#!/data/data/com.termux/files/usr/bin/sh

REPO_URL="https://github.com/xnnnsets/roblox-monitor"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/.git" ]; then
    REPO_DIR="$SCRIPT_DIR"
else
    REPO_DIR="$HOME/roblox-monitor"
fi

say() {
    printf "%s\n" "$1"
}

ensure_repo() {
    if ! command -v git >/dev/null 2>&1; then
        clear
        say "[*] Installing git..."
        pkg install git -y || return 1
    fi

    if [ "$REPO_DIR" = "$SCRIPT_DIR" ]; then
        # Running from inside repo — hard-reset to latest commit
        git -C "$REPO_DIR" fetch --quiet origin 2>/dev/null || true
        git -C "$REPO_DIR" reset --hard origin/main 2>/dev/null || true
        return 0
    fi

    # Running from outside repo — always fresh clone for latest code
    # config.json is stored at ../config.json (outside repo) and is safe
    rm -rf "$REPO_DIR" 2>/dev/null || true
    git clone "$REPO_URL" "$REPO_DIR" || return 1
    return 0
}

ensure_deps() {
    clear
    say "[*] Checking dependencies..."
    pkg update -y >/dev/null 2>&1
    for tool in lua54 grep procps git curl; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            clear
            say "[*] Installing $tool..."
            pkg install "$tool" -y || return 1
        fi
    done
    return 0
}

ensure_repo || { say "[!] Failed to prepare repository."; exit 1; }

if [ "$SCRIPT_DIR" != "$REPO_DIR" ] && [ -x "$REPO_DIR/start.sh" ]; then
    exec "$REPO_DIR/start.sh" "$@"
fi

ensure_deps || { say "[!] Failed to install dependencies."; exit 1; }
termux-wake-lock
cd "$REPO_DIR" || exit 1

cleanup() {
    command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock >/dev/null 2>&1 || true
}

stop_monitor() {
    if [ -n "${LUA_PID:-}" ]; then
        kill -TERM "$LUA_PID" 2>/dev/null || true
        pkill -TERM -P "$LUA_PID" 2>/dev/null || true
    fi
    cleanup
    exit 130
}

trap stop_monitor INT TERM HUP QUIT TSTP

lua "$REPO_DIR/main.lua" "$@" &
LUA_PID=$!
wait "$LUA_PID"
STATUS=$?

trap - INT TERM HUP QUIT TSTP
cleanup
exit "$STATUS"