"""Generate the Bobodan application icon (.ico) from the brand avatar.

Windows desktop builds (P5G.2 Electron NSIS) and browser favicons share
one source: the transparent brand avatar in
`web/frontend/public/assets/brand/avatar/`. This script bakes the sizes
Windows actually uses into a multi-resolution ICO:

    .venv\\Scripts\\python.exe scripts/make_icon.py

Output: `web/frontend/public/assets/brand/bobodan.ico`
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow 未安装：pip install pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "web" / "frontend" / "public" / "assets" / "brand" / "avatar" / "bobodan-avatar-512.png"
OUTPUT = ROOT / "web" / "frontend" / "public" / "assets" / "brand" / "bobodan.ico"

# Windows 实际会请求的尺寸；256 是上限（更大的尺寸 Windows 不会用）。
SIZES = (16, 32, 48, 64, 128, 256)


def main() -> int:
    if not SOURCE.is_file():
        print(f"找不到源头像：{SOURCE}", file=sys.stderr)
        return 1

    with Image.open(SOURCE) as source:
        source = source.convert("RGBA")

        # Pillow 从同一图像按 sizes 自动生成多分辨率帧写入 ICO。
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        source.save(
            OUTPUT,
            format="ICO",
            sizes=[(size, size) for size in SIZES],
        )

    print(f"已生成 {OUTPUT}（{', '.join(f'{s}x{s}' for s in SIZES)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
