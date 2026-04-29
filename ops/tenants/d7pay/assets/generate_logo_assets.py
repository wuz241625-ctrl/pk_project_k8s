#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageOps


ROOT = pathlib.Path(__file__).resolve().parents[4]
ASSET_DIR = ROOT / "ops/tenants/d7pay/assets"
FLUTTER_ROOT = ROOT.parent / "pk_project" / "ashrafi_merchant_flutter"
SOURCE_IMAGE = ASSET_DIR / "d7pay-logo-source-imagegen.png"


def load_source() -> Image.Image:
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"缺少 D7pay 源图: {SOURCE_IMAGE}")
    image = Image.open(SOURCE_IMAGE).convert("RGBA")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


def resize_square(source: Image.Image, size: int) -> Image.Image:
    return source.resize((size, size), Image.Resampling.LANCZOS)


def canvas_logo(source: Image.Image, width: int, height: int, fill: tuple[int, int, int, int]) -> Image.Image:
    canvas = Image.new("RGBA", (width, height), fill)
    icon_size = min(int(width * 0.78), int(height * 0.92))
    icon = resize_square(source, icon_size)
    canvas.alpha_composite(icon, ((width - icon.width) // 2, (height - icon.height) // 2))
    return canvas


def save_png(path: pathlib.Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def save_ico(path: pathlib.Path, source: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    icon = resize_square(source, 256)
    icon.save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> int:
    source = load_source()
    mark_1024 = resize_square(source, 1024)
    full_logo = canvas_logo(source, 1600, 1200, (255, 255, 255, 255))
    wordmark_safe = canvas_logo(source, 900, 260, (255, 255, 255, 0))

    save_png(ASSET_DIR / "d7pay-logo-mark-1024.png", mark_1024)
    save_png(ASSET_DIR / "d7pay-logo-full-1600x1200.png", full_logo)
    save_png(ASSET_DIR / "d7pay-logo-wordmark-900x260.png", wordmark_safe)
    save_ico(ASSET_DIR / "d7pay-favicon.ico", source)

    sidebar_logo = resize_square(source, 128)
    compact_full = canvas_logo(source, 320, 180, (255, 255, 255, 0))
    for repo in [ROOT / "admin-h5", ROOT / "merchant-h5"]:
        save_png(repo / "src/assets/brand/d7pay-logo-mark.png", sidebar_logo)
        save_png(repo / "src/assets/brand/d7pay-logo-full.png", compact_full)
        save_ico(repo / "public/d7pay-favicon.ico", source)

    download_logo = resize_square(source, 192)
    save_png(ROOT / "apkdownload/src/assets/logo/d7pay-logo-192x192.png", download_logo)
    save_png(ROOT / "apkdownload/public/d7pay-logo-192x192.png", download_logo)

    density_sizes = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    if FLUTTER_ROOT.exists():
        for folder, size in density_sizes.items():
            save_png(
                FLUTTER_ROOT / f"android/app/src/main/res/{folder}/ic_launcher_d7pay.png",
                resize_square(source, size),
            )

    print(f"D7pay logo assets generated from {SOURCE_IMAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
