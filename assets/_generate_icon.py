"""Gera assets/icon.png e assets/icon.ico do Network Monitor."""

from __future__ import annotations

import io
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent

TEAL = (11, 110, 143)
BLUE = (0, 120, 212)
WHITE = (255, 255, 255)
GREEN = (26, 127, 55)
RING = (255, 255, 255)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blend(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )


def draw_icon(size: int) -> Image.Image:
    """Ícone: radar + hub + peers; um peer online (verde)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    assert px is not None

    radius = max(2, int(size * 0.22))
    last = max(1, size - 1)
    for y in range(size):
        for x in range(size):
            cx_edge = min(x, size - 1 - x)
            cy_edge = min(y, size - 1 - y)
            if cx_edge < radius and cy_edge < radius:
                dx = radius - cx_edge
                dy = radius - cy_edge
                if dx * dx + dy * dy > radius * radius:
                    continue
            t = (x + y) / (2 * last)
            r, g, b = blend(TEAL, BLUE, t)
            px[x, y] = (r, g, b, 255)

    draw = ImageDraw.Draw(img)
    cx = cy = size / 2
    s = size / 64.0

    def oval(
        x: float,
        y: float,
        r: float,
        *,
        fill: tuple[int, ...] | None = None,
    ) -> None:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    # Em 16px, menos detalhe para manter legível na bandeja
    if size >= 24:
        for rad, alpha, w in ((22, 110, 2), (15, 140, 2)):
            ring_r = rad * s
            ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            rd = ImageDraw.Draw(ring)
            rd.ellipse(
                (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
                outline=(*RING, alpha),
                width=max(1, int(round(w * s))),
            )
            img = Image.alpha_composite(img, ring)
            draw = ImageDraw.Draw(img)

    peer_angles = (math.radians(-30), math.radians(130), math.radians(250))
    peer_r = (20 if size <= 16 else 22) * s
    peers = [
        (cx + peer_r * math.cos(a), cy + peer_r * math.sin(a)) for a in peer_angles
    ]

    line_w = max(1, int(round((1.5 if size <= 16 else 2.2) * s)))
    for x, y in peers:
        draw.line((cx, cy, x, y), fill=(*WHITE, 230), width=line_w)

    hub_r = max(2.0, 5.2 * s)
    oval(cx, cy, hub_r, fill=WHITE)

    online_idx = 0
    for i, (x, y) in enumerate(peers):
        pr = max(1.5, 3.6 * s)
        if i == online_idx:
            if size >= 24:
                oval(x, y, pr + max(1.0, 1.2 * s), fill=WHITE)
                oval(x, y, max(1.5, pr * 0.72), fill=GREEN)
            else:
                oval(x, y, pr, fill=GREEN)
        else:
            oval(x, y, pr, fill=WHITE)

    return img


def write_ico(path: Path, images: list[Image.Image]) -> None:
    """ICO com PNG embutido (Windows Vista+), uma entrada por tamanho."""
    entries: list[tuple[int, int, bytes]] = []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        data = buf.getvalue()
        entries.append((im.width, im.height, data))

    offset = 6 + 16 * len(entries)
    parts = [struct.pack("<HHH", 0, 1, len(entries))]
    payloads: list[bytes] = []
    for width, height, data in entries:
        w = 0 if width >= 256 else width
        h = 0 if height >= 256 else height
        parts.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset))
        payloads.append(data)
        offset += len(data)

    path.write_bytes(b"".join(parts) + b"".join(payloads))


def main() -> None:
    master = draw_icon(512)
    png_path = ASSETS / "icon.png"
    master.resize((256, 256), Image.Resampling.LANCZOS).save(png_path, format="PNG")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_images = [draw_icon(sz) for sz in sizes]
    ico_path = ASSETS / "icon.ico"
    write_ico(ico_path, ico_images)

    ui_dir = ASSETS.parent / "python" / "ui"
    favicon_ico = ui_dir / "favicon.ico"
    favicon_png = ui_dir / "favicon.png"
    if ui_dir.is_dir():
        favicon_ico.write_bytes(ico_path.read_bytes())
        master.resize((32, 32), Image.Resampling.LANCZOS).save(favicon_png, format="PNG")

    # limpa artefato de teste se existir
    for junk in ("icon2.ico",):
        p = ASSETS / junk
        if p.exists():
            p.unlink()

    print(f"Wrote {png_path} ({png_path.stat().st_size} bytes)")
    print(f"Wrote {ico_path} ({ico_path.stat().st_size} bytes)")
    if ui_dir.is_dir():
        print(f"Wrote {favicon_ico} ({favicon_ico.stat().st_size} bytes)")
        print(f"Wrote {favicon_png} ({favicon_png.stat().st_size} bytes)")
    print("ICO sizes:", [im.size for im in ico_images])


if __name__ == "__main__":
    main()
