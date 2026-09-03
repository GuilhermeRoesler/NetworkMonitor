"""Empacota o Network Monitor com PyInstaller (Windows)."""

from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

APP_NAME = "NetworkMonitor"
ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
ICON_ICO = ASSETS_DIR / "icon.ico"


def build_args() -> list[str]:
    sep = ";" if sys.platform == "win32" else ":"
    args = [
        "main.py",
        "--onedir",
        f"--name={APP_NAME}",
        "--noconfirm",
        "--clean",
        "--hidden-import=gui",
        "--collect-all=winotify",
        "--collect-all=pystray",
        "--collect-all=PIL",
    ]
    if ICON_ICO.is_file():
        args.append(f"--icon={ICON_ICO}")
    if ASSETS_DIR.is_dir():
        args.append(f"--add-data={ASSETS_DIR}{sep}assets")
    if sys.platform == "win32":
        args.append("--windowed")
    return args


def main() -> None:
    print("Iniciando a compilação do Network Monitor (Python)...")
    PyInstaller.__main__.run(build_args())
    print("\nCompilação concluída!")
    if sys.platform == "win32":
        print(f"Executável em: dist/{APP_NAME}/{APP_NAME}.exe")
        print("Copie peers.json para a pasta do .exe se quiser reutilizar a config.")
    else:
        print(f"Executável em: dist/{APP_NAME}/{APP_NAME}")


if __name__ == "__main__":
    main()
