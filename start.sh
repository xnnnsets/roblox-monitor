#!/data/data/com.termux/files/usr/bin/bash

echo "=========================================="
echo "    INITIALIZING ROBLOX MONITOR"
echo "=========================================="

echo "[*] Mengetes akses Root..."
if ! su -c "id" &> /dev/null; then
    echo "------------------------------------------"
    echo " [!] ERROR: AKSES ROOT DITOLAK / TIDAK ADA"
    echo " Tolong klik 'GRANT/IZINKAN' pada pop-up"
    echo " Magisk atau KernelSU mase!"
    echo "------------------------------------------"
    exit 1
else
    echo "[v] Akses Root aman."
fi

echo "[*] Memeriksa tools..."
pkg update -y
dependencies=("python" "tsu" "grep" "procps")

for tool in "${dependencies[@]}"; do
    if ! command -v $tool &> /dev/null; then
        pkg install $tool -y
    fi
done

if ! python -c "import requests" &> /dev/null; then
    pip install requests
fi

cd ~/roblox-monitor
termux-wake-lock
python monitor.py