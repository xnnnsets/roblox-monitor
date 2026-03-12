#!/data/data/com.termux/files/usr/bin/sh

# Debug script untuk capture disconnect patterns real-time

PACKAGE="com.roblox.client"
OUTPUT="/home/xnnnsets/roblox_disconnect_log.txt"

echo "[*] Memulai live logcat monitoring untuk disconnect patterns..."
echo "[*] Outputnya akan tersimpan di: $OUTPUT"
echo "[*] Trigger AFK/disconnect sekarang (tunggu 20-25 menit atau lakukan action yang cause disconnect)"
echo ""
echo "=== Live Roblox Logs ===" | tee "$OUTPUT"
echo "Timestamp: $(date)" | tee -a "$OUTPUT"
echo "" | tee -a "$OUTPUT"

# Capture ALL Roblox logs raw tanpa filter
# Nanti kita cari pattern yang muncul saat disconnect
su -c "logcat -v threadtime 2>/dev/null | grep -E 'Roblox|ActivityManager|app_crash|Process.*died' | head -500" | while read line; do
    echo "$line" | tee -a "$OUTPUT"
done

echo ""
echo "[*] Selesai. Check file: $OUTPUT"
echo "[*] Share output file ke GitHub atau folder download"
