# roblox-monitor

Script monitor Roblox di Termux (Android root) untuk:
- Auto rejoin saat app crash/mati.
- Cek error/disconnect dari logcat.
- Kelola multi package Roblox (official + clone).
- Auto float/grid window (sesuai setting).

Runtime utama ada di `main.lua`.
`start.sh` dipakai sebagai bootstrap/update + instal dependensi, lalu menjalankan `main.lua`.

---

## 1) Syarat Wajib

Wajib sebelum pakai:
- Android **sudah root** (`su` berfungsi).
- Termux terpasang.
- Internet aktif.
- Minimal ada 1 package Roblox terpasang.

Catatan penting:
- Tool ini menjalankan perintah root (`su -c ...`). Kalau root gagal, monitor tidak akan berjalan normal.
- Hindari battery saver agresif saat monitoring.

---

## 2) Instalasi Step-by-Step (Pemula)

### Langkah A — Pertama kali

Jalankan ini di Termux:

```sh
curl -L -o start.sh https://raw.githubusercontent.com/xnnnsets/roblox-monitor/refs/heads/main/start.sh && chmod +x start.sh && ./start.sh
```

Penjelasan singkat:
- `-O start.sh` menjaga nama file tetap konsisten (tidak jadi `start.sh.1`, `start.sh.2`, dll).
- Script akan cek/install dependensi (`lua54`, `git`, `curl`, dll).
- Setelah itu, menu utama monitor akan terbuka.

### Langkah B — Jalankan harian (setelah setup)

```sh
~/roblox-monitor/start.sh
```

---

## 3) Cara Kerja `start.sh`

Perilaku saat ini:
- Jika dijalankan dari luar repo (`~/roblox-monitor`), script akan fresh clone repo terbaru.
- Jika dijalankan dari dalam repo, script akan `fetch` lalu `reset --hard origin/main`.

Artinya:
- Update selalu bersih dan terbaru.
- Edit manual di folder repo bisa tertimpa.

Kenapa config aman?
- Config disimpan di `../config.json` (di luar folder repo), jadi tidak ikut terhapus saat repo di-refresh.

Contoh path umum:
- Repo: `~/roblox-monitor`
- Config: `~/config.json`

---

## 4) Alur Menu Utama (Paling Aman untuk User Baru)

Setelah script berjalan:

1. Pilih bahasa.
2. Pilih **Setup configuration (Wajib First Run)**.
3. Ikuti prompt sampai preview config muncul.
4. Simpan (`y`).
5. Kembali ke menu utama.
6. Pilih **Optimalkan + Buka Aplikasi** untuk mulai monitoring.

Menu utama:
- `1. Setup configuration` = setup cepat awal.
- `2. Edit config` = ubah setting detail kapan saja.
- `3. Optimize + Launch Apps` = mulai monitor.
- `4. Misc` = auto-run setelah reboot + update repo.

---

## 5) Penjelasan Menu `Edit config`

Di `Edit config`, sekarang ada:
- **View current config / Lihat config sekarang**: menampilkan nilai config aktif.
- Opsi ubah private server, target package, mode cache, dan lainnya.
- Opsi behavior baru dengan **logika yes/no**.

### Logika Yes/No (Penting)

Untuk prompt `(y/n)`:
- `y` / `yes` / enter saat default yes = fitur aktif.
- `n` / `no` = fitur nonaktif.

Contoh:
- `Launch missing apps immediately on start? (y/n)`
  - `y` = package yang belum jalan langsung di-launch saat monitor mulai.
  - `n` = tidak launch langsung; monitor mengikuti alur normal grace/crash.

- `Aggressive username detection? (y/n)`
  - `y` = retry + sumber scan tambahan (lebih kuat, sedikit lebih berat).
  - `n` = scan normal saja (lebih ringan, tapi peluang `unknown` lebih besar).

---

## 6) Referensi Lengkap Konfigurasi + Artinya

Lokasi file config: `../config.json`

### A. Bahasa & Package

- `language`
  - `id` atau `en`.
  - Bahasa menu.

- `package_mode`
  - `auto` = scan package Roblox otomatis.
  - `manual` = daftar package manual.

- `manual_packages`
  - Daftar package Roblox manual.
  - Dipakai saat `package_mode = manual`.

- `monitor_selection`
  - `all` = monitor semua package yang tersedia.
  - `selected` = monitor package terpilih saja.

- `selected_packages`
  - Daftar package target saat `monitor_selection = selected`.

### B. Private Server

- `server_mode`
  - `all` = satu server code untuk semua package.
  - `per_package` = server code berbeda per package.

- `server_code`
  - Private server code global/fallback.

- `server_code_by_package`
  - Mapping server code per package.

### C. Interval Monitoring

- `check_interval`
  - Jeda loop monitor (detik).
  - Nilai lebih kecil = respon lebih cepat, resource lebih tinggi.

- `log_check_every_cycles`
  - Cek log setiap N loop.
  - `1` = cek setiap loop (paling cepat, lebih berat).

- `startup_grace_seconds`
  - Waktu toleransi setelah join sebelum app dianggap crash/mati.

### D. Cache / AFK / Notifikasi

- `clear_cache_mode`
  - `all` = clear cache semua package Roblox.
  - `target` = clear cache hanya package target monitor.

- `afk_timeout_minutes`
  - Timeout AFK dalam menit.

- `discord_webhook`
  - Opsional. Isi untuk notifikasi Discord.

### E. Float / Grid Window Behavior

- `auto_float`
  - `true` = aktifkan freeform/float behavior.
  - `false` = nonaktifkan float behavior.

- `auto_grid`
  - `true` = aktifkan auto grid resize/position.
  - `false` = nonaktifkan grid behavior.

- `auto_float_grid`
  - Nilai turunan kompatibilitas (`auto_float && auto_grid`).

- `float_start_delay_seconds`
  - Delay sebelum langkah float dimulai.

- `a10_launch_delay_seconds`
  - Delay launch tambahan untuk alur Android 10.

- `multi_launch_delay_seconds`
  - Jeda antar launch app normal.

- `float_orientation_mode`
  - `system`, `landscape`, atau `portrait`.

- `grid_layout_preset`
  - `balanced`, `compact`, `ultra-compact`, `wide`.

### F. Output Monitor

- `monitor_ui_mode`
  - `safe` = output ringkas/stabil.
  - `live` = output snapshot lebih detail.

- `package_usernames`
  - Cache username per package untuk mengurangi `unknown` berulang.

### G. Key Behavior Baru (Berbasis Yes/No)

- `enable_immediate_launch` (boolean)
  - `true` = langsung launch app yang tidak berjalan saat monitor mulai.
  - `false` = lewati immediate launch.

- `initial_launch_gap_seconds` (number)
  - Jeda antar initial launch saat immediate launch aktif.

- `aggressive_username_detection` (boolean)
  - `true` = mode agresif (retry + scan tambahan).
  - `false` = mode normal.

- `username_fetch_delay_seconds` (number)
  - Delay setelah join sebelum fetch username.
  - Berguna saat username sering terbaca `unknown` terlalu awal.

Catatan:
- Jika key baru ini belum ada di `config.json` lama, sistem pakai default internal dan akan ditulis saat save.

---

## 7) Contoh `config.json` Aman untuk Pemula

Baseline pemula (silakan sesuaikan):

```json
{
  "language": "id",
  "package_mode": "auto",
  "monitor_selection": "all",
  "check_interval": 10,
  "server_mode": "all",
  "server_code": "ISI_SERVER_CODE_KAMU",
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

## 8) FAQ Singkat

### Q: Kenapa username masih `unknown`?

A:
- Naikkan `username_fetch_delay_seconds` (contoh `8` sampai `12`).
- Pastikan `aggressive_username_detection = true`.
- Biarkan monitor berjalan beberapa siklus agar cache username terisi.

### Q: Kenapa app tidak langsung launch saat monitor start?

A:
- Cek `enable_immediate_launch` bernilai `true`.
- Cek pemilihan package target (auto/manual + all/selected).

### Q: Kenapa config tetap ada walau repo di-update/re-clone?

A:
- Karena config disimpan di `../config.json` (di luar folder repo).

---

## 9) Versi Super Singkat (User Baru)

Kalau mau cepat:
1. Jalankan `./start.sh`.
2. Buka `Setup configuration`.
3. Isi server code.
4. Simpan dengan `y`.
5. Pilih `Optimize + Launch Apps`.

Selesai. Kalau ada yang terasa tidak pas, buka `Edit config` lalu pakai **View current config** untuk cek nilai aktif.
