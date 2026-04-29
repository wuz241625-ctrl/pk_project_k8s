#!/usr/bin/env python3
from __future__ import annotations

import math
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = pathlib.Path(__file__).resolve().parents[4]
FLUTTER_ROOT = ROOT.parent / "pk_project" / "ashrafi_merchant_flutter"

BLUE = (16, 104, 245, 255)
CYAN = (26, 190, 228, 255)
NAVY = (13, 26, 58, 255)
DEEP_BLUE = (17, 57, 192, 255)


def font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ]
    for path in candidates:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


def gradient(size: tuple[int, int], left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size)
    px = img.load()
    for x in range(w):
        t = x / max(w - 1, 1)
        c = tuple(int(left[i] * (1 - t) + right[i] * t) for i in range(4))
        for y in range(h):
            px[x, y] = c
    return img


def paste_mask(base: Image.Image, fill: Image.Image | tuple[int, int, int, int], mask: Image.Image) -> None:
    if isinstance(fill, tuple):
        fill_img = Image.new("RGBA", base.size, fill)
    else:
        fill_img = fill
    base.alpha_composite(Image.composite(fill_img, Image.new("RGBA", base.size), mask))


def slanted_rect(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], slant: int, fill: int) -> None:
    x1, y1, x2, y2 = xy
    draw.polygon([(x1 + slant, y1), (x2, y1), (x2 - slant, y2), (x1, y2)], fill=fill)


def mark(size: int, with_plate: bool = False) -> Image.Image:
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    if with_plate:
        plate = Image.new("RGBA", (s, s), (255, 255, 255, 255))
        shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(shadow)
        r = int(s * 0.22)
        d.rounded_rectangle((int(s * 0.05), int(s * 0.05), int(s * 0.95), int(s * 0.95)), radius=r, fill=(0, 65, 160, 42))
        shadow = shadow.filter(ImageFilter.GaussianBlur(int(s * 0.018)))
        img.alpha_composite(shadow)
        d = ImageDraw.Draw(plate)
        d.rounded_rectangle((int(s * 0.06), int(s * 0.06), int(s * 0.94), int(s * 0.94)), radius=r, fill=(255, 255, 255, 255))
        img.alpha_composite(plate)

    mask_d = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask_d)
    d.rounded_rectangle((int(s * 0.24), int(s * 0.17), int(s * 0.84), int(s * 0.77)), radius=int(s * 0.30), fill=255)
    d.rectangle((int(s * 0.22), int(s * 0.17), int(s * 0.52), int(s * 0.77)), fill=255)
    d.polygon(
        [
            (int(s * 0.22), int(s * 0.17)),
            (int(s * 0.40), int(s * 0.17)),
            (int(s * 0.30), int(s * 0.77)),
            (int(s * 0.14), int(s * 0.77)),
        ],
        fill=255,
    )
    d.rounded_rectangle((int(s * 0.42), int(s * 0.28), int(s * 0.68), int(s * 0.64)), radius=int(s * 0.18), fill=0)
    d.rectangle((int(s * 0.34), int(s * 0.28), int(s * 0.52), int(s * 0.64)), fill=0)

    grad_d = gradient((s, s), BLUE, (35, 165, 236, 255))
    paste_mask(img, grad_d, mask_d)

    mask_swoosh = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask_swoosh)
    d.rounded_rectangle((int(s * 0.18), int(s * 0.47), int(s * 0.50), int(s * 0.78)), radius=int(s * 0.16), fill=255)
    d.polygon([(int(s * 0.48), int(s * 0.45)), (int(s * 0.60), int(s * 0.45)), (int(s * 0.48), int(s * 0.78)), (int(s * 0.34), int(s * 0.78))], fill=0)
    paste_mask(img, (9, 55, 194, 220), mask_swoosh)

    mask_7 = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask_7)
    slanted_rect(d, (int(s * 0.24), int(s * 0.39), int(s * 0.66), int(s * 0.50)), int(s * 0.04), 255)
    d.polygon(
        [
            (int(s * 0.55), int(s * 0.39)),
            (int(s * 0.71), int(s * 0.39)),
            (int(s * 0.48), int(s * 0.78)),
            (int(s * 0.34), int(s * 0.78)),
        ],
        fill=255,
    )
    grad_7 = gradient((s, s), DEEP_BLUE, CYAN)
    paste_mask(img, grad_7, mask_7)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def wordmark(width: int, height: int) -> Image.Image:
    scale = 3
    w, h = width * scale, height * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(int(h * 0.58))
    text = "D7pay"
    box = d.textbbox((0, 0), text, font=f)
    x = (w - (box[2] - box[0])) // 2
    y = int(h * 0.14)
    d.text((x, y), "D7", font=f, fill=BLUE)
    d.text((x + int((box[2] - box[0]) * 0.42), y), "pay", font=f, fill=NAVY)
    return img.resize((width, height), Image.Resampling.LANCZOS)


def full_logo(width: int, height: int) -> Image.Image:
    scale = 3
    w, h = width * scale, height * scale
    img = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    mark_img = mark(int(h * 0.54), with_plate=False)
    mark_img = mark_img.resize((int(h * 0.54), int(h * 0.54)), Image.Resampling.LANCZOS)
    mx = (w - mark_img.width) // 2
    my = int(h * 0.05)
    img.alpha_composite(mark_img, (mx, my))
    wm = wordmark(int(w * 0.84), int(h * 0.25)).resize((int(w * 0.84), int(h * 0.25)), Image.Resampling.LANCZOS)
    img.alpha_composite(wm, ((w - wm.width) // 2, int(h * 0.67)))
    return img.resize((width, height), Image.Resampling.LANCZOS)


def save_png(path: pathlib.Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def save_ico(path: pathlib.Path, source: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
    source.save(path, sizes=sizes)


def main() -> int:
    asset_dir = ROOT / "ops/tenants/d7pay/assets"
    source_mark = mark(1024, with_plate=True)
    source_full = full_logo(1600, 1200)
    source_word = wordmark(900, 260)

    save_png(asset_dir / "d7pay-logo-mark-1024.png", source_mark)
    save_png(asset_dir / "d7pay-logo-full-1600x1200.png", source_full)
    save_png(asset_dir / "d7pay-logo-wordmark-900x260.png", source_word)
    save_ico(asset_dir / "d7pay-favicon.ico", source_mark)

    for repo in [ROOT / "admin-h5", ROOT / "merchant-h5"]:
        save_png(repo / "src/assets/brand/d7pay-logo-mark.png", mark(96, with_plate=False))
        save_png(repo / "src/assets/brand/d7pay-logo-full.png", full_logo(320, 180))
        save_ico(repo / "public/d7pay-favicon.ico", source_mark)

    save_png(ROOT / "apkdownload/src/assets/logo/d7pay-logo-192x192.png", mark(192, with_plate=True))
    save_png(ROOT / "apkdownload/public/d7pay-logo-192x192.png", mark(192, with_plate=True))

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
                mark(size, with_plate=True),
            )

    print("D7pay logo assets generated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
