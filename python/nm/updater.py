"""Verificação e aplicação de atualizações via GitHub Releases."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from nm.version import get_app_version

GITHUB_OWNER = "GuilhermeRoesler"
GITHUB_REPO = "NetworkMonitor"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
INSTALLER_NAME_RE = re.compile(
    r"^NetworkMonitor-python-installer-win-x64-v(?P<ver>.+)\.exe$",
    re.IGNORECASE,
)
USER_AGENT = "NetworkMonitor-Updater"
HTTP_TIMEOUT_SEC = 12
UPDATE_TIMEOUT_SEC = 10

_lock = threading.Lock()
_status: dict[str, Any] = {
    "checking": False,
    "available": False,
    "current_version": "",
    "latest_version": "",
    "download_url": "",
    "asset_name": "",
    "error": "",
    "applying": False,
}
_check_started = False
_notified_version = ""


def parse_version(raw: str) -> tuple[int, ...]:
    text = (raw or "").strip().lstrip("vV")
    if not text:
        return (0,)
    core = text.split("-", 1)[0].split("+", 1)[0]
    parts: list[int] = []
    for chunk in core.split("."):
        digits = re.match(r"(\d+)", chunk)
        parts.append(int(digits.group(1)) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def find_installer_asset(release: dict[str, Any]) -> dict[str, str] | None:
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        match = INSTALLER_NAME_RE.match(name)
        if not match:
            continue
        url = str(asset.get("browser_download_url") or "").strip()
        if not url:
            continue
        return {
            "name": name,
            "url": url,
            "version": match.group("ver"),
        }
    return None


def _http_get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SEC) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Resposta de release inválida")
    return payload


def snapshot_update_status() -> dict[str, Any]:
    with _lock:
        current = get_app_version()
        data = dict(_status)
        data["current_version"] = data.get("current_version") or current
        return data


def _set_status(**kwargs: Any) -> None:
    with _lock:
        _status.update(kwargs)


def _notify_update_available(latest: str, current: str) -> None:
    """Toast de sistema uma vez por versão detectada nesta sessão."""
    global _notified_version
    with _lock:
        if not latest or _notified_version == latest:
            return
        _notified_version = latest
    try:
        from nm.notify import notify

        notify(
            title="Atualização disponível",
            message=f"Versão {latest} pronta (atual: {current}). Abra o painel para atualizar.",
        )
    except Exception:
        logging.debug("Falha ao notificar atualização disponível", exc_info=True)


def check_for_update(*, force: bool = False) -> dict[str, Any]:
    """Consulta a release mais recente. Seguro para chamar de thread."""
    current = get_app_version()
    with _lock:
        if _status.get("applying"):
            return dict(_status)
        if _status.get("checking") and not force:
            return dict(_status)
        _status["checking"] = True
        _status["error"] = ""
        _status["current_version"] = current

    try:
        release = _http_get_json(RELEASES_LATEST_URL)
        tag = str(release.get("tag_name") or "").strip()
        latest = tag.lstrip("vV")
        asset = find_installer_asset(release)
        if not asset:
            raise LookupError("Nenhum instalador Python encontrado na release")
        asset_ver = asset["version"]
        if latest and parse_version(asset_ver) != parse_version(latest):
            logging.info(
                "Versão do asset (%s) difere da tag (%s); usando a do asset",
                asset_ver,
                latest,
            )
        latest = asset_ver or latest
        available = bool(latest) and is_newer(latest, current)
        _set_status(
            checking=False,
            available=available,
            current_version=current,
            latest_version=latest,
            download_url=asset["url"] if available else "",
            asset_name=asset["name"] if available else "",
            error="",
        )
        if available:
            _notify_update_available(latest, current)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        ValueError,
        LookupError,
    ) as exc:
        logging.info("Verificação de atualização indisponível: %s", exc)
        _set_status(
            checking=False,
            available=False,
            current_version=current,
            latest_version="",
            download_url="",
            asset_name="",
            error=str(exc),
        )
    except Exception:
        logging.exception("Falha inesperada ao verificar atualização")
        _set_status(
            checking=False,
            available=False,
            current_version=current,
            latest_version="",
            download_url="",
            asset_name="",
            error="falha inesperada",
        )
    return snapshot_update_status()


def start_background_check() -> None:
    global _check_started
    with _lock:
        if _check_started:
            return
        _check_started = True
        # Marca checking antes da thread para a UI refletir progresso.
        # A thread precisa de force=True: sem isso check_for_update retorna
        # cedo ao ver checking já True e a consulta ao GitHub nunca roda.
        _status["checking"] = True
        _status["current_version"] = get_app_version()

    thread = threading.Thread(
        target=lambda: check_for_update(force=True),
        name="nm-update-check",
        daemon=True,
    )
    thread.start()


def resolve_apply_update_script() -> Path | None:
    candidates: list[Path] = []
    script_dir = Path(__file__).resolve().parent.parent
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "scripts" / "apply_update.ps1")
        from nm.paths import APP_DIR

        candidates.append(APP_DIR / "scripts" / "apply_update.ps1")
    candidates.append(script_dir / "scripts" / "apply_update.ps1")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _installer_temp_path(asset_name: str) -> Path:
    base = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", asset_name) or "NetworkMonitor-setup.exe"
    return base / "NetworkMonitor" / safe


def _spawn_apply_script(script: Path, url: str, out_file: Path) -> None:
    process_name = ""
    if getattr(sys, "frozen", False):
        process_name = Path(sys.executable).stem

    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script),
        "-Url",
        url,
        "-OutFile",
        str(out_file),
        "-AppPid",
        str(os.getpid()),
        "-TimeoutSec",
        str(UPDATE_TIMEOUT_SEC),
    ]
    if process_name:
        args.extend(["-ProcessName", process_name])

    flags = 0
    if sys.platform == "win32":
        # DETACHED + NEW_PROCESS_GROUP: o script sobrevive ao exit do app.
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )

    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(out_file.parent),
        creationflags=flags,
        close_fds=True,
    )


def begin_update() -> dict[str, Any]:
    """Dispara o script externo de update. Retorna status para a GUI."""
    status = snapshot_update_status()
    if status.get("applying"):
        return {"ok": False, "error": "atualização já em andamento", **status}
    if not status.get("available") or not status.get("download_url"):
        return {"ok": False, "error": "nenhuma atualização disponível", **status}

    script = resolve_apply_update_script()
    if script is None:
        return {"ok": False, "error": "script de atualização não encontrado", **status}

    asset_name = str(status.get("asset_name") or "NetworkMonitor-setup.exe")
    out_file = _installer_temp_path(asset_name)
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        _set_status(applying=True, error="")
        _spawn_apply_script(script, str(status["download_url"]), out_file)
    except Exception as exc:
        logging.exception("Falha ao iniciar atualização")
        _set_status(applying=False, error=str(exc))
        return {"ok": False, "error": str(exc), **snapshot_update_status()}

    # Quit adiado: evita deadlock do WebView (js_api na thread da UI) e libera o
    # instalador. Se o processo travar, o script força o kill após o timeout.
    def _deferred_quit() -> None:
        try:
            from gui import status_window

            status_window.close()
        except Exception:
            logging.debug("Quit adiado do painel falhou", exc_info=True)

    threading.Timer(0.35, _deferred_quit).start()
    return {"ok": True, **snapshot_update_status()}
