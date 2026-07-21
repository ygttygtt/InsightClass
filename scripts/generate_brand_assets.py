"""Generate deterministic InsightClass desktop and web brand assets.

The source geometry is intentionally kept in code so the Windows ICO, tray
PNG, frontend PNG, favicon, and SVG stay visually identical.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
PUBLIC_DIR = ROOT / "frontend" / "public"
MASTER_SIZE = 1024
ICON_EDGE_LENGTHS = (16, 24, 32, 48, 64, 128, 256)
ICON_SIZES = tuple((edge, edge) for edge in ICON_EDGE_LENGTHS)


def _mix(start: tuple[int, int, int], end: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(left + (right - left) * amount) for left, right in zip(start, end))


def _cubic_points(
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
    steps: int = 80,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control_1[0]
            + 3 * inverse * t**2 * control_2[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control_1[1]
            + 3 * inverse * t**2 * control_2[1]
            + t**3 * end[1]
        )
        points.append((x, y))
    return points


def _build_master() -> Image.Image:
    scale = MASTER_SIZE / 256
    gradient = Image.new("RGBA", (MASTER_SIZE, MASTER_SIZE), (0, 0, 0, 0))
    pixels = gradient.load()
    indigo = (79, 70, 229)
    cyan = (6, 182, 212)
    for y in range(MASTER_SIZE):
        for x in range(MASTER_SIZE):
            amount = min(1.0, max(0.0, (x + y) / (2 * (MASTER_SIZE - 1))))
            red, green, blue = _mix(indigo, cyan, amount)
            pixels[x, y] = (red, green, blue, 255)

    tile_mask = Image.new("L", gradient.size, 0)
    mask_draw = ImageDraw.Draw(tile_mask)
    mask_draw.rounded_rectangle(
        (12 * scale, 12 * scale, 244 * scale, 244 * scale),
        radius=54 * scale,
        fill=255,
    )
    gradient.putalpha(tile_mask)

    output = Image.new("RGBA", gradient.size, (0, 0, 0, 0))
    output.alpha_composite(gradient)
    draw = ImageDraw.Draw(output)

    # A single eye-shaped contour represents observation and analysis. The
    # high-contrast silhouette remains legible at Windows' 16 px size.
    outer_left = (57 * scale, 128 * scale)
    outer_right = (199 * scale, 128 * scale)
    outer = _cubic_points(
        outer_left,
        (92 * scale, 74 * scale),
        (164 * scale, 74 * scale),
        outer_right,
    ) + _cubic_points(
        outer_right,
        (164 * scale, 182 * scale),
        (92 * scale, 182 * scale),
        outer_left,
    )[1:]
    inner_left = (77 * scale, 128 * scale)
    inner_right = (179 * scale, 128 * scale)
    inner = _cubic_points(
        inner_left,
        (103 * scale, 98 * scale),
        (153 * scale, 98 * scale),
        inner_right,
    ) + _cubic_points(
        inner_right,
        (153 * scale, 158 * scale),
        (103 * scale, 158 * scale),
        inner_left,
    )[1:]
    eye_mask = Image.new("L", output.size, 0)
    eye_draw = ImageDraw.Draw(eye_mask)
    eye_draw.polygon(outer, fill=248)
    eye_draw.polygon(inner, fill=0)
    eye_layer = Image.new("RGBA", output.size, (255, 255, 255, 255))
    eye_layer.putalpha(eye_mask)
    output.alpha_composite(eye_layer)

    center_x = center_y = 128 * scale
    draw.ellipse(
        (
            center_x - 25 * scale,
            center_y - 25 * scale,
            center_x + 25 * scale,
            center_y + 25 * scale,
        ),
        fill=(255, 255, 255, 255),
    )
    draw.ellipse(
        (
            center_x - 12 * scale,
            center_y - 12 * scale,
            center_x + 12 * scale,
            center_y + 12 * scale,
        ),
        fill=(30, 41, 89, 255),
    )
    highlight_radius = 3.5 * scale
    highlight_x = center_x - 4 * scale
    highlight_y = center_y - 4 * scale
    draw.ellipse(
        (
            highlight_x - highlight_radius,
            highlight_y - highlight_radius,
            highlight_x + highlight_radius,
            highlight_y + highlight_radius,
        ),
        fill=(255, 255, 255, 240),
    )
    return output


def _write_svg(path: Path) -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-labelledby="title desc">
  <title id="title">InsightClass</title>
  <desc id="desc">以观察之眼代表课堂视觉分析的 InsightClass 标志</desc>
  <defs>
    <linearGradient id="brand-gradient" x1="12" y1="12" x2="244" y2="244" gradientUnits="userSpaceOnUse">
      <stop stop-color="#4f46e5"/>
      <stop offset="1" stop-color="#06b6d4"/>
    </linearGradient>
  </defs>
  <rect x="12" y="12" width="232" height="232" rx="54" fill="url(#brand-gradient)"/>
  <path fill="#fff" fill-rule="evenodd" d="M57 128C92 74 164 74 199 128C164 182 92 182 57 128ZM77 128C103 98 153 98 179 128C153 158 103 158 77 128Z"/>
  <circle cx="128" cy="128" r="25" fill="#fff"/>
  <circle cx="128" cy="128" r="12" fill="#1e2959"/>
  <circle cx="124" cy="124" r="3.5" fill="#fff" fill-opacity=".94"/>
</svg>
"""
    path.write_text(svg, encoding="utf-8", newline="\n")


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    master = _build_master()
    resampling = Image.Resampling.LANCZOS

    svg_path = ASSET_DIR / "insightclass-mark.svg"
    png_path = ASSET_DIR / "insightclass-mark-256.png"
    tray_path = ASSET_DIR / "insightclass-tray.png"
    icon_path = ASSET_DIR / "insightclass.ico"
    _write_svg(svg_path)

    icon_256 = master.resize((256, 256), resampling)
    icon_256.save(png_path, optimize=True)
    master.resize((64, 64), resampling).save(tray_path, optimize=True)
    icon_256.save(icon_path, format="ICO", sizes=ICON_SIZES, bitmap_format="png")

    shutil.copyfile(svg_path, PUBLIC_DIR / "insightclass-mark.svg")
    shutil.copyfile(png_path, PUBLIC_DIR / "insightclass-mark-256.png")
    shutil.copyfile(icon_path, PUBLIC_DIR / "favicon.ico")

    print(f"Generated SVG: {svg_path.relative_to(ROOT)}")
    print(f"Generated PNG: {png_path.relative_to(ROOT)}")
    print(f"Generated tray PNG: {tray_path.relative_to(ROOT)}")
    print(
        f"Generated ICO ({', '.join(map(str, ICON_EDGE_LENGTHS))} px): "
        f"{icon_path.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
