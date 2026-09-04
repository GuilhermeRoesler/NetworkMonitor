"""
Entrypoint do Network Monitor.

Uso: python main.py [--run|--gui|--scan|...]
A lógica vive no pacote ``nm``.
"""

from __future__ import annotations

import sys

try:
    import pystray  # noqa: F401
    from PIL import Image  # noqa: F401
    from winotify import Notification  # noqa: F401
except ImportError:
    print("Dependência ausente. Execute: pip install -r python/requirements.txt")
    sys.exit(1)

from nm.cli import main

if __name__ == "__main__":
    main()
