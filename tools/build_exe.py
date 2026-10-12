"""
Builds dist/Charles.exe: one file, no console window, no Python needed.

Run:  pip install -r requirements.txt pyinstaller
      python tools/build_exe.py
"""

import os
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")


def make_icon():
    """Square-crop her portrait into a multi-size .ico."""
    img = Image.open(os.path.join(ROOT, "docs", "img", "coat-mochi.png")).convert("RGBA")
    l, t, r, b = img.getbbox()
    side = max(r - l, b - t)
    cx, cy = (l + r) // 2, (t + b) // 2
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(img.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)), (0, 0))
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, "charles.ico")
    sq.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def main():
    icon = make_icon()
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "Charles",
        "--icon", icon,
        "--collect-all", "uiautomation",       # ships its UIAutomation helper DLLs
        "--hidden-import", "comtypes.stream",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", BUILD,
        "--specpath", BUILD,
        os.path.join(ROOT, "desk_cat.py"),
    ], cwd=ROOT)
    print("\nbuilt", os.path.join(ROOT, "dist", "Charles.exe"))


if __name__ == "__main__":
    main()
