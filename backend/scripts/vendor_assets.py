"""Run ONCE (needs internet) to make the app work fully offline forever
after that.

Downloads:
  - Tailwind's self-contained browser build (a single JS file — it compiles
    utility classes to CSS entirely in the browser at runtime, and doesn't
    call home for anything once loaded, so hosting it locally is enough to
    remove the CDN dependency completely).
  - The Cairo + Material Symbols Outlined font files Google Fonts serves,
    plus a local stylesheet with @font-face rules pointing at them instead
    of fonts.gstatic.com.

Run with:  python -m scripts.vendor_assets
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
VENDOR_DIR = FRONTEND_DIR / "vendor"
FONTS_DIR = VENDOR_DIR / "fonts"

# A modern desktop User-Agent gets Google to serve the modern woff2 files
# (an old/bare User-Agent gets served ttf/eot instead).
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def vendor_tailwind() -> None:
    print("Downloading Tailwind's browser build...")
    data = fetch("https://cdn.tailwindcss.com?plugins=forms,container-queries")
    (VENDOR_DIR / "tailwind.js").write_bytes(data)
    print(f"  saved {VENDOR_DIR / 'tailwind.js'} ({len(data) / 1024:.0f} KB)")


def vendor_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    families = [
        ("Cairo", "wght@400;500;600;700;800;900"),
        ("Material+Symbols+Outlined", "wght,FILL@100..700,0..1"),
        ("IBM+Plex+Sans", "wght@400;500;600;700"),
    ]
    css_chunks = []
    for family, params in families:
        print(f"Fetching font metadata for {family}...")
        url = f"https://fonts.googleapis.com/css2?family={family}:{params}&display=swap"
        css_text = fetch(url).decode("utf-8")

        for match in re.finditer(
            r"url\((https://fonts\.gstatic\.com/[^)]+\.(?:woff2|woff|ttf))\)", css_text
        ):
            font_url = match.group(1)
            fname = font_url.rsplit("/", 1)[-1]
            dest = FONTS_DIR / fname
            if not dest.exists():
                print(f"  downloading {fname}...")
                dest.write_bytes(fetch(font_url))
            css_text = css_text.replace(font_url, f"fonts/{fname}")

        css_chunks.append(css_text)

    (VENDOR_DIR / "fonts.css").write_text("\n".join(css_chunks), encoding="utf-8")
    print(f"  saved {VENDOR_DIR / 'fonts.css'} + {len(list(FONTS_DIR.glob('*')))} font files")


def main() -> None:
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    vendor_tailwind()
    vendor_fonts()
    print("\nDone — the app no longer needs internet to load its styling/fonts.")


if __name__ == "__main__":
    main()
