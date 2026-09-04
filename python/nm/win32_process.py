"""Subprocess oculto no Windows (sem janela de console)."""

from __future__ import annotations

import subprocess
from typing import Any


def hidden_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Como ``subprocess.run``, mas com CREATE_NO_WINDOW + SW_HIDE."""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    flags = int(kwargs.pop("creationflags", 0)) | subprocess.CREATE_NO_WINDOW
    kwargs.pop("startupinfo", None)
    return subprocess.run(
        args,
        startupinfo=startupinfo,
        creationflags=flags,
        **kwargs,
    )
