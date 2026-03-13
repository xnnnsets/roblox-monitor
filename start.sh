#!/data/data/com.termux/files/usr/bin/sh

REPO_URL="https://github.com/xnnnsets/roblox-monitor"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_BACKUP="$HOME/.roblox-monitor-config.backup.json"
CONFIG_BACKUP_LAST="$HOME/.roblox-monitor-config.last.json"

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

t() {
    if [ "$LANG_CHOICE" = "en" ]; then
        printf "%s" "$2"
    else
        printf "%s" "$1"
    fi
}

say() {
    printf "%s\n" "$(t "$1" "$2")"
}

load_saved_language() {
    if [ -f "$REPO_DIR/config.json" ]; then
        saved_lang="$(grep -o '"language"[[:space:]]*:[[:space:]]*"[a-z][a-z]"' "$REPO_DIR/config.json" 2>/dev/null | head -1 | sed 's/.*"\([a-z][a-z]\)"/\1/')"
        case "$saved_lang" in
            en|id) LANG_CHOICE="$saved_lang" ;;
        esac
    fi
}

print_header() {
    clear
    echo "=========================================="
    if [ "$LANG_CHOICE" = "en" ]; then
        echo "      ROBLOX MONITOR CONTROL CENTER"
    else
        echo "      PUSAT KONTROL ROBLOX MONITOR"
    fi
    echo "=========================================="
}

backup_config() {
    rm -f "$CONFIG_BACKUP"
    if [ -f "$REPO_DIR/config.json" ]; then
        cp "$REPO_DIR/config.json" "$CONFIG_BACKUP" 2>/dev/null
        cp "$REPO_DIR/config.json" "$CONFIG_BACKUP_LAST" 2>/dev/null
        return 0
    fi
    if [ -f "$SCRIPT_DIR/config.json" ]; then
        cp "$SCRIPT_DIR/config.json" "$CONFIG_BACKUP" 2>/dev/null
        cp "$SCRIPT_DIR/config.json" "$CONFIG_BACKUP_LAST" 2>/dev/null
        return 0
    fi
    return 1
}

restore_config() {
    if [ -f "$CONFIG_BACKUP" ]; then
        cp "$CONFIG_BACKUP" "$REPO_DIR/config.json" 2>/dev/null
        rm -f "$CONFIG_BACKUP"
        say "[v] Config lama berhasil dipulihkan." "[v] Previous config restored successfully."
    fi
}

ensure_repo() {
    if ! command -v git >/dev/null 2>&1; then
        say "[*] Git belum ada, menginstall..." "[*] Git not found, installing..."
        pkg install git -y || return 1
    fi

    backup_config >/dev/null 2>&1 && say "[*] Backup config ditemukan ($CONFIG_BACKUP_LAST)." "[*] Config backup found ($CONFIG_BACKUP_LAST)."

    if [ -d "$REPO_DIR/.git" ] && [ "$REPO_DIR" = "$SCRIPT_DIR" ]; then
        say "[*] Repo aktif terdeteksi, refresh dengan git..." "[*] Active repo detected, refreshing with git..."
        cd "$REPO_DIR" || return 1
        git fetch --all || return 1
        git reset --hard origin/main || return 1
        git clean -fd || return 1
    else
        if [ -d "$REPO_DIR" ]; then
            say "[*] Repo lama terdeteksi, hapus dan clone ulang..." "[*] Old repo detected, removing and re-cloning..."
            rm -rf "$REPO_DIR" || return 1
        else
            say "[*] Repo tidak ditemukan, cloning..." "[*] Repo not found, cloning..."
        fi
        git clone "$REPO_URL" "$REPO_DIR" || return 1
    fi

    restore_config

    return 0
}

ensure_deps() {
    say "[*] Memeriksa dependencies..." "[*] Checking dependencies..."
    pkg update -y >/dev/null 2>&1
    for tool in python tsu grep procps git; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            printf "    %s\n" "$(t "Menginstall $tool..." "Installing $tool...")"
            pkg install "$tool" -y || return 1
        fi
    done

    if ! python -c "import requests" >/dev/null 2>&1; then
        say "[*] Menginstall Python requests..." "[*] Installing Python requests..."
        pip install requests >/dev/null 2>&1 || pip install requests
    fi
    return 0
}

check_root() {
    if ! su -c "id" >/dev/null 2>&1; then
        say "[!] Akses root ditolak" "[!] Root access denied"
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
    targets="$(python config_wizard.py --mode get-cache-packages --lang "$LANG_CHOICE")"
    if [ -z "$targets" ]; then
        say "[!] Tidak ada package target yang terkonfigurasi/terdeteksi." "[!] No target package configured/detected."
        return 0
    fi

    echo "$targets" | while IFS= read -r pkg; do
        [ -z "$pkg" ] && continue
        printf "[*] %s: %s\n" "$(t "Membersihkan" "Cleaning")" "$pkg"
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
    say "[v] Boot script dibuat di $BOOT_DIR/roblox-monitor.sh" "[v] Boot script created at $BOOT_DIR/roblox-monitor.sh"
    say "[i] Install aplikasi Termux:Boot (F-Droid) dan beri izin auto-start." "[i] Install Termux:Boot app (F-Droid) and allow auto-start permission."
}

remove_boot_autorun() {
    rm -f "$HOME/.termux/boot/roblox-monitor.sh"
    say "[v] Boot script dihapus." "[v] Boot script removed."
}

misc_menu() {
    while true; do
        print_header
        echo "------------------------------------------"
        echo "$(t "Lainnya" "Misc")"
        echo "1. $(t "Setup auto jalan setelah reboot" "Setup auto exec after reboot")"
        echo "2. $(t "Nonaktifkan auto jalan setelah reboot" "Disable auto exec after reboot")"
        echo "3. $(t "Update repo (git pull)" "Update repo (git pull)")"
        echo "0. $(t "Kembali" "Back")"
        printf "Choice : "
        read -r c
        case "$c" in
            1) setup_boot_autorun ;;
            2) remove_boot_autorun ;;
            3) cd "$REPO_DIR" && git pull ;;
            0) break ;;
            *) say "Pilihan tidak valid" "Invalid choice" ;;
        esac
        echo
        say "Tekan Enter..." "Press Enter..."
        read -r _
    done
}

main_menu() {
    while true; do
        print_header
        if [ "$LANG_CHOICE" = "en" ]; then
            echo "1. Setup configuration (First Run Needed)"
            echo "2. Edit config"
            echo "3. Optimize + Launch Apps"
            echo "4. Misc (auto exec after reboot, etc)"
            echo "0. Exit"
        else
            echo "1. Setup configuration (Wajib First Run)"
            echo "2. Ubah konfigurasi"
            echo "3. Optimalkan + Buka Aplikasi"
            echo "4. Lainnya (auto exec setelah reboot, dll)"
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
            *) say "Pilihan tidak valid" "Invalid choice" ;;
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

if [ "$AUTO_RUN" -eq 1 ]; then
    load_saved_language
    print_header
    ensure_repo || { say "[!] Gagal menyiapkan repository." "[!] Failed to prepare repository."; exit 1; }
    load_saved_language
    ensure_deps || { say "[!] Gagal menginstall dependencies." "[!] Failed to install dependencies."; exit 1; }
    run_monitor
    exit $?
fi

pick_language
print_header
ensure_repo || { say "[!] Gagal menyiapkan repository." "[!] Failed to prepare repository."; exit 1; }

# Jika dijalankan dari luar repo (bootstrap), serahkan kontrol ke start.sh di repo
# supaya selalu pakai versi terbaru dan tidak ada file start.sh ganda.
if [ "$SCRIPT_DIR" != "$REPO_DIR" ] && [ -x "$REPO_DIR/start.sh" ]; then
    say "[v] Meneruskan ke versi terbaru di repo..." "[v] Handing off to latest version in repo..."
    say "[i] Untuk selanjutnya jalankan: $REPO_DIR/start.sh" "[i] Next time run directly: $REPO_DIR/start.sh"
    exec "$REPO_DIR/start.sh"
fi

ensure_deps || { say "[!] Gagal menginstall dependencies." "[!] Failed to install dependencies."; exit 1; }
main_menu