#!/data/data/com.termux/files/usr/bin/sh

REPO_URL="https://github.com/xnnnsets/roblox-monitor"
REPO_DIR="$HOME/roblox-monitor"

clear
echo "=========================================="
echo "    INITIALIZING ROBLOX MONITOR"
echo "=========================================="

# ---------- Root check ----------
echo "[*] Mengetes akses Root..."
if ! su -c "id" >/dev/null 2>&1; then
    echo "------------------------------------------"
    echo " [!] ERROR: AKSES ROOT DITOLAK / TIDAK ADA"
    echo " Tolong klik 'GRANT/IZINKAN' pada pop-up"
    echo " Magisk atau KernelSU mase!"
    echo "------------------------------------------"
    exit 1
fi
echo "[v] Akses Root aman."

# ---------- Auto-clone repo if missing ----------
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "[*] Repo tidak ditemukan. Mengkloning dari GitHub..."
    if ! command -v git >/dev/null 2>&1; then
        pkg install git -y
        if [ $? -ne 0 ]; then
            echo "[!] Gagal menginstall git. Periksa koneksi internet."
            exit 1
        fi
    fi
    git clone "$REPO_URL" "$REPO_DIR"
    if [ $? -ne 0 ]; then
        echo "[!] Gagal clone repo. Periksa koneksi internet."
        exit 1
    fi
    echo "[v] Repo berhasil di-clone ke $REPO_DIR"
else
    echo "[v] Repo sudah ada di $REPO_DIR"
fi

# ---------- Install dependencies ----------
echo "[*] Memeriksa & menginstall tools..."
pkg update -y

for tool in python tsu grep procps git; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "    Installing $tool..."
        pkg install "$tool" -y
    else
        echo "    [v] $tool sudah ada"
    fi
done

if ! python -c "import requests" >/dev/null 2>&1; then
    echo "[*] Installing Python requests..."
    pip install requests
else
    echo "    [v] Python requests sudah ada"
fi

# ---------- Launch monitor ----------
echo "=========================================="
echo "[v] Semua siap. Memulai Roblox Monitor..."
echo "=========================================="

cd "$REPO_DIR"
termux-wake-lock
python monitor.py