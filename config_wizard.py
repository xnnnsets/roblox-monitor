import argparse
import json
import os
import re
import subprocess
from typing import List

CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "language": "id",
    "package": "",
    "package_mode": "auto",
    "manual_packages": [],
    "monitor_selection": "all",
    "selected_packages": [],
    "check_interval": 10,
    "server_code": "",
    "server_mode": "all",
    "server_code_by_package": {},
    "discord_webhook": "",
    "afk_timeout_minutes": 20,
    "clear_cache_mode": "target",
    "auto_float_grid": True,
    "float_start_delay_seconds": 3,
    "multi_launch_delay_seconds": 30,
    "float_orientation_mode": "system",
}


def tr(lang: str, id_text: str, en_text: str) -> str:
    return id_text if lang == "id" else en_text


def clear_screen() -> None:
    os.system("clear")


def print_section(lang: str, id_title: str, en_title: str) -> None:
    print("\n" + "=" * 54)
    print(tr(lang, id_title, en_title))
    print("=" * 54)


def prompt_menu_choice(lang: str, options: List[str], default: str = "1") -> str:
    while True:
        raw = input(f"{tr(lang, 'Pilihan', 'Choice')} : ").strip()
        if not raw and default:
            raw = default
        if raw in options:
            return raw
        print(tr(lang, "Pilihan tidak valid.", "Invalid choice."))


def normalize_packages(items: List[str]) -> List[str]:
    seen = set()
    normalized = []
    for item in items:
        pkg = (item or "").strip()
        if not pkg:
            continue
        if pkg not in seen:
            seen.add(pkg)
            normalized.append(pkg)
    return normalized


def scan_packages() -> List[str]:
    result = subprocess.run(
        ["sh", "-c", "pm list packages 2>/dev/null | grep -i roblox"],
        capture_output=True,
        text=True,
        timeout=6,
    )
    packages = []
    for line in result.stdout.splitlines():
        pkg = line.replace("package:", "").strip()
        if pkg:
            packages.append(pkg)
    return normalize_packages(packages)


def parse_server_code(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.search(r"[?&]code=([^&#]+)", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-fA-F0-9]{32})\b", text)
    if m:
        return m.group(1)
    return text


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = DEFAULT_CONFIG.copy()
    config.update(data)
    config["manual_packages"] = normalize_packages(config.get("manual_packages", []))
    config["selected_packages"] = normalize_packages(config.get("selected_packages", []))
    if not isinstance(config.get("server_code_by_package"), dict):
        config["server_code_by_package"] = {}
    return config


def save_config(config: dict) -> None:
    config["manual_packages"] = normalize_packages(config.get("manual_packages", []))
    config["selected_packages"] = normalize_packages(config.get("selected_packages", []))
    if not isinstance(config.get("server_code_by_package"), dict):
        config["server_code_by_package"] = {}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def prompt(lang: str, label_id: str, label_en: str, default: str = "") -> str:
    label = tr(lang, label_id, label_en)
    if default != "":
        value = input(f"{label} [{default}]: ").strip()
        return value if value else default
    return input(f"{label}: ").strip()


def prompt_int(lang: str, label_id: str, label_en: str, default: int, min_value: int = 1) -> int:
    while True:
        raw = prompt(lang, label_id, label_en, str(default))
        try:
            value = int(raw)
            if value >= min_value:
                return value
        except ValueError:
            pass
        print(tr(lang, "Input angka tidak valid.", "Invalid number input."))


def prompt_float(lang: str, label_id: str, label_en: str, default: float, min_value: float = 0.1) -> float:
    while True:
        raw = prompt(lang, label_id, label_en, str(default))
        try:
            value = float(raw)
            if value >= min_value:
                return value
        except ValueError:
            pass
        print(tr(lang, "Input angka tidak valid.", "Invalid number input."))


def prompt_bool(lang: str, label_id: str, label_en: str, default: bool) -> bool:
    default_text = "y" if default else "n"
    while True:
        raw = prompt(lang, label_id, label_en, default_text).lower()
        if raw in ("y", "yes", "1"):
            return True
        if raw in ("n", "no", "0"):
            return False
        print(tr(lang, "Pilih y/n.", "Use y/n."))


def resolve_source_packages(config: dict) -> List[str]:
    auto_packages = scan_packages()
    manual_packages = normalize_packages(config.get("manual_packages", []))

    legacy_package = (config.get("package") or "").strip()
    if legacy_package and legacy_package not in manual_packages:
        manual_packages.append(legacy_package)

    mode = config.get("package_mode", "auto")
    if mode == "manual":
        source = manual_packages or auto_packages
    else:
        source = auto_packages or manual_packages
    return normalize_packages(source)


def resolve_target_packages(config: dict) -> List[str]:
    source = resolve_source_packages(config)
    selection = config.get("monitor_selection", "all")
    selected = normalize_packages(config.get("selected_packages", []))

    if selection == "selected" and selected:
        ordered = [pkg for pkg in source if pkg in selected]
        extras = [pkg for pkg in selected if pkg not in ordered]
        target = ordered + extras
        return normalize_packages(target)
    return source


def resolve_cache_packages(config: dict) -> List[str]:
    cache_mode = str(config.get("clear_cache_mode", "target")).lower()
    if cache_mode == "all":
        return resolve_source_packages(config)
    return resolve_target_packages(config)


def configure_server_settings(config: dict, lang: str, available: List[str]) -> None:
    available = normalize_packages(available)
    print_section(lang, "Konfigurasi Private Server", "Private Server Configuration")
    print("1. " + tr(lang, "Satu private server untuk semua package", "One private server for all packages"))
    print("2. " + tr(lang, "Private server berbeda per package", "Different private server per package"))
    default_mode = "1" if str(config.get("server_mode", "all")) == "all" else "2"
    mode = prompt_menu_choice(lang, ["1", "2"], default=default_mode)

    if mode == "1":
        config["server_mode"] = "all"
        raw = prompt(
            lang,
            "Masukkan private server link / game link / server code",
            "Enter private server link / game link / server code",
            config.get("server_code", ""),
        )
        config["server_code"] = parse_server_code(raw)
        return

    config["server_mode"] = "per_package"
    per_map = config.get("server_code_by_package", {})
    if not available:
        print(tr(lang, "Tidak ada package, gunakan server code global.", "No packages available, using global server code."))
    else:
        print(tr(lang, "Isi server code per package (kosong = pakai global)", "Set per-package server code (blank = use global)"))
        for pkg in available:
            value = prompt(
                lang,
                f"{pkg} server link/code",
                f"{pkg} server link/code",
                per_map.get(pkg, ""),
            )
            per_map[pkg] = parse_server_code(value) if value else ""
    config["server_code_by_package"] = per_map
    fallback = prompt(
        lang,
        "Server code global fallback",
        "Global fallback server code",
        config.get("server_code", ""),
    )
    config["server_code"] = parse_server_code(fallback)


def configure_cache_mode(config: dict, lang: str) -> None:
    print_section(lang, "Mode Clear Cache", "Clear Cache Mode")
    print("1. " + tr(lang, "Clear cache semua package Roblox", "Clear cache all Roblox packages"))
    print("2. " + tr(lang, "Clear cache package target monitor", "Clear cache monitor target packages"))
    default_mode = "1" if str(config.get("clear_cache_mode", "target")) == "all" else "2"
    choice = prompt_menu_choice(lang, ["1", "2"], default=default_mode)
    config["clear_cache_mode"] = "all" if choice == "1" else "target"


def configure_float_orientation(config: dict, lang: str) -> None:
    print_section(lang, "Orientasi Float/Grid", "Float/Grid Orientation")
    print("1. " + tr(lang, "Ikuti orientasi sistem", "Follow system orientation"))
    print("2. " + tr(lang, "Paksa landscape semua app", "Force landscape all apps"))
    print("3. " + tr(lang, "Paksa portrait semua app", "Force portrait all apps"))
    mode = str(config.get("float_orientation_mode", "system")).lower()
    default_mode = "1"
    if mode == "landscape":
        default_mode = "2"
    elif mode == "portrait":
        default_mode = "3"
    choice = prompt_menu_choice(lang, ["1", "2", "3"], default=default_mode)
    if choice == "2":
        config["float_orientation_mode"] = "landscape"
    elif choice == "3":
        config["float_orientation_mode"] = "portrait"
    else:
        config["float_orientation_mode"] = "system"


def choose_packages_interactive(lang: str, available: List[str], current_selected: List[str]) -> List[str]:
    if not available:
        print(tr(lang, "Tidak ada package Roblox terdeteksi.", "No Roblox packages detected."))
        return []

    print(tr(lang, "Pilih package (pisahkan koma, contoh: 1,3)", "Choose packages (comma-separated, example: 1,3)"))
    for idx, pkg in enumerate(available, start=1):
        marker = "*" if pkg in current_selected else " "
        print(f" {idx}. [{marker}] {pkg}")

    raw = input(f"{tr(lang, 'Pilihan', 'Choice')} : ").strip()
    if not raw:
        return current_selected

    selected = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
            if 1 <= idx <= len(available):
                selected.append(available[idx - 1])
        except ValueError:
            continue
    return normalize_packages(selected)


def collect_manual_packages(lang: str, existing: List[str]) -> List[str]:
    packages = normalize_packages(existing)
    print(tr(
        lang,
        "Input package satu per baris. Tekan Enter kosong jika selesai.",
        "Input one package per line. Press empty Enter when done.",
    ))
    if packages:
        print(tr(lang, f"Saat ini: {', '.join(packages)}", f"Current: {', '.join(packages)}"))

    while True:
        raw = input(tr(lang, "Paket", "Package") + " : ").strip()
        if not raw:
            break
        additions = normalize_packages(raw.split(","))
        packages = normalize_packages(packages + additions)
        print(tr(lang, f"Ditambahkan: {', '.join(additions)}", f"Added: {', '.join(additions)}"))
    return packages


def configure_monitor_selection(config: dict, lang: str, available: List[str]) -> None:
    available = normalize_packages(available)
    if not available:
        config["monitor_selection"] = "all"
        config["selected_packages"] = []
        print(tr(lang, "Tidak ada package tersedia.", "No packages available."))
        return

    print("\n" + tr(lang, "Pilih target monitor Roblox:", "Choose Roblox monitor targets:"))
    print("1. " + tr(lang, "Buka semua package", "Open all packages"))
    print("2. " + tr(lang, "Pilih package tertentu", "Choose selected packages"))
    mode = prompt_menu_choice(
        lang,
        options=["1", "2"],
        default="1" if config.get("monitor_selection", "all") == "all" else "2",
    )

    if mode == "2":
        config["monitor_selection"] = "selected"
        config["selected_packages"] = choose_packages_interactive(
            lang,
            available,
            config.get("selected_packages", []),
        )
    else:
        config["monitor_selection"] = "all"
        config["selected_packages"] = []


def package_management_menu(config: dict, lang: str) -> None:
    while True:
        clear_screen()
        print("=" * 46)
        print(tr(lang, "Kelola Package", "Package Management"))
        print("=" * 46)
        print(tr(lang, f"Mode sekarang: {config['package_mode']}", f"Current mode: {config['package_mode']}"))
        print(tr(lang, f"Manual list: {', '.join(config['manual_packages']) or '-'}", f"Manual list: {', '.join(config['manual_packages']) or '-'}"))
        print("1. " + tr(lang, "Ubah ke mode AUTO scanner", "Set AUTO scanner mode"))
        print("2. " + tr(lang, "Ubah ke mode MANUAL input", "Set MANUAL mode"))
        print("3. " + tr(lang, "Tambah paket manual", "Add manual package"))
        print("4. " + tr(lang, "Hapus paket manual", "Remove manual package"))
        print("5. " + tr(lang, "Import dari hasil scanner", "Import from scanner result"))
        print("0. " + tr(lang, "Kembali", "Back"))

        choice = prompt_menu_choice(lang, options=["1", "2", "3", "4", "5", "0"], default="0")
        if choice == "1":
            config["package_mode"] = "auto"
            print(tr(lang, "Mode package: AUTO", "Package mode: AUTO"))
        elif choice == "2":
            config["package_mode"] = "manual"
            print(tr(lang, "Mode package: MANUAL", "Package mode: MANUAL"))
        elif choice == "3":
            config["manual_packages"] = collect_manual_packages(lang, config.get("manual_packages", []))
        elif choice == "4":
            manual = config.get("manual_packages", [])
            if not manual:
                print(tr(lang, "List manual kosong.", "Manual list is empty."))
                input(tr(lang, "Tekan Enter...", "Press Enter..."))
                continue
            for idx, pkg in enumerate(manual, start=1):
                print(f" {idx}. {pkg}")
            raw = input(f"{tr(lang, 'Pilihan', 'Choice')} : ").strip()
            try:
                idx = int(raw)
                if 1 <= idx <= len(manual):
                    removed = manual.pop(idx - 1)
                    print(tr(lang, f"Dihapus: {removed}", f"Removed: {removed}"))
            except ValueError:
                print(tr(lang, "Input invalid.", "Invalid input."))
        elif choice == "5":
            scanned = scan_packages()
            if not scanned:
                print(tr(lang, "Tidak ada package terdeteksi.", "No package detected."))
                continue
            print(tr(lang, "Package hasil scanner:", "Scanned packages:"))
            for idx, pkg in enumerate(scanned, start=1):
                print(f" {idx}. {pkg}")
            raw = input(tr(lang, "Pilih nomor (contoh 1,2) atau ketik all", "Choose numbers (example 1,2) or type all") + ": ").strip().lower()
            to_add = []
            if raw == "all":
                to_add = scanned
            else:
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        idx = int(part)
                        if 1 <= idx <= len(scanned):
                            to_add.append(scanned[idx - 1])
                    except ValueError:
                        continue
            config["manual_packages"] = normalize_packages(config.get("manual_packages", []) + to_add)
            print(tr(lang, "Manual list diperbarui.", "Manual list updated."))
        elif choice == "0":
            break

        input(tr(lang, "Tekan Enter...", "Press Enter..."))


def quick_setup(config: dict, lang: str) -> dict:
    clear_screen()
    print_section(lang, "SETUP CONFIGURATION (WAJIB FIRST RUN)", "SETUP CONFIGURATION (FIRST RUN REQUIRED)")

    print_section(lang, "Sumber Package Roblox", "Roblox Package Source")
    print("1. " + tr(lang, "Auto scanner package app Roblox", "Auto scanner Roblox app package"))
    print("2. " + tr(lang, "Manual input app Roblox package", "Manual input Roblox app package"))
    mode_choice = prompt_menu_choice(
        lang,
        options=["1", "2"],
        default="1" if config.get("package_mode", "auto") == "auto" else "2",
    )

    if mode_choice == "2":
        config["package_mode"] = "manual"
        config["manual_packages"] = collect_manual_packages(lang, config.get("manual_packages", []))
        available = normalize_packages(config.get("manual_packages", []))
    else:
        config["package_mode"] = "auto"
        scanned = scan_packages()
        if not scanned:
            print(tr(
                lang,
                "Auto scanner tidak menemukan package. Beralih ke manual input.",
                "Auto scanner found no packages. Switching to manual input.",
            ))
            config["package_mode"] = "manual"
            config["manual_packages"] = collect_manual_packages(lang, config.get("manual_packages", []))
            available = normalize_packages(config.get("manual_packages", []))
        else:
            available = scanned
            print("\n" + tr(lang, "Hasil auto scanner:", "Auto scanner result:"))
            for idx, pkg in enumerate(available, start=1):
                print(f" {idx}. {pkg}")

    configure_monitor_selection(config, lang, available)
    configure_server_settings(config, lang, available)
    configure_cache_mode(config, lang)

    print_section(lang, "Konfigurasi Lainnya", "Other Configuration")
    config["discord_webhook"] = prompt(
        lang,
        "Discord webhook (opsional, kosongkan jika tidak pakai)",
        "Discord webhook (optional, leave blank if unused)",
        config.get("discord_webhook", ""),
    )
    config["check_interval"] = prompt_int(lang, "Check interval (detik)", "Check interval (seconds)", int(config.get("check_interval", 10)))
    config["afk_timeout_minutes"] = prompt_float(
        lang,
        "AFK timeout (menit)",
        "AFK timeout (minutes)",
        float(config.get("afk_timeout_minutes", 20)),
    )
    config["auto_float_grid"] = prompt_bool(
        lang,
        "Auto float grid? (y/n)",
        "Auto float grid? (y/n)",
        bool(config.get("auto_float_grid", True)),
    )
    config["float_start_delay_seconds"] = prompt_int(
        lang,
        "Float start delay (detik)",
        "Float start delay (seconds)",
        int(config.get("float_start_delay_seconds", 3)),
        0,
    )
    config["multi_launch_delay_seconds"] = prompt_int(
        lang,
        "Jeda buka antar app (detik)",
        "Delay between app launches (seconds)",
        int(config.get("multi_launch_delay_seconds", 30)),
        0,
    )
    configure_float_orientation(config, lang)

    return config


def edit_config(config: dict, lang: str) -> dict:
    while True:
        clear_screen()
        print("=" * 50)
        print(tr(lang, "EDIT CONFIG", "EDIT CONFIG"))
        print("=" * 50)
        print("1. " + tr(lang, "Private server (all/per package)", "Private server (all/per package)"))
        print("2. " + tr(lang, "Kelola package (auto/manual, tambah/hapus)", "Manage packages (auto/manual, add/remove)"))
        print("3. " + tr(lang, "Pilih package monitor (all/selected)", "Choose monitor targets (all/selected)"))
        print("4. " + tr(lang, "Mode clear cache (all/target)", "Clear cache mode (all/target)"))
        print("5. " + tr(lang, "Discord webhook", "Discord webhook"))
        print("6. " + tr(lang, "Check interval", "Check interval"))
        print("7. " + tr(lang, "AFK timeout", "AFK timeout"))
        print("8. " + tr(lang, "Auto float grid", "Auto float grid"))
        print("9. " + tr(lang, "Float start delay", "Float start delay"))
        print("10. " + tr(lang, "Jeda buka antar app", "Delay between app launches"))
        print("11. " + tr(lang, "Orientasi float/grid", "Float/grid orientation"))
        print("12. " + tr(lang, "Simpan dan keluar", "Save and exit"))
        print("0. " + tr(lang, "Batal", "Cancel"))

        choice = prompt_menu_choice(lang, options=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "0"], default="0")
        if choice == "1":
            available = resolve_source_packages(config)
            configure_server_settings(config, lang, available)
        elif choice == "2":
            package_management_menu(config, lang)
        elif choice == "3":
            available = resolve_source_packages(config)
            configure_monitor_selection(config, lang, available)
        elif choice == "4":
            configure_cache_mode(config, lang)
        elif choice == "5":
            config["discord_webhook"] = prompt(
                lang,
                "Discord webhook",
                "Discord webhook",
                config.get("discord_webhook", ""),
            )
        elif choice == "6":
            config["check_interval"] = prompt_int(
                lang,
                "Check interval (detik)",
                "Check interval (seconds)",
                int(config.get("check_interval", 10)),
            )
        elif choice == "7":
            config["afk_timeout_minutes"] = prompt_float(
                lang,
                "AFK timeout (menit)",
                "AFK timeout (minutes)",
                float(config.get("afk_timeout_minutes", 20)),
            )
        elif choice == "8":
            config["auto_float_grid"] = prompt_bool(
                lang,
                "Auto float grid? (y/n)",
                "Auto float grid? (y/n)",
                bool(config.get("auto_float_grid", True)),
            )
        elif choice == "9":
            config["float_start_delay_seconds"] = prompt_int(
                lang,
                "Float start delay (detik)",
                "Float start delay (seconds)",
                int(config.get("float_start_delay_seconds", 3)),
                0,
            )
        elif choice == "10":
            config["multi_launch_delay_seconds"] = prompt_int(
                lang,
                "Jeda buka antar app (detik)",
                "Delay between app launches (seconds)",
                int(config.get("multi_launch_delay_seconds", 30)),
                0,
            )
        elif choice == "11":
            configure_float_orientation(config, lang)
        elif choice == "12":
            save_config(config)
            print(tr(lang, "Config tersimpan.", "Config saved."))
            return config
        elif choice == "0":
            print(tr(lang, "Edit dibatalkan.", "Edit cancelled."))
            return config

        input(tr(lang, "Tekan Enter...", "Press Enter..."))


def do_get_target_packages() -> None:
    config = load_config()
    for pkg in resolve_target_packages(config):
        print(pkg)


def do_get_cache_packages() -> None:
    config = load_config()
    for pkg in resolve_cache_packages(config):
        print(pkg)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["setup", "edit", "get-target-packages", "get-cache-packages"], required=True)
    parser.add_argument("--lang", choices=["id", "en"], default="id")
    args = parser.parse_args()

    if args.mode == "get-target-packages":
        do_get_target_packages()
        return
    if args.mode == "get-cache-packages":
        do_get_cache_packages()
        return

    config = load_config()
    config["language"] = args.lang

    if args.mode == "setup":
        config = quick_setup(config, args.lang)
        save_config(config)
        print(tr(args.lang, "Setup selesai & config tersimpan.", "Setup complete & config saved."))
        return

    if args.mode == "edit":
        edit_config(config, args.lang)


if __name__ == "__main__":
    main()
