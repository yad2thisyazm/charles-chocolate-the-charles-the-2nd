"""
Builds dist/Charles.exe: one file, no console window, no Python needed.

Run:  pip install -r requirements.txt pyinstaller
      python tools/build_exe.py
"""

import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
IMG = os.path.join(ROOT, "docs", "img")
TUTORIAL_PICS = ("wave", "happy", "angry", "dizzy", "idle", "mission")  # what the first-run tutorial shows


def make_icon():
    """Her face on a pink tile (drawn by her own code), as a multi-size .ico."""
    spec = importlib.util.spec_from_file_location("desk_cat", os.path.join(ROOT, "desk_cat.py"))
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, "charles.ico")
    dc.portrait(256).save(path, sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
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
        "--hidden-import", "comtypes.client.dynamic",  # makes the desktop icon
        *[arg for name in TUTORIAL_PICS
          for arg in ("--add-data", f"{os.path.join(IMG, name + '.png')}{os.pathsep}img")],
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", BUILD,
        "--specpath", BUILD,
        os.path.join(ROOT, "desk_cat.py"),
    ], cwd=ROOT)
    print("\nbuilt", os.path.join(ROOT, "dist", "Charles.exe"))


if __name__ == "__main__":
    main()
