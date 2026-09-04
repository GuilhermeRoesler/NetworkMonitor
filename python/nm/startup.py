"""Instalação na pasta Startup do Windows."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import winreg
from pathlib import Path

from nm import paths

LEGACY_STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_STARTUP_VALUE = "RadminMonitor"
STARTUP_LINK_NAME = f"{paths.APP_NAME}.lnk"


def get_pythonw() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe)


def startup_folder() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def startup_lnk_path() -> Path:
    return startup_folder() / STARTUP_LINK_NAME


def startup_vbs_path() -> Path:
    return startup_folder() / "RadminMonitor.vbs"


def remove_legacy_startup_registry() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            LEGACY_STARTUP_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, LEGACY_STARTUP_VALUE)
            logging.info("Entrada legada removida do registro Run.")
    except OSError:
        pass


def remove_startup_vbs() -> None:
    vbs_path = startup_vbs_path()
    if vbs_path.exists():
        vbs_path.unlink()
        logging.info("Startup VBS removido: %s", vbs_path)


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_startup_shortcut() -> None:
    lnk_path = startup_lnk_path()
    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable).resolve())
        # Sem flags: bandeja + monitor (não usar --run, que é só console).
        arguments = ""
    else:
        target = get_pythonw()
        main_script = paths.SCRIPT_DIR / "main.py"
        arguments = f'"{main_script}"'
    lnk_path.parent.mkdir(parents=True, exist_ok=True)

    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut({_ps_single_quote(str(lnk_path))}); "
        f"$s.TargetPath = {_ps_single_quote(target)}; "
        f"$s.Arguments = {_ps_single_quote(arguments)}; "
        f"$s.WorkingDirectory = {_ps_single_quote(str(paths.APP_DIR))}; "
        f"$s.Description = {_ps_single_quote(paths.APP_NAME)}; "
        "$s.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Falha ao criar atalho de startup: {result.stderr.strip() or result.stdout.strip()}"
        )


def remove_startup_shortcut() -> None:
    lnk_path = startup_lnk_path()
    if lnk_path.exists():
        lnk_path.unlink()
        logging.info("Atalho de startup removido: %s", lnk_path)


def install_startup() -> None:
    create_startup_shortcut()
    remove_legacy_startup_registry()
    remove_startup_vbs()

    print("Registrado na inicialização do Windows (pasta Startup).")
    print(f"Atalho: {startup_lnk_path()}")
    print("Você também pode abrir shell:startup no Explorer para gerenciar manualmente.")


def uninstall_startup() -> None:
    remove_startup_shortcut()
    remove_legacy_startup_registry()
    remove_startup_vbs()

    print("Removido da inicialização do Windows.")
