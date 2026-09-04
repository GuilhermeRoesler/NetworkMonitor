"""Gera assets/icon.png e assets/icon.ico do Network Monitor.

Design: fundo escuro + radar teal (paridade com python/ui/favicon.svg).
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent

# Alinhado ao painel (app.css) e favicon.svg
BG = (11, 18, 24)  # #0b1218
ACCENT = (42, 159, 150)  # #2a9f96
ACCENT_BRIGHT = (60, 181, 171)  # #3cb5ab


def _rgba(rgb: tuple[int, int, int], alpha: float) -> tuple[int, int, int, int]:
    a = max(0, min(255, int(round(alpha * 255))))
    return (*rgb, a)


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    size: int,
    radius: float,
    fill: tuple[int, int, int, int],
) -> None:
    r = max(1.0, radius)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=fill)


def draw_icon(size: int) -> Image.Image:
    """Ícone escuro: anéis de radar + setor + hub teal."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Cantos arredondados proporcionais ao SVG (rx=7 em 32 → ~0.22)
    corner = size * (7 / 32)
    draw_rounded_rect(draw, size, corner, (*BG, 255))

    cx = cy = size / 2
    # Escala do SVG: viewBox 32, raios 12.2 / 8.2 / 4.2
    s = size / 32.0

    rings = (
        (12.2, 0.28, 1.2),
        (8.2, 0.42, 1.2),
        (4.2, 0.58, 1.2),
    )

    # Em 16px, só o anel externo + hub (legível na bandeja)
    if size <= 16:
        rings = ((11.0, 0.55, 1.4),)

    for rad, opacity, width in rings:
        ring_r = rad * s
        w = max(1, int(round(width * s)))
        # Pillow outline cresce para dentro/fora; desenhar em camada
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse(
            (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
            outline=_rgba(ACCENT, opacity),
            width=w,
        )
        img = Image.alpha_composite(img, layer)
        draw = ImageDraw.Draw(img)

    outer_r = 12.2 * s
    # Setor SVG: de 12h horário até (10.55, 6.1). Pillow: 0°=3h, positivo=horário.
    if size >= 24:
        wedge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        wd = ImageDraw.Draw(wedge)
        bbox = (cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r)
        wd.pieslice(bbox, start=270, end=30, fill=_rgba(ACCENT, 0.22))
        img = Image.alpha_composite(img, wedge)
        draw = ImageDraw.Draw(img)

        tip_x = cx + 10.55 * s
        tip_y = cy + 6.1 * s
        line_w = max(1, int(round(1.35 * s)))
        draw.line((cx, cy, tip_x, tip_y), fill=_rgba(ACCENT, 0.95), width=line_w)
    else:
        tip_x = cx + 9.5 * s
        tip_y = cy + 5.5 * s
        draw.line(
            (cx, cy, tip_x, tip_y),
            fill=_rgba(ACCENT, 0.9),
            width=max(1, int(round(1.2 * s))),
        )

    hub_r = max(1.2, 1.7 * s)
    draw.ellipse(
        (cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r),
        fill=(*ACCENT_BRIGHT, 255),
    )

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
        # PNG do painel/web: desenhar em 32px (não downscale de 512 — fica borrado na aba).
        draw_icon(32).save(favicon_png, format="PNG")
        # ICO multi-size para fallback; browsers modernos preferem favicon.svg.
        write_ico(favicon_ico, [draw_icon(sz) for sz in (16, 32, 48)])

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
