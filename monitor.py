import os
import time
import json
import subprocess
import requests
import sys

# Load Config
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    print("Error: config.json tidak ditemukan!")
    sys.exit(1)

PACKAGE = config["package"]
INTERVAL = config["check_interval"]
WEBHOOK = config["discord_webhook"]
CODE = config["server_code"]

def send_discord(msg):
    if WEBHOOK:
        try: requests.post(WEBHOOK, json={"content": msg}, timeout=5)
        except: pass

def check_root_permission():
    try:
        # Menjalankan command id lewat root
        result = subprocess.run(["su", "-c", "id"], capture_output=True, text=True, timeout=5)
        return "uid=0(root)" in result.stdout
    except:
        return False

def check_game_status():
    cmd = f'su -c "logcat -d -t 200 | grep -Ei \'com.roblox.client|Disconnect|Error Code:|Connection lost|appStopped=true|kick\'"'
    logs = os.popen(cmd).read()
    
    triggers = ["Error Code: 277", "Error Code: 279", "Connection lost", "Disconnected from server", "appStopped=true", "was kicked"]
    
    for trigger in triggers:
        if trigger.lower() in logs.lower():
            return True, trigger
    return False, None

def kill_roblox():
    print("[!] Killing Roblox & Cleaning Logs...")
    os.system(f'su -c "am force-stop {PACKAGE}"')
    os.system('su -c "logcat -c"')

def join_server():
    link = f"roblox://navigation/share_links?code={CODE}&type=Server"
    print(f"[+] Launching: {link}")
    os.system(f'su -c "am start -a android.intent.action.VIEW -d \'{link}\'"')
    
    print("[*] Menunggu game loading untuk auto-tap...")
    time.sleep(20)
    print("[+] Melakukan Auto-Tap agar tidak idle...")
    os.system('su -c "input tap 500 1000"')
    time.sleep(2)
    os.system('su -c "input tap 500 1000"')

def monitor():
    os.system('clear')
    print("==========================================")
    print("   ROBLOX LOG-HUNTER (STABLE ROOT)")
    print("==========================================")
    
    if not check_root_permission():
        print("\n[!!!] ERROR: PYTHON GAGAL MENGAKSES ROOT [!!!]")
        print("Cek kembali izin Termux di aplikasi Superuser lu.")
        sys.exit(1)

    print("[v] Sistem siap. Menghapus log lama...")
    os.system('su -c "logcat -c"')

    while True:
        pid = os.popen(f'su -c "pidof {PACKAGE}"').read().strip()
        is_error, reason = check_game_status()

        if not pid:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ Roblox Crash/Mati")
            send_discord("❌ Roblox Crash! Membuka ulang...")
            kill_roblox()
            join_server()
            
        elif is_error:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Error Detect: {reason}")
            send_discord(f"⚠️ Game Terputus! Alasan: {reason}. Rejoining...")
            kill_roblox()
            join_server()
            
        else:
            print(f"[{time.strftime('%H:%M:%S')}] ✅ Game Running (PID: {pid})", end='\r')

        time.sleep(INTERVAL)

if name == "__main__":
    monitor()