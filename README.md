# roblox-monitor
Termux android, Rooted auto rejoin if crash or disconnect

## Quick Start

**Bootstrap (pertama kali / first time):**
```sh
wget -O start.sh https://raw.githubusercontent.com/xnnnsets/roblox-monitor/refs/heads/main/start.sh && chmod +x start.sh && ./start.sh
```
> `-O start.sh` memastikan file tidak jadi ganda (`start.sh.1`) jika sudah ada sebelumnya.

**Selanjutnya (after first run):**
```sh
~/roblox-monitor/start.sh
```
Script akan otomatis update repo saat dijalankan.

Menu flow:
- Choose language (Indonesia / English)
- `Setup configuration (First Run Needed)`
- `Edit config`
- `Run scripts` (auto kill + clear cache target Roblox apps before monitor starts)
- `Misc` (auto-run after reboot, repo update)
