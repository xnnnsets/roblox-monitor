#!/data/data/com.termux/files/usr/bin/sh

REPO_URL="https://github.com/xnnnsets/roblox-monitor"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/.git" ]; then
    REPO_DIR="$SCRIPT_DIR"
else
    REPO_DIR="$HOME/roblox-monitor"
fi

LANG_CHOICE="id"
AUTO_RUN=0
if [ "$1" = "--autorun" ]; then
    AUTO_RUN=1
fi

print_header() {
    clear
    echo "=========================================="
    echo "      ROBLOX MONITOR CONTROL CENTER"
    echo "=========================================="
}

ensure_repo() {
    if [ -d "$REPO_DIR/.git" ]; then
        return 0
    fi
    echo "[*] Repo not found, cloning..."
    if ! command -v git >/dev/null 2>&1; then
        pkg install git -y || return 1
    fi
    git clone "$REPO_URL" "$REPO_DIR" || return 1
    return 0
}

ensure_deps() {
    echo "[*] Checking dependencies..."
    pkg update -y >/dev/null 2>&1
    for tool in python tsu grep procps git; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            echo "    Installing $tool..."
            pkg install "$tool" -y || return 1
        fi
    done

    if ! python -c "import requests" >/dev/null 2>&1; then
        pip install requests >/dev/null 2>&1 || pip install requests
    fi
    return 0
}

check_root() {
    if ! su -c "id" >/dev/null 2>&1; then
        echo "[!] Root access denied"
        return 1
    fi
    return 0
}

pick_language() {
    print_header
    echo "Pilih Bahasa / Choose Language"
    echo "1. Indonesia"
    echo "2. English"
    printf "Choice : "
    read -r lang_pick
    case "$lang_pick" in
        2) LANG_CHOICE="en" ;;
        *) LANG_CHOICE="id" ;;
    esac
    clear
}

run_setup() {
    cd "$REPO_DIR" || return 1
    python config_wizard.py --mode setup --lang "$LANG_CHOICE"
}

run_edit() {
    cd "$REPO_DIR" || return 1
    python config_wizard.py --mode edit --lang "$LANG_CHOICE"
}

clear_cache_and_kill_targets() {
    cd "$REPO_DIR" || return 1
    targets="$(python config_wizard.py --mode get-target-packages --lang "$LANG_CHOICE")"
    if [ -z "$targets" ]; then
        echo "[!] No target package configured/detected."
        return 0
    fi

    echo "$targets" | while IFS= read -r pkg; do
        [ -z "$pkg" ] && continue
        echo "[*] Cleaning: $pkg"
        su -c "am force-stop $pkg" >/dev/null 2>&1
        su -c "rm -rf /data/data/$pkg/cache/* /data/data/$pkg/code_cache/* 2>/dev/null"
    done
}

run_monitor() {
    check_root || return 1
    cd "$REPO_DIR" || return 1
    clear_cache_and_kill_targets
    command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
    python monitor.py
}

setup_boot_autorun() {
    BOOT_DIR="$HOME/.termux/boot"
    mkdir -p "$BOOT_DIR"
    cat > "$BOOT_DIR/roblox-monitor.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
cd "$REPO_DIR"
./start.sh --autorun
EOF
    chmod +x "$BOOT_DIR/roblox-monitor.sh"
    echo "[v] Boot script created at $BOOT_DIR/roblox-monitor.sh"
    echo "[i] Install Termux:Boot app (F-Droid) and allow auto-start permission."
}

remove_boot_autorun() {
    rm -f "$HOME/.termux/boot/roblox-monitor.sh"
    echo "[v] Boot script removed."
}

misc_menu() {
    while true; do
        echo "------------------------------------------"
        echo "Misc"
        echo "1. Setup auto exec after reboot"
        echo "2. Disable auto exec after reboot"
        echo "3. Update repo (git pull)"
        echo "0. Back"
        printf "> "
        read -r c
        case "$c" in
            1) setup_boot_autorun ;;
            2) remove_boot_autorun ;;
            3) cd "$REPO_DIR" && git pull ;;
            0) break ;;
            *) echo "Invalid choice" ;;
        esac
    done
}

main_menu() {
    while true; do
        print_header
        if [ "$LANG_CHOICE" = "en" ]; then
            echo "1. Setup configuration (First Run Needed)"
            echo "2. Edit config"
            echo "3. Run scripts"
            echo "4. Misc (auto exec after reboot, etc)"
            echo "0. Exit"
        else
            echo "1. Setup configuration (Wajib First Run)"
            echo "2. Edit config"
            echo "3. Run scripts"
            echo "4. Misc (auto exec after reboot, dll)"
            echo "0. Keluar"
        fi
        printf "Choice : "
        read -r choice
        case "$choice" in
            1) run_setup ;;
            2) run_edit ;;
            3) run_monitor ;;
            4) misc_menu ;;
            0) exit 0 ;;
            *) echo "Invalid choice" ;;
        esac
        echo
        if [ "$LANG_CHOICE" = "en" ]; then
            echo "Press Enter..."
        else
            echo "Tekan Enter..."
        fi
        read -r _
    done
}

print_header
ensure_repo || { echo "[!] Failed to prepare repository."; exit 1; }
ensure_deps || { echo "[!] Failed to install dependencies."; exit 1; }

if [ "$AUTO_RUN" -eq 1 ]; then
    run_monitor
    exit $?
fi

pick_language
main_menu