#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys

from PIL import Image


ROOT = pathlib.Path(__file__).resolve().parents[4]
ASSET_DIR = ROOT / "ops/tenants/d7pay/assets"
FLUTTER_ROOT = ROOT.parent / "pk_project" / "ashrafi_merchant_flutter"


SOURCE_FILES = {
    "app_1024": "d7pay-logo-source-app-1024.png",
    "app_192": "d7pay-logo-source-app-192.png",
    "app_144": "d7pay-logo-source-app-144.png",
    "app_96": "d7pay-logo-source-app-96.png",
    "app_72": "d7pay-logo-source-app-72.png",
    "app_48": "d7pay-logo-source-app-48.png",
    "sidebar_128": "d7pay-logo-source-sidebar-128.png",
    "download_192": "d7pay-logo-source-download-192.png",
    "favicon_256": "d7pay-logo-source-favicon-256.png",
    "favicon_64": "d7pay-logo-source-favicon-64.png",
    "favicon_48": "d7pay-logo-source-favicon-48.png",
    "favicon_32": "d7pay-logo-source-favicon-32.png",
    "favicon_16": "d7pay-logo-source-favicon-16.png",
}


def source(name: str) -> Image.Image:
    path = ASSET_DIR / SOURCE_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"缺少 D7pay image_gen 源图: {path}")
    return Image.open(path).convert("RGBA")


def exact(image: Image.Image, width: int, height: int, fill: tuple[int, int, int, int] = (255, 255, 255, 255)) -> Image.Image:
    if image.size == (width, height):
        return image
    canvas = Image.new("RGBA", (width, height), fill)
    work = image.copy()
    work.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas.alpha_composite(work, ((width - work.width) // 2, (height - work.height) // 2))
    return canvas


def save_png(path: pathlib.Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def save_ico(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    images = [
        exact(source("favicon_16"), 16, 16),
        exact(source("favicon_32"), 32, 32),
        exact(source("favicon_48"), 48, 48),
        exact(source("favicon_64"), 64, 64),
        exact(source("favicon_256"), 128, 128),
        exact(source("favicon_256"), 256, 256),
    ]
    images[-1].save(path, sizes=[img.size for img in images], append_images=images[:-1])


def main() -> int:
    save_png(ASSET_DIR / "d7pay-logo-mark-1024.png", exact(source("app_1024"), 1024, 1024))
    save_png(ASSET_DIR / "d7pay-logo-full-1600x1200.png", exact(source("app_1024"), 1600, 1200))
    save_png(ASSET_DIR / "d7pay-logo-wordmark-900x260.png", exact(source("sidebar_128"), 900, 260, (255, 255, 255, 0)))
    save_ico(ASSET_DIR / "d7pay-favicon.ico")

    sidebar = exact(source("sidebar_128"), 128, 128)
    sidebar_full = exact(source("sidebar_128"), 320, 180, (255, 255, 255, 0))
    for repo in [ROOT / "admin-h5", ROOT / "merchant-h5"]:
        save_png(repo / "src/assets/brand/d7pay-logo-mark.png", sidebar)
        save_png(repo / "src/assets/brand/d7pay-logo-full.png", sidebar_full)
        save_ico(repo / "public/d7pay-favicon.ico")

    download = exact(source("download_192"), 192, 192)
    save_png(ROOT / "apkdownload/src/assets/logo/d7pay-logo-192x192.png", download)
    save_png(ROOT / "apkdownload/public/d7pay-logo-192x192.png", download)

    density_sources = {
        "mipmap-mdpi": ("app_48", 48),
        "mipmap-hdpi": ("app_72", 72),
        "mipmap-xhdpi": ("app_96", 96),
        "mipmap-xxhdpi": ("app_144", 144),
        "mipmap-xxxhdpi": ("app_192", 192),
    }
    if FLUTTER_ROOT.exists():
        for folder, (source_name, size) in density_sources.items():
            save_png(
                FLUTTER_ROOT / f"android/app/src/main/res/{folder}/ic_launcher_d7pay.png",
                exact(source(source_name), size, size),
            )

    print("D7pay logo assets generated from per-size image_gen sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
