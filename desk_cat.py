"""
Charles Chocolate the Charles the IInd - a soft little cat that lives on your desktop.

  * Wanders, sits, loafs into naps, and blinks at you.
  * Left-click to poke her (she does NOT like it). Poke too much and she storms off.
  * Gently wiggle your cursor over her to pet her - she purrs.
  * Drag her around; she drops back onto the taskbar when you let go.
  * Spend more than 5 minutes scrolling Reels / Shorts / TikTok and she
    marches over and closes the tab for you (or blocks scrolling, or just
    tells you off - your choice).
  * Right-click for the menu (reels rules, coat, size, test mission, quit).

Run:   pythonw desk_cat.py          (no console window)
Test:  python desk_cat.py --test    (limit drops to 20 seconds)
"""

import ctypes
import hashlib
import json
import math
import os
import queue
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
import winreg
from ctypes import wintypes
from urllib.parse import urlsplit

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

try:
    import uiautomation as auto  # reads the browser address bar
except ImportError:
    auto = None

# ---------------------------------------------------------------- settings
VERSION = "1.2.1"  # bump with every release; the release workflow checks it matches the tag
REPO = "yad2thisyazm/charles-chocolate-the-charles-the-2nd"
TEST_MODE = "--test" in sys.argv
TEST_LIMIT = 20       # "Test the reels mission": 20s of reels open, scrolling or not
SCROLL_GRACE = 45     # counts as "scrolling" if you scrolled within this many seconds
FORGET_AFTER = 60     # leave reels this long and the timer resets

REEL_TITLES = ("reels", "tiktok", "#shorts", "youtube shorts")  # only if the URL can't be read
REEL_EXES = ("tiktok.exe", "instagram.exe")  # desktop apps, matched on the program itself
REEL_STORE_APPS = ("tiktok", "instagram")    # Store apps: exact window title in ApplicationFrameHost
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
            "opera_gx.exe", "vivaldi.exe", "arc.exe", "zen.exe", "chromium.exe",
            "librewolf.exe", "waterfox.exe", "floorp.exe", "thorium.exe"}

POKE_LINES = ["hss!", "don't touch me", "mrrow!!", "rude.", "excuse me??", "*swats you*"]
IDLE_LINES = ["mrrp", "...", "meow", "*stares at you*", "mew?"]
PET_LINES = ["purrrr", "prrr~", "more pets pls", "mrrp :3"]
DIZZY_LINES = ["@_@", "the room is spinning...", "whoaaa", "stop shaking meee", "never again"]
KNEAD_LINES = ["*makes biscuits*", "knead knead", "prrrp"]
WAVE_LINES = ["hi!! :3", "oh hi!", "hewwo", "*waves*"]
BUTTERFLY_LINES = ["!!", "a butterfly!!", "must... catch..."]
DONE_LINES = ["go touch grass :3", "you're welcome.", "drink some water!", "there. much better."]
HANG_STATES = ("mission_jump", "mission_hang", "mission_swipe", "mission_closing", "mission_letgo")
PAW = (80, -118)  # where her swatting paw is, in cat-local units, while hanging
FOOT = 26         # gap under her feet inside the window, so dangling legs fit

# name: (fur, ink for face, blush/heart)
COATS = {
    "Mochi (white)": ("#ecE8dd", "#2b2926", "#f2b8bd"),
    "Ash (grey)": ("#b4b3b8", "#26252a", "#efb0b8"),
    "Midnight (black)": ("#35343a", "#f3efe4", "#d98c9a"),
    "Ginger": ("#f1b47a", "#3a2a20", "#f0939b"),
    "Cream": ("#f2dcb8", "#3a2f26", "#f0a4a8"),
    "Blue (grey-blue)": ("#9aa7b8", "#232833", "#efb0b8"),
}
SIZES = {"Small": 0.75, "Medium": 1.0, "Large": 1.3}
LIMITS = {"2 minutes": 2, "5 minutes": 5, "10 minutes": 10, "15 minutes": 15, "30 minutes": 30}
WARNINGS = {"30 seconds before": 30, "1 minute before": 60, "2 minutes before": 120, "No warning": 0}
ACTIONS = {"Close the tab": "close", "Block scrolling": "block", "Just tell me off": "nag"}
DEFAULTS = {"coat": "Mochi (white)", "size": "Medium",
            "limit_minutes": 5, "warning_seconds": 60, "action": "close", "welcomed": False,
            "check_updates": None}  # None: never asked, so it's off
APP_NAME = "Charles Chocolate the Charles the 2nd"  # what the desktop icon is called

# Settings live next to the script when run from source; in %APPDATA% for the packaged
# .exe (a one-file exe unpacks into a temp folder that's wiped on exit).
FROZEN = getattr(sys, "frozen", False)
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Charles Chocolate")
if FROZEN:
    os.makedirs(DATA_DIR, exist_ok=True)
    SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
    ASSETS = os.path.join(getattr(sys, "_MEIPASS", ""), "img")
else:
    SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desk_cat_settings.json")
    ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "img")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ---------------------------------------------------------------- win32
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
except Exception:
    pass

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                       ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                       ctypes.c_void_p, wintypes.DWORD]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
shell32 = ctypes.WinDLL("shell32")
shell32.SHGetFolderPathW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR]
try:
    UI_SCALE = user32.GetDpiForSystem() / 96  # display scaling (150% -> 1.5)
except Exception:
    UI_SCALE = 1.0

WM_CLOSE = 0x0010
VK_LBUTTON, VK_SHIFT, VK_CONTROL, VK_MENU, VK_W, VK_LWIN, VK_RWIN = 0x01, 0x10, 0x11, 0x12, 0x57, 0x5B, 0x5C
SCROLL_KEYS = {0x21, 0x22, 0x23, 0x24, 0x26, 0x28}  # PgUp, PgDn, End, Home, Up, Down
NEXT_KEYS = SCROLL_KEYS | {0x20, 0x4A, 0x4B}  # + Space, J, K: counted as scrolling, never blocked
KEYUP = 0x0002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def window_exe(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def work_area(x=0, y=0):
    """The screen minus the taskbar, on the monitor nearest a point (the main one by default)."""
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    mon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        r = mi.rcWork
    else:
        r = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def tap(vk, up=False):
    user32.keybd_event(vk, 0, KEYUP if up else 0, 0)


def bring_to_front(hwnd):
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    # Borrow the front window's input state so Windows lets us switch focus. (An Alt
    # tap would do it too, but that lands in whatever app you're using.)
    me = kernel32.GetCurrentThreadId()
    them = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(them) and them != me and user32.AttachThreadInput(me, them, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, them, False)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


def modifiers_held():
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN))


def shade(hex_color, f):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(max(0, min(255, int(v * f))) for v in (r, g, b))


def mix(c1, c2, f):
    """Opaque blend of two hex colours (f=0 -> c1, f=1 -> c2)."""
    a, b = shade(c1, 1), shade(c2, 1)
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def bezier(pts, t):
    while len(pts) > 1:
        pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(pts, pts[1:])]
    return pts[0]


# ---------------------------------------------------------------- her home: startup, desktop icon
QUIT_EVENT = None  # set by another Charles starting up (a newer .exe, say): time to go


def claim_single_instance():
    """One Charles at a time. Opening her again asks the one already running to leave
    and takes over, so running a freshly downloaded Charles.exe is all an update needs."""
    global QUIT_EVENT
    mutex = kernel32.CreateMutexW(None, True, "Local\\CharlesChocolate.running")
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    QUIT_EVENT = kernel32.CreateEventW(None, False, False, "Local\\CharlesChocolate.quit")
    if already:
        kernel32.SetEvent(QUIT_EVENT)
        if kernel32.WaitForSingleObject(mutex, 8000) not in (0, 0x80):  # ours, or she quit
            sys.exit(0)  # the other one didn't leave; don't run two
        kernel32.ResetEvent(QUIT_EVENT)
    return mutex


def launch_command():
    """(program, arguments) that start her: the .exe, or pythonw + this script."""
    if FROZEN:
        return sys.executable, ""
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return (pyw if os.path.exists(pyw) else sys.executable), f'"{os.path.abspath(__file__)}"'


def startup_command():
    exe, args = launch_command()
    return f'"{exe}" {args}'.strip()


def in_startup():
    """Is she in the Run key? Points it here if what it points at has moved, or (for the
    .exe) if this is a different copy, so a newer download takes over."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
            cmd, _ = winreg.QueryValueEx(k, "Charles Chocolate")
            stale = not all(os.path.exists(path) for path in str(cmd).split('"')[1::2])
            if stale or (FROZEN and str(cmd) != startup_command()):
                winreg.SetValueEx(k, "Charles Chocolate", 0, winreg.REG_SZ, startup_command())
        return True
    except OSError:
        return False


def set_startup(on):
    """Returns False if Windows wouldn't let us."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Charles Chocolate", 0, winreg.REG_SZ, startup_command())
            else:
                winreg.DeleteValue(k, "Charles Chocolate")
        return True
    except OSError:
        return on is False and not in_startup()


def desktop_icon_path():
    buf = ctypes.create_unicode_buffer(260)
    shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY (follows OneDrive)
    return os.path.join(buf.value or os.path.join(os.path.expanduser("~"), "Desktop"), APP_NAME + ".lnk")


def _wscript_shell():
    import comtypes.client
    return comtypes.client.CreateObject("WScript.Shell", dynamic=True)


def icon_file():
    """The .exe carries her icon; from source, draw one into her data folder."""
    if FROZEN:
        return sys.executable
    path = os.path.join(DATA_DIR, "charles.ico")
    if not os.path.exists(path):
        os.makedirs(DATA_DIR, exist_ok=True)
        portrait(256).save(path, sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    return path


def has_desktop_icon():
    return os.path.exists(desktop_icon_path())


def set_desktop_icon(on):
    """Adds or removes her desktop icon. Returns False if that didn't work."""
    path = desktop_icon_path()
    try:
        if not on:
            if os.path.exists(path):
                os.remove(path)
            return True
        exe, args = launch_command()
        link = _wscript_shell().CreateShortcut(path)
        link.TargetPath = exe
        link.Arguments = args
        link.WorkingDirectory = os.path.dirname(os.path.abspath(sys.argv[0]))
        link.IconLocation = icon_file() + ",0"
        link.Description = "A small, soft, slightly judgemental cat for your desktop"
        link.Save()
        return True
    except Exception:
        return False


def follow_this_exe():
    """A newer Charles.exe was opened from somewhere else: point her desktop icon at it."""
    if not FROZEN or not has_desktop_icon():
        return
    try:
        target = _wscript_shell().CreateShortcut(desktop_icon_path()).TargetPath
    except Exception:
        return
    if os.path.normcase(str(target)) != os.path.normcase(sys.executable):
        set_desktop_icon(True)


# ---------------------------------------------------------------- updates
def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


class Updater:
    """For the .exe, while "Check for updates" is on: asks GitHub once a day whether there's a
    newer Charles.exe, and when you say so, downloads it, checks it, swaps it in for this one
    and starts it (which makes this one leave). Settings live in %APPDATA%, so they stay."""

    API = "https://api.github.com/repos/" + REPO + "/releases/latest"
    DOWNLOADS = "https://github.com/" + REPO + "/releases/download/"

    def __init__(self, enabled):
        self.enabled = enabled    # callable: is the setting on?
        self.last_check = 0.0
        self.found = None         # {"version", "url", "size", "sha256"} of a newer release
        self.progress = None      # 0..1 while downloading
        self.message = None       # something she should say about it
        self.busy = False
        exe = sys.executable
        self.old, self.new = exe[:-4] + ".old.exe", exe + ".new"
        threading.Thread(target=self._loop, daemon=True).start()

    def check_soon(self):
        self.last_check = 0.0

    def _loop(self):
        time.sleep(30)
        while True:
            for leftover in (self.old, self.new):  # from the last update, once that copy has exited
                if os.path.exists(leftover) and not self.busy:
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass
            if self.enabled() and not self.found and time.time() - self.last_check > 24 * 3600:
                self.last_check = time.time()
                try:
                    self.found = self._latest()
                except Exception:
                    pass  # offline, GitHub's down...: try again tomorrow
            time.sleep(60)

    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": f"Charles-Chocolate/{VERSION}",
                                                   "Accept": "application/vnd.github+json"})
        return urllib.request.urlopen(req, timeout=30)

    def _latest(self):
        with self._get(self.API) as r:
            rel = json.load(r)
        if rel.get("draft") or rel.get("prerelease") or \
                version_tuple(rel.get("tag_name")) <= version_tuple(VERSION):
            return None
        for a in rel.get("assets", []):
            url = a.get("browser_download_url", "")
            if a.get("name") == "Charles.exe" and url.startswith(self.DOWNLOADS):
                return {"version": rel["tag_name"].lstrip("v"), "url": url, "size": int(a["size"]),
                        "sha256": (a.get("digest") or "").removeprefix("sha256:").lower()}
        return None

    def install(self):
        if self.found and not self.busy:
            self.busy = True
            threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        f, exe = self.found, sys.executable
        try:
            self.progress = 0.0
            digest = hashlib.sha256()
            done = 0
            with self._get(f["url"]) as r, open(self.new, "wb") as out:
                while chunk := r.read(1 << 18):
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    self.progress = min(1.0, done / max(1, f["size"]))
            with open(self.new, "rb") as check:
                looks_like_exe = check.read(2) == b"MZ"
            if done != f["size"] or not looks_like_exe or (f["sha256"] and digest.hexdigest() != f["sha256"]):
                raise ValueError("download didn't match")
        except Exception:
            self._give_up("the download went wrong, so I'm staying as I am. try again later?")
            return
        # Windows lets a running .exe be renamed (not deleted), so: me -> .old.exe, new -> me.
        try:
            if os.path.exists(self.old):
                os.remove(self.old)
            os.replace(exe, self.old)
        except OSError:
            self._give_up("I'm not allowed to change my own file here. grab the new me from GitHub!",
                          open_page=True)
            return
        try:
            os.replace(self.new, exe)
            env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")  # start it as a fresh app
            subprocess.Popen([exe], env=env, close_fds=True,
                             creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_PROCESS_GROUP
            self.message = "see you in a sec :3"  # the new me will ask me to leave
        except OSError:
            try:
                if os.path.exists(exe):
                    os.replace(exe, self.new)
                os.replace(self.old, exe)
            except OSError:
                pass
            self._give_up("hm, the new me wouldn't start, so I'm staying as I am.")

    def _give_up(self, message, open_page=False):
        try:
            os.remove(self.new)
        except OSError:
            pass
        self.progress, self.busy, self.message = None, False, message
        if open_page:
            webbrowser.open("https://github.com/" + REPO + "/releases/latest")


# ---------------------------------------------------------------- reels watcher
def is_reels_url(url):
    """Is this address a short-video feed? Matches the site and the start of the path
    exactly, so instagram.com/reelsofindia or google.com/search?q=tiktok.com don't count."""
    url = (url or "").strip().lower()
    if not url or " " in url:  # something typed into the address bar, not an address
        return False
    if "://" not in url:  # Chrome and Edge hide the https://
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    for prefix in ("www.", "m."):
        host = host.removeprefix(prefix)
    path = [p for p in parts.path.split("/") if p]
    first = path[0] if path else ""
    if host == "instagram.com":
        return first in ("reels", "reel")
    if host == "youtube.com":
        return first == "shorts"
    if host == "facebook.com":
        return first in ("reel", "reels")
    if host == "tiktok.com":  # the feeds and single videos; not profiles, settings, help...
        return first in ("", "foryou", "following", "friends", "explore") or \
            (first.startswith("@") and len(path) > 1 and path[1] in ("video", "photo"))
    return False


def same_page(tab_name, title):
    """Does a tab's name belong to the page the window title shows?"""
    a, b = (tab_name or "").lower().strip()[:24], (title or "").lower()
    return bool(a) and (b.startswith(a) or a in b)


class ReelsWatcher:
    """Background thread: figures out if the focused window is a reels feed,
    plus mouse/keyboard hooks that note when you scroll (and can block it)."""

    def __init__(self):
        # (reels hwnd or None, is it a browser, are we sure): one tuple, swapped in whole,
        # so nobody reads the window from one check and the rest from the next.
        self.seen = (None, False, False)
        self.last_scroll = 0.0
        self.hook_ok = True
        self.blocking = False     # while set, scrolling in any reels window is swallowed
        self.blocked_at = 0.0     # last time we swallowed a scroll
        self._edit_cache = {}     # hwnd -> (address bar, or None while we wait to look again)
        self.jobs = queue.Queue()
        threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._hooks, daemon=True).start()

    def scrolling(self):
        if not self.hook_ok:
            return True
        return time.time() - self.last_scroll < SCROLL_GRACE

    def _hooks(self):
        def mouse(n, w, l):
            if n == 0 and w in (0x020A, 0x020E):  # wheel / horizontal wheel
                reels = self.seen[0]
                pt = ctypes.cast(l, ctypes.POINTER(wintypes.POINT))[0]  # MSLLHOOKSTRUCT.pt
                if reels and user32.GetAncestor(user32.WindowFromPoint(pt), 2) == reels:
                    self.last_scroll = time.time()
                    if self.blocking:
                        self.blocked_at = time.time()
                        return 1
            return user32.CallNextHookEx(None, n, w, l)

        def keyboard(n, w, l):
            if n == 0 and w in (0x0100, 0x0104):  # WM_KEYDOWN / WM_SYSKEYDOWN
                vk = ctypes.cast(l, ctypes.POINTER(wintypes.DWORD))[0]
                reels = self.seen[0]
                if vk in NEXT_KEYS and reels and user32.GetForegroundWindow() == reels:
                    self.last_scroll = time.time()
                    if self.blocking and vk in SCROLL_KEYS:
                        self.blocked_at = time.time()
                        return 1
            return user32.CallNextHookEx(None, n, w, l)

        self._procs = HOOKPROC(mouse), HOOKPROC(keyboard)
        mod = kernel32.GetModuleHandleW(None)
        hooks = []

        def install():
            for h in hooks:
                if h:
                    user32.UnhookWindowsHookEx(h)
            hooks[:] = [user32.SetWindowsHookExW(14, self._procs[0], mod, 0),  # WH_MOUSE_LL
                        user32.SetWindowsHookExW(13, self._procs[1], mod, 0)]  # WH_KEYBOARD_LL
            self.hook_ok = bool(hooks[0])

        install()
        if not self.hook_ok:
            return
        # Windows quietly drops a low-level hook that answers too slowly (easy for Python
        # while she's busy drawing) and doesn't tell us, so put fresh ones in every minute.
        user32.SetTimer(None, 0, 60_000, None)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0113:  # WM_TIMER
                install()

    def _url(self, hwnd):
        if auto is None:
            return ""
        edit, retry_at = self._edit_cache.get(hwnd, (None, 0.0))
        if edit is None and time.time() < retry_at:
            return ""
        try:
            if edit is None or not edit.Exists(0, 0):
                edit = auto.ControlFromHandle(hwnd).EditControl(searchDepth=16)
            url = (edit.GetValuePattern().Value or "").lower()
            self._edit_cache[hwnd] = (edit, 0.0)
            return url
        except Exception:
            # No address bar (fullscreen, an installed web app): don't spend a second
            # searching for it every second, look again in a little while.
            self._edit_cache[hwnd] = (None, time.time() + 15)
            return ""

    def url_is_reels(self, hwnd):
        return is_reels_url(self._url(hwnd))

    def _check(self):
        # The focused window first; if that isn't reels (e.g. a screen recorder
        # grabbed focus), fall back to whatever window the mouse is over.
        hit = self._classify(user32.GetForegroundWindow())
        if hit[0]:
            return hit
        under = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(*cursor_pos())), 2)  # GA_ROOT
        if under:
            under_hit = self._classify(under)
            if under_hit[0]:
                return under_hit
        return hit

    def _classify(self, hwnd):
        """(reels hwnd or None, is it a browser, are we sure)"""
        if not hwnd:
            return None, False, False
        title = window_title(hwnd).lower()
        exe = window_exe(hwnd)
        if exe in BROWSERS:
            url = self._url(hwnd)
            if url:  # trust the address bar over the title ("fishing reels - amazon")
                return (hwnd if is_reels_url(url) else None), True, True
            hit = any(t in title for t in REEL_TITLES)
            return (hwnd if hit else None), True, False
        if exe in REEL_EXES or (exe == "applicationframehost.exe" and title.strip() in REEL_STORE_APPS):
            return hwnd, False, True
        return None, False, False

    # UI Automation objects belong to the watcher thread, so the cat hands it
    # jobs and picks up the result on a later frame.
    def submit(self, fn, *args):
        job = {"fn": fn, "args": args, "done": False, "result": None}
        self.jobs.put(job)
        return job

    def find_tab(self, hwnd):
        """The active reels tab: where to swat, and its close (X) button if we can tell
        which one that is. None if we can't be sure which tab is showing the reels."""
        if auto is None or not self.url_is_reels(hwnd):
            return None
        root = auto.ControlFromHandle(hwnd)
        title = window_title(hwnd)
        for strip, _ in auto.WalkControl(root, maxDepth=12):
            if strip.ControlTypeName != "TabControl":
                continue
            for tab, _ in auto.WalkControl(strip, maxDepth=3):
                if tab.ControlTypeName != "TabItemControl":
                    continue
                try:
                    selected = tab.GetSelectionItemPattern().IsSelected
                except Exception:
                    selected = True  # no selection info: the name check below decides
                if not selected or not same_page(tab.Name, title):
                    continue
                buttons = [b for b, _ in auto.WalkControl(tab, maxDepth=2)
                           if b.ControlTypeName == "ButtonControl" and b.BoundingRectangle.width() > 0]
                # A tab playing sound can have a mute button next to the X (Edge, or Chrome
                # with tab muting on), so only press one that's clearly the close button.
                # Otherwise she still swats the tab, and closes it with Ctrl+W.
                named = [b for b in buttons if "close" in (b.Name or "").lower()]
                btn = named[0] if named else buttons[0] if len(buttons) == 1 else None
                r = (btn or tab).BoundingRectangle
                if r.width() <= 0:
                    return None
                x = (r.left + r.right) // 2 if btn else r.right - 16
                return {"x": x, "y": (r.top + r.bottom) // 2, "button": btn, "name": tab.Name}
            return None
        return None

    def close_tab(self, hwnd):
        """Close the reels tab. Finds it afresh right before pressing (you may have
        switched tabs while she ran over), so it only presses what's showing reels now.
        Returns "closed", "gone" (you'd already left) or "unsure" (didn't touch anything)."""
        if not user32.IsWindow(hwnd) or not self.url_is_reels(hwnd):
            return "gone"
        found = self.find_tab(hwnd)
        if found is None:
            return "unsure"
        btn = found["button"]
        if btn is not None:
            try:
                try:
                    btn.GetInvokePattern().Invoke()
                except Exception:
                    btn.GetLegacyIAccessiblePattern().DoDefaultAction()
                return "closed"
            except Exception:
                pass
        # Keyboard fallback: only if that window is in front *and* still on reels, and
        # no key is held (Shift would turn Ctrl+W into close-the-whole-window).
        if modifiers_held() or not bring_to_front(hwnd):
            return "unsure"
        if self.url_is_reels(hwnd) and user32.GetForegroundWindow() == hwnd and not modifiers_held():
            tap(VK_CONTROL); tap(VK_W); tap(VK_W, up=True); tap(VK_CONTROL, up=True)
            return "closed"
        return "unsure"

    def _watch(self):
        ctx = auto.UIAutomationInitializerInThread() if auto else None
        if ctx:
            ctx.__enter__()
            auto.SetGlobalSearchTimeout(1)
        next_check = 0.0
        while True:
            try:
                job = self.jobs.get(timeout=0.1)
            except queue.Empty:
                job = None
            if job:
                try:
                    job["result"] = job["fn"](*job["args"])
                except Exception:
                    job["result"] = None
                job["done"] = True
            if time.time() >= next_check:
                next_check = time.time() + 1.0
                try:
                    self.seen = self._check()
                except Exception:
                    self.seen = (None, False, False)
                if len(self._edit_cache) > 32:  # forget windows that have closed
                    for h in [h for h in self._edit_cache if not user32.IsWindow(h)]:
                        del self._edit_cache[h]


# ---------------------------------------------------------------- drawing
# supersampling for smooth edges (scaled-up displays already have the pixels to spare)
SS = 3 if UI_SCALE < 1.4 else 2


class Painter:
    """Draws in cat-local units: origin at the cat's feet, y up is negative,
    +x is the way she faces. Mirrors automatically when facing left.
    `g` grows every shape (used to paint the soft rim underneath the fur)."""

    def __init__(self, img, scale, facing, cx, gy):
        self.d = ImageDraw.Draw(img)
        self.k = scale * SS
        self.f = facing
        self.cx, self.gy = cx * SS, gy * SS
        self.g = 0.0
        self.col = "#ffffff"
        self.kx = self.ky = 1.0   # squash & stretch around her feet
        self.twitch = 0.0         # flicks the far ear
        self.ear_at = None

    def p(self, x, y):
        return self.cx + x * self.f * self.k * self.kx, self.gy + y * self.k * self.ky

    def ellipse(self, cx, cy, rx, ry, fill=None):
        x, y = self.p(cx, cy)
        rx, ry = (rx + self.g) * self.k * self.kx, (ry + self.g) * self.k * self.ky
        self.d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=fill or self.col)

    def rrect(self, x1, y1, x2, y2, r):
        (a, b), (c, d) = self.p(x1, y1), self.p(x2, y2)
        g = self.g * self.k
        self.d.rounded_rectangle((min(a, c) - g, min(b, d) - g, max(a, c) + g, max(b, d) + g),
                                 radius=(r + self.g) * self.k, fill=self.col)

    def rpoly(self, pts, r):
        """Polygon with soft rounded corners."""
        flat = [self.p(*q) for q in pts]
        rr = (r + self.g) * self.k
        self.d.polygon(flat, fill=self.col)
        self.d.line(flat + [flat[0]], fill=self.col, width=int(rr * 2), joint="curve")
        for x, y in flat:
            self.d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=self.col)

    def tube(self, pts, r):
        """A thick round-ended stroke along a bezier curve."""
        n = 1 if len(pts) == 2 else 18
        flat = [self.p(*bezier(pts, i / n)) for i in range(n + 1)]
        rr = (r + self.g) * self.k
        self.d.line(flat, fill=self.col, width=int(rr * 2), joint="curve")
        for x, y in flat[::3] + [flat[-1]]:
            self.d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=self.col)

    def stroke(self, pts, w, fill):
        flat = [self.p(*q) for q in pts]
        width = max(1, int(w * self.k))
        self.d.line(flat, fill=fill, width=width, joint="curve")
        for x, y in (flat[0], flat[-1]):
            self.d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=fill)

    def arc(self, cx, cy, r, start, end, w, fill):
        x, y = self.p(cx, cy)
        rr = r * self.k
        self.d.arc((x - rr, y - rr, x + rr, y + rr), start, end, fill=fill, width=max(1, int(w * self.k)))

    def ear_tris(self, hx, hy, tilt):
        tw = self.twitch
        return ([(hx - 25, hy - 8), (hx - 19 - tilt, hy - 33), (hx - 5, hy - 22)],
                [(hx + 3, hy - 24), (hx + 18 + tilt + tw, hy - 34 + abs(tw) * 0.5), (hx + 26, hy - 8)])

    def ears(self, hx, hy, tilt=0.0):
        self.ear_at = (hx, hy, tilt)
        for tri in self.ear_tris(hx, hy, tilt):
            self.rpoly(tri, 4.5)

    def inner_ears(self, fill):
        if not self.ear_at:
            return
        col, self.col = self.col, fill
        for tri in self.ear_tris(*self.ear_at):
            mx, my = sum(x for x, _ in tri) / 3, sum(y for _, y in tri) / 3
            self.rpoly([(mx + (x - mx) * 0.45, my + (y - my) * 0.45 + 2) for x, y in tri], 1.6)
        self.col = col


def note(d, x, y, s, fill):
    """A little music note (purring)."""
    d.ellipse((x - s * 0.7, y - s * 0.5, x + s * 0.7, y + s * 0.5), fill=fill)
    d.line((x + s * 0.6, y, x + s * 0.6, y - s * 2.2), fill=fill, width=max(1, int(s * 0.32)))
    d.line((x + s * 0.6, y - s * 2.2, x + s * 1.4, y - s * 1.5), fill=fill, width=max(1, int(s * 0.32)))


def butterfly(d, x, y, s, flap, col):
    w = s * (0.35 + 0.65 * flap)
    for dx in (-1, 1):
        d.ellipse((x + dx * w * 1.15 - w * 0.6, y - s * 1.0, x + dx * w * 1.15 + w * 0.6, y + s * 0.05), fill=col)
        d.ellipse((x + dx * w * 0.8 - w * 0.4, y - s * 0.05, x + dx * w * 0.8 + w * 0.4, y + s * 0.75),
                  fill=col)
    d.line((x, y - s * 0.8, x, y + s * 0.7), fill="#5a4a55", width=max(1, int(s * 0.28)))


def heart(d, x, y, s, fill):
    d.ellipse((x - s, y - s, x, y), fill=fill)
    d.ellipse((x, y - s, x + s, y), fill=fill)
    d.polygon([(x - s, y - s * 0.45), (x + s, y - s * 0.45), (x, y + s)], fill=fill)


def portrait(n, coat="Mochi (white)", tile="#f7a8c4"):
    """Her face on a soft rounded tile, n pixels square: her icon."""
    fur, ink, blush = COATS[coat]
    w = n * 4
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, w - 1), radius=int(w * 0.24), fill=tile)
    cat = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    k = n / 112
    P = Painter(cat, k * 4 / SS, 1, (n / 2 - 9 * k) * 4 / SS, n * 0.72 * 4 / SS)
    hx, hy = 0, -38
    for g, col in ((1.4, shade(fur, 0.8)), (0.0, fur)):
        P.g, P.col = g, col
        P.ellipse(hx - 2, hy + 66, 50, 36)  # shoulders, running off the bottom
        P.ellipse(hx, hy, 33, 29)
        P.ears(hx, hy)
    P.inner_ears(mix(fur, blush, 0.75))
    ex1, ex2, ey, mx = hx + 5, hx + 23, hy + 1, hx + 14
    for ex in (ex1, ex2):
        P.ellipse(ex, ey, 5.6, 6.3, ink)
        P.ellipse(ex + 1.7, ey - 1.9, 2.1, 2.1, "#ffffff" if ink[1:3] < "80" else "#2b2926")
    for ex in (ex1 - 5, ex2 + 5):
        P.ellipse(ex, ey + 7.5, 4.6, 2.8, mix(fur, blush, 0.8))
    P.ellipse(mx, ey + 4.4, 2.2, 1.5, mix(blush, ink, 0.25))
    P.arc(mx - 2.2, ey + 6.2, 2.2, 10, 170, 1.5, ink)
    P.arc(mx + 2.2, ey + 6.2, 2.2, 10, 170, 1.5, ink)
    cat.putalpha(ImageChops.multiply(cat.getchannel("A"), img.getchannel("A")))  # clip to the tile
    img.alpha_composite(cat)
    return img.resize((n, n), Image.LANCZOS)


def to_bgra(img, reduce=1):
    """RGBA image -> premultiplied BGRA bytes, the way a layered window wants them."""
    out = img.convert("RGBa")
    if reduce > 1:
        out = out.reduce(reduce)
    r, g, b, a = out.split()
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


class Surface:
    """A window with per-pixel transparency that we paint whole frames into."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, ex | 0x80000)  # WS_EX_LAYERED
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.dib = None
        self.w = self.h = 0

    def resize(self, w, h):
        bmi = BITMAPINFOHEADER(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(self.mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(self.mem_dc, dib)
        if self.dib:
            gdi32.DeleteObject(self.dib)
        self.dib, self.bits, self.w, self.h = dib, bits, w, h

    def show(self, data, x, y, alpha=255):
        ctypes.memmove(self.bits, data, len(data))
        blend = BLENDFUNCTION(0, 0, alpha, 1)
        pos = wintypes.POINT(int(x), int(y))
        size = wintypes.SIZE(self.w, self.h)
        src = wintypes.POINT(0, 0)
        user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, ctypes.byref(pos), ctypes.byref(size),
                                   self.mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), 2)


# ---------------------------------------------------------------- the cat
def load_settings():
    """Saved settings, plus the names of any that were invalid. People hand-edit the
    file, so anything that doesn't make sense falls back to its default."""
    settings, bad = dict(DEFAULTS), []
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except FileNotFoundError:
        return settings, bad
    except Exception:
        return settings, ["the whole file"]
    if not isinstance(saved, dict):
        return settings, ["the whole file"]
    choices = {"coat": COATS, "size": SIZES, "action": ACTIONS.values()}
    ranges = {"limit_minutes": (1, 24 * 60), "warning_seconds": (0, 24 * 60 * 60)}
    for key, value in saved.items():
        if key in choices:
            ok = isinstance(value, str) and value in choices[key]
        elif key == "welcomed":
            ok = isinstance(value, bool)
        elif key == "check_updates":
            ok = value is None or isinstance(value, bool)
        elif key in ranges:
            try:
                ok = not isinstance(value, bool) and value == int(value) and \
                    ranges[key][0] <= int(value) <= ranges[key][1]
                value = int(value)
            except (TypeError, ValueError):
                ok = False
        else:
            continue
        if ok:
            settings[key] = value
        else:
            bad.append(key)
    return settings, bad


class Cat:
    def __init__(self):
        self.settings, bad = load_settings()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.update_idletasks()
        self.hwnd = int(self.root.wm_frame(), 16)
        self.surface = Surface(self.hwnd)
        user32.SetWindowLongW(self.hwnd, -20, user32.GetWindowLongW(self.hwnd, -20) | 0x80)  # TOOLWINDOW
        self.apply_size()

        self.wa = work_area()
        self.x = float(self.wa[2] - self.W - 140)
        self.y = float(self.floor())
        self.vy = 0.0
        self.facing = -1
        self.state = "idle"
        self.pose = "sit"
        self.state_until = time.time() + 4
        self.target = None
        self.speed = 1.6
        self.phase = 0.0
        self.bubble = None
        self.bubble_until = 0
        self.blink_at = time.time() + 3
        self.pokes = []
        self.pet = 0.0
        self.last_cursor = cursor_pos()
        self.t = 0.0

        self.watcher = ReelsWatcher()
        self.reels_secs = 0.0
        self.away_secs = 0.0
        self.warned = False
        self.mission_hwnd = None
        self.mission_browser = False
        self.job = None
        self.testing = False
        self.land_msg = None
        self.spin = 0.0
        self.last_drag_v = (0, 0)
        self.dizzy_pending = False
        self.last_tick = time.time()
        self.screen_check_at = 0.0
        self.init_anim()

        self.drag = None
        self.welcome = None
        self.updater = Updater(lambda: bool(self.settings["check_updates"])) if FROZEN else None
        self.update_offered = False
        self.root.bind("<ButtonPress-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Button-3>", self.on_menu)
        self.build_menu()

        self.root.geometry(f"{self.W}x{self.H}+{int(self.x)}+{int(self.y)}")
        if bad:
            self.say(f"mrrp! (my settings file had a typo in {', '.join(bad)}, so I used the default)", 7)
        elif not self.settings["welcomed"]:
            self.say("oh! a new human. read this pls :3", 5)
        elif self.updater and self.settings["check_updates"] is None:
            # someone who had her before updates existed: tell them once
            self.say("new trick! I can check for updates. right-click me → Check for updates", 8)
            self.settings["check_updates"] = False
            self.save_settings()
        else:
            self.say("mrrp! hi :3", 3)
        self.set_state("wave", 2.6)
        if not self.settings["welcomed"]:
            self.root.after(700, self.show_welcome)
        self.root.after(2000, follow_this_exe)
        self.loop()

    def init_anim(self):
        self.sq, self.sqv = 0.0, 0.0      # squash/stretch spring
        self.look = [0.0, 0.0]            # where her pupils point
        self.glance = (0.0, 0.0)
        self.glance_at = time.time() + 3
        self.twitch_t0 = 0.0
        self.twitch_at = time.time() + random.uniform(3, 8)
        self.hop_t0, self.hop_n, self.hop_y = 0.0, 0, 0.0
        self.bf = None                    # butterfly she's watching
        self.paw_tip = None

    # ---------------- setup helpers
    def apply_size(self):
        self.s = SIZES.get(self.settings["size"], 1.0) * UI_SCALE
        self.W, self.H = int(280 * self.s), int(230 * self.s)
        self.font = ImageFont.truetype("segoeuib.ttf", int(13 * self.s * SS))
        self.zfont = ImageFont.truetype("segoeuib.ttf", int(12 * self.s * SS))
        self.surface.resize(self.W, self.H)
        self.root.geometry(f"{self.W}x{self.H}")

    def build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Reels timer: 0:00", state="disabled")
        self.vars = {key: tk.StringVar(value=str(self.settings[key]))
                     for key in ("coat", "size", "limit_minutes", "warning_seconds", "action")}

        def submenu(key, options, cmd):
            sub = tk.Menu(self.menu, tearoff=0)
            for label, value in options.items():
                sub.add_radiobutton(label=label, variable=self.vars[key], value=str(value),
                                    command=lambda: cmd(key))
            return sub

        rules = tk.Menu(self.menu, tearoff=0)
        rules.add_cascade(label="Time limit", menu=submenu("limit_minutes", LIMITS, self.set_rule))
        rules.add_cascade(label="Warning", menu=submenu("warning_seconds", WARNINGS, self.set_rule))
        rules.add_cascade(label="When time's up", menu=submenu("action", ACTIONS, self.set_rule))
        self.menu.add_cascade(label="Reels rules", menu=rules)
        self.menu.add_cascade(label="Coat", menu=submenu("coat", {n: n for n in COATS}, self.set_look))
        self.menu.add_cascade(label="Size", menu=submenu("size", {n: n for n in SIZES}, self.set_look))
        self.startup_var = tk.BooleanVar(value=in_startup())
        self.menu.add_checkbutton(label="Start with Windows", variable=self.startup_var,
                                  command=self.toggle_startup)
        self.desktop_var = tk.BooleanVar(value=has_desktop_icon())
        self.menu.add_checkbutton(label="Desktop icon", variable=self.desktop_var,
                                  command=self.toggle_desktop_icon)
        if self.updater:
            self.updates_var = tk.BooleanVar(value=bool(self.settings["check_updates"]))
            self.menu.add_checkbutton(label="Check for updates", variable=self.updates_var,
                                      command=self.toggle_updates)
        self.menu.add_command(label="How I work", command=self.show_welcome)
        self.menu.add_command(label="Test the reels mission", command=self.test_mission)
        self.menu.add_separator()
        self.menu.add_command(label=f"Charles v{VERSION}", state="disabled")
        self.menu.add_command(label="Bye Charles (quit)", command=self.quit)

    def set_look(self, key):
        old_size = self.settings["size"]
        self.settings[key] = self.vars[key].get()
        if self.settings["size"] != old_size:
            bottom = self.y + self.H
            self.apply_size()
            self.y = bottom - self.H
        self.save_settings()
        self.say("how do I look?", 2)

    def set_rule(self, key):
        val = self.vars[key].get()
        self.settings[key] = val if key == "action" else int(val)
        self.save_settings()
        self.unblock()
        self.warned = False
        lm, ws, act = (self.settings[k] for k in ("limit_minutes", "warning_seconds", "action"))
        then = {"close": "I close it", "block": "no more scrolling", "nag": "I tell you off"}[act]
        self.say(f"ok: {lm} min of reels, then {then}", 3.5)

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def toggle_startup(self, on=None):
        on = self.startup_var.get() if on is None else on
        if set_startup(on):
            self.say("see you every morning :3" if on else "fine. call me when you need me.", 2.5)
        else:
            self.say("hm, Windows said no", 2)
        self.startup_var.set(in_startup())

    def toggle_desktop_icon(self, on=None):
        on = self.desktop_var.get() if on is None else on
        if set_desktop_icon(on):
            self.say("look, it's me! on your desktop!" if on else "ok, no more desktop me.", 2.5)
        else:
            self.say("hm, Windows said no", 2)
        self.desktop_var.set(has_desktop_icon())

    def toggle_updates(self, on=None):
        on = self.updates_var.get() if on is None else on
        self.settings["check_updates"] = on
        self.updates_var.set(on)
        self.save_settings()
        if on:
            self.updater.check_soon()
            self.say("ok! I'll peek at GitHub once a day for a newer me", 3)
        else:
            self.say("ok, no update checks.", 2)

    def check_updater(self):
        """Offer a newer version once it's found, and say how an update's going."""
        u = self.updater
        if not u or self.state.startswith("mission"):
            return
        if u.found and not self.update_offered:
            self.update_offered = True
            self.menu.insert_command(1, label=f"Update me to v{u.found['version']}", command=u.install)
            self.say(f"a new me is out! (v{u.found['version']}) right-click me → Update me", 7)
        if u.message:
            self.say(u.message, 5)
            u.message = None
        elif u.busy and u.progress is not None and time.time() > self.bubble_until - 0.3:
            self.say(f"fetching the new me... {int(u.progress * 100)}%", 1)

    def show_welcome(self):
        if self.welcome is None:
            self.welcome = Welcome(self)

    def welcome_closed(self):
        self.welcome = None
        if not self.settings["welcomed"] or self.settings["check_updates"] is None:
            self.settings["welcomed"] = True
            self.settings["check_updates"] = bool(self.settings["check_updates"])
            self.save_settings()
        if self.state in ("idle", "sleep", "wave", "knead", "happy"):
            self.pose = "sit"
            self.say("ok! let's be friends :3", 3)
            self.set_state("wave", 2.4)

    def screen_under(self):
        """Work area of the monitor her feet are on."""
        return work_area(self.x + self.W / 2, self.y + self.H - FOOT * self.s)

    def check_screen(self):
        """Resolution changes, docking, a moved taskbar: keep her on a real floor."""
        if self.state in HANG_STATES or self.state in ("held", "fall", "mission_go", "mission_prep"):
            return
        wa = self.screen_under()
        if wa == self.wa:
            return
        self.wa = wa
        self.x = min(max(self.x, wa[0]), wa[2] - self.W)
        self.y = min(self.y, self.floor())
        self.vy = 0
        self.set_state("fall")

    def floor(self):
        return self.wa[3] - self.H + int((FOOT - 6) * self.s)

    def say(self, text, secs=2.5):
        self.bubble = text
        self.bubble_until = time.time() + secs

    def set_state(self, s, secs=None):
        if s != "butterfly":
            self.bf = None  # an interrupted chase shouldn't leave her head tilted up
        self.state = s
        self.state_until = time.time() + (secs if secs is not None else 9999)

    def walk_to(self, tx, ty=None, speed=1.6, state="walk"):
        self.target = (tx, ty if ty is not None else self.floor())
        self.speed = speed * self.s
        self.facing = 1 if tx > self.x else -1
        self.set_state(state)

    # ---------------- mouse
    def on_press(self, e):
        self.drag = (e.x_root, e.y_root, self.x, self.y, False)

    def on_drag(self, e):
        if not self.drag or self.state.startswith("mission"):
            return
        sx, sy, ox, oy, moved = self.drag
        if moved or abs(e.x_root - sx) + abs(e.y_root - sy) > 6:
            self.drag = (sx, sy, ox, oy, True)
            nx, ny = ox + e.x_root - sx, oy + e.y_root - sy
            # shaking her around winds up the dizzy meter; sharp direction changes count extra
            vx, vy = nx - self.x, ny - self.y
            self.spin += math.hypot(vx, vy)
            if vx * self.last_drag_v[0] + vy * self.last_drag_v[1] < 0:
                self.spin += 45 * self.s
            self.last_drag_v = (vx, vy)
            if self.spin > 900 * self.s:
                self.dizzy_pending = True
            self.x, self.y = nx, ny
            if self.state != "held":
                self.set_state("held")
                self.say(random.choice(["put me down!!", "hey!", "wheee?"]), 1.5)
            elif self.dizzy_pending and self.bubble not in DIZZY_LINES:
                self.say(random.choice(DIZZY_LINES), 2)

    def on_release(self, e):
        if not self.drag:
            return
        moved = self.drag[4]
        self.drag = None
        if moved:
            self.vy = 0
            self.wa = self.screen_under()  # dropped on another monitor: land on its floor
            self.set_state("fall")
        else:
            self.poke()

    def on_menu(self, e):
        m, s = divmod(int(self.reels_secs), 60)
        lm, ls = divmod(self.limit(), 60)
        label = f"Reels timer: {m}:{s:02d} / {lm}:{ls:02d}" + (" (test)" if self.testing else "")
        self.menu.entryconfigure(0, label=label)
        self.menu.tk_popup(e.x_root, e.y_root)

    def poke(self):
        if self.state.startswith("mission"):
            self.say("not now, I'm busy", 1.5)
            return
        now = time.time()
        self.pokes = [p for p in self.pokes if now - p < 6] + [now]
        self.pet = 0
        if len(self.pokes) >= 5:
            self.pokes = []
            self.say("that's it. I'm leaving.", 2.5)
            mid = (self.wa[0] + self.wa[2]) / 2
            far = self.wa[0] + 40 if self.x > mid else self.wa[2] - self.W - 40
            self.walk_to(far, speed=7, state="storm")
            return
        self.say("!!! who woke me" if self.state == "sleep" else random.choice(POKE_LINES), 2)
        self.set_state("angry", 2.2)

    def check_petting(self):
        cx, cy = cursor_pos()
        moved = math.dist((cx, cy), self.last_cursor)
        self.last_cursor = (cx, cy)
        self.pet = max(0.0, self.pet - 3)
        if self.state not in ("idle", "walk", "happy", "knead", "wave") or \
                user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            return
        bx, by = self.x + self.W / 2, self.y + self.H - FOOT * self.s
        if abs(cx - bx) < 70 * self.s and by - 125 * self.s < cy < by and 1 < moved < 60:
            self.pet += moved
            if self.pet > 350 and self.state != "happy":
                self.say(random.choice(PET_LINES), 2.5)
                self.set_state("happy", 2.5)
            elif self.state == "happy":
                self.state_until = time.time() + 1.5

    def test_mission(self):
        # Stays armed until she's closed something: leave and come back as often as you like.
        self.testing = True
        self.reels_secs = 0
        self.away_secs = 0
        self.warned = False
        self.unblock()
        self.say("ok, 20 seconds of reels and I'm coming for it", 4)

    def limit(self):
        if self.testing or TEST_MODE:
            return TEST_LIMIT
        return max(1, int(self.settings["limit_minutes"])) * 60

    def warn_at(self):
        limit = self.limit()
        if self.testing or TEST_MODE:
            return limit - 10
        warn = int(self.settings["warning_seconds"])
        return limit - warn if 0 < warn < limit else None

    def quit(self):
        self.root.destroy()
        os._exit(0)

    # ---------------- reels logic (runs once per tick)
    def track_reels(self, dt):
        hwnd, is_browser, sure = self.watcher.seen
        if hwnd and (self.testing or self.watcher.scrolling()):
            self.reels_secs += dt
            self.away_secs = 0
        elif not hwnd and not self.testing:
            self.away_secs += dt
            if self.away_secs > FORGET_AFTER:
                self.reels_secs = 0
                self.warned = False
                self.unblock()

        if self.watcher.blocking and time.time() - self.watcher.blocked_at < 0.2 and \
                time.time() > self.bubble_until and not self.state.startswith("mission"):
            self.say(random.choice(["nope.", "no more scrolling.", "I said no.", "*sits on scroll wheel*"]), 2)
            self.set_state("angry", 1.5)

        if self.state.startswith("mission") or self.state == "held" or self.watcher.blocking:
            return
        warn_at = self.warn_at()
        if not self.warned and warn_at is not None and self.reels_secs >= warn_at and hwnd:
            self.warned = True
            left = self.limit() - warn_at
            self.say(f"{left} more seconds..." if left < 60 else
                     "one more minute of reels..." if left == 60 else f"{left // 60} more minutes of reels...", 4)
        if self.reels_secs >= self.limit() and hwnd:
            self.intervene(hwnd, is_browser, sure)

    def intervene(self, hwnd, is_browser, sure):
        action = "close" if self.testing else self.settings["action"]
        if action == "nag":
            self.reels_secs = 0
            self.warned = False
            self.say(random.choice(["that's enough reels.", "go touch grass :3", "time's up, scroller."]), 4)
            self.set_state("angry", 3)
        elif action == "block":
            self.block(hwnd, "that's enough. no more scrolling.")
        elif is_browser and not sure:
            # Couldn't read the address bar, so we can't tell which tab is reels.
            self.cant_close(hwnd)
        else:
            self.start_mission(hwnd, is_browser)

    def block(self, hwnd, line):
        """Swallow scrolling in every reels window (not just this one, or a new window
        would get around it) until you've been away from reels for a while."""
        self.watcher.blocking = True
        self.testing = False
        self.say(line, 4)
        l, t, r, b = window_rect(hwnd)
        lo, hi = self.wa[0], self.wa[2] - self.W
        self.walk_to(min(max((l + r) / 2 - self.W / 2, lo), hi), speed=7, state="storm")

    def unblock(self):
        self.watcher.blocking = False

    def cant_close(self, hwnd):
        """Graceful failure: never guess. Block scrolling there instead and say why."""
        self.mission_hwnd = None
        self.reels_secs = 0
        if hwnd and user32.IsWindow(hwnd):
            self.block(hwnd, "I can't tell which tab is the reels one, so I won't close anything. "
                             "no more scrolling though.")
        else:
            self.say("I couldn't find the reels to close. please close it yourself!", 5)
            self.set_state("angry", 3)

    def start_mission(self, hwnd, is_browser):
        self.mission_hwnd, self.mission_browser = hwnd, is_browser
        self.job = self.watcher.submit(self.watcher.find_tab, hwnd) if is_browser else None
        self.say("okay. that's enough reels.", 3)
        self.set_state("mission_prep", 3.5)

    def plan_jump(self):
        """Work out where the tab's X is and run underneath it.
        Returns False (and backs off) if we couldn't find the exact tab."""
        hwnd = self.mission_hwnd
        l, t, r, b = window_rect(hwnd)
        found = self.job["result"] if self.job and self.job["done"] else None
        self.job = None
        if found:
            px, py = found["x"], found["y"]
        elif self.mission_browser:
            self.cant_close(hwnd)
            return
        else:
            px, py = r - 24, max(t, 0) + 16       # the app's own close button
        cxw = self.x + self.W / 2
        self.facing = 1 if px >= cxw else -1
        hx = px - self.W / 2 - PAW[0] * self.s * self.facing
        hy = py - (self.H - FOOT * self.s) - PAW[1] * self.s
        self.hang_pos = (hx, hy)
        self.hang_facing = self.facing
        self.walk_to(min(max(hx, self.wa[0] - self.W / 3), self.wa[2] - self.W * 2 / 3), speed=8,
                     state="mission_go")

    def still_reels(self):
        hwnd = self.mission_hwnd
        return bool(hwnd) and self.watcher.seen[0] == hwnd and user32.IsWindow(hwnd)

    def close_target(self):
        """Swat landed: close just that tab (or the reels app)."""
        hwnd = self.mission_hwnd
        self.reels_secs = 0
        self.warned = False
        if not self.still_reels():
            self.land_msg = "oh, you stopped? ...good."
            self.set_state("mission_letgo", 0.4)
            return
        self.testing = False
        if self.mission_browser:
            self.job = self.watcher.submit(self.watcher.close_tab, hwnd)
            self.set_state("mission_closing", 8)
            return
        if window_exe(hwnd) in BROWSERS:  # never close a whole browser window
            self.watcher.blocking = True
            self.land_msg = "I couldn't close it safely, so no more scrolling there instead."
            self.set_state("mission_letgo", 0.5)
            return
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self.land_msg = random.choice(DONE_LINES)
        self.set_state("mission_letgo", 0.5)

    def end_mission(self):
        self.mission_hwnd = None
        self.vy = 0
        self.wa = self.screen_under()  # the tab may have been on another monitor
        self.set_state("fall")

    # ---------------- behaviour
    def pick_walk(self):
        """Mostly pottering about the bottom-right corner, sometimes a longer stroll."""
        lo, hi = self.wa[0], self.wa[2] - self.W
        zone = max(lo, self.wa[2] - max(560 * self.s, (self.wa[2] - self.wa[0]) * 0.3))
        if random.random() < 0.12:
            return random.uniform(lo, hi)
        if self.x < zone:
            return random.uniform(zone, hi)
        return min(max(self.x + random.uniform(-300, 300) * self.s, zone), hi)

    def update(self, dt):
        now = time.time()
        st = self.state
        self.spin *= 0.93

        if st in ("walk", "storm", "mission_go"):
            tx, ty = self.target
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            self.phase += self.speed * 0.11 / self.s
            if dist <= self.speed:
                self.x, self.y = tx, ty
                if st == "mission_go":
                    self.facing = self.hang_facing
                    self.jump_from = (self.x, self.y)
                    self.jump_t0 = now
                    self.jump_dur = 0.45 + math.dist(self.jump_from, self.hang_pos) / 2600
                    self.set_state("mission_jump")
                elif st == "storm":
                    self.pose = "sit"
                    self.set_state("angry", 3)
                    if now > self.bubble_until:
                        self.say("hmph.", 3)
                else:
                    self.pose = random.choice(["sit", "stand"])
                    self.set_state("idle", random.uniform(4, 9))
            else:
                self.x += dx / dist * self.speed
                self.y += dy / dist * self.speed
                if abs(dx) > 1:
                    self.facing = 1 if dx > 0 else -1

        elif st == "mission_prep":
            if (self.job is None or self.job["done"]) or now > self.state_until:
                if self.still_reels():
                    self.plan_jump()
                else:
                    self.mission_hwnd = None
                    self.say("oh, you stopped? ...good.", 3)
                    self.reels_secs = 0
                    self.set_state("idle", 4)

        elif st == "mission_jump":
            u = min(1.0, (now - self.jump_t0) / self.jump_dur)
            e = 1 - (1 - u) ** 2
            (fx, fy), (tx, ty) = self.jump_from, self.hang_pos
            self.x = fx + (tx - fx) * e
            self.y = fy + (ty - fy) * e - math.sin(math.pi * u) * 90 * self.s
            if u >= 1:
                self.set_state("mission_hang", 0.7)

        elif st == "mission_hang" and now > self.state_until:
            self.set_state("mission_swipe", 0.9)
        elif st == "mission_swipe" and now > self.state_until:
            self.close_target()
        elif st == "mission_closing":
            result = self.job["result"] if self.job and self.job["done"] else None
            if result or now > self.state_until:
                self.job = None
                if result == "closed":
                    self.land_msg = random.choice(DONE_LINES)
                elif result == "gone":
                    self.land_msg = "oh, you stopped? ...good."
                else:  # couldn't verify the tab, so nothing was closed
                    self.watcher.blocking = True
                    self.land_msg = "I couldn't close it safely, so no more scrolling there instead."
                self.set_state("mission_letgo", 0.5)
        elif st == "mission_letgo" and now > self.state_until:
            self.end_mission()

        elif st == "fall":
            self.vy += 1.4 * self.s
            self.y += self.vy
            if self.y >= self.floor():
                self.y = self.floor()
                self.pose = "stand"
                self.sq = -0.22
                if self.dizzy_pending:
                    self.dizzy_pending = False
                    self.set_state("dizzy", 4.5)
                    self.say(random.choice(DIZZY_LINES), 3)
                else:
                    self.set_state("idle", random.uniform(3, 6))
                    self.say(self.land_msg or "hmph.", 4 if self.land_msg else 1.5)
                    lo, hi = self.wa[0], self.wa[2] - self.W
                    if not lo <= self.x <= hi:  # dropped half off the screen: come back on
                        self.walk_to(min(max(self.x, lo), hi))
                self.land_msg = None

        elif st == "dizzy":
            lo, hi = self.wa[0], self.wa[2] - self.W
            self.x = min(max(self.x + math.sin(self.t * 2.3) * 1.3 * self.s, lo), hi)
            if now > self.state_until:
                self.set_state("idle", 4)
                self.say("...what happened?", 2.5)

        elif st in ("angry", "happy") and now > self.state_until:
            self.set_state("idle", random.uniform(3, 6))

        elif st == "sleep" and now > self.state_until:
            self.pose = "sit"
            self.set_state("idle", 4)
            self.say("*yawn*", 2)

        elif st in ("knead", "wave") and now > self.state_until:
            self.set_state("idle", random.uniform(3, 6))

        elif st == "hop":
            u = (now - self.hop_t0) / 0.42
            n = int(u)
            if n != self.hop_n:
                self.hop_n = n
                self.sq = -0.18
            if n >= 2:
                self.hop_y = 0.0
                self.set_state("idle", random.uniform(3, 6))
            else:
                self.hop_y = math.sin(math.pi * (u % 1)) * 26

        elif st == "butterfly":
            bf = self.bf
            age = now - bf["t0"]
            if age > bf["swat"] and not bf["swatted"]:
                bf["swatted"] = True
                self.say(random.choice(BUTTERFLY_LINES), 1.5)
            if age > bf["swat"] + 1.6 or now > self.state_until:
                self.bf = None
                self.set_state("idle", random.uniform(3, 6))
                if random.random() < 0.5:
                    self.say("aww it got away", 2)

        elif st == "idle" and now > self.state_until:
            r = random.random()
            cx, cy = cursor_pos()
            near = math.dist((cx, cy), (self.x + self.W / 2, self.y + self.H / 2)) < 320 * self.s
            if r < 0.38:
                self.walk_to(self.pick_walk())
            elif r < 0.5:
                self.set_state("sleep", random.uniform(15, 40))
            elif r < 0.62:
                self.pose = "sit" if self.pose == "stand" else "stand"
                self.set_state("idle", random.uniform(4, 8))
            elif r < 0.71:
                self.pose = "sit"
                self.set_state("knead", random.uniform(4, 7))
                self.say(random.choice(KNEAD_LINES), 2.5)
            elif r < 0.8:
                self.pose = "sit"
                self.bf = {"t0": now, "swat": random.uniform(3.5, 5), "swatted": False,
                           "col": random.choice(["#f7a8c4", "#a9c9f5", "#f8d27a", "#bfa8f2"]),
                           "seed": random.uniform(0, 6)}
                self.set_state("butterfly", 9)
            elif r < 0.87:
                self.pose = "stand"
                self.hop_t0, self.hop_n = now, 0
                self.sq = 0.12
                self.set_state("hop", 2)
            elif r < 0.93 and near:
                self.pose = "sit"
                self.say(random.choice(WAVE_LINES), 2)
                self.set_state("wave", 2.2)
            else:
                self.say(random.choice(IDLE_LINES), 2)
                self.set_state("idle", random.uniform(4, 8))

        if now > self.blink_at + 0.14:
            # sometimes a double blink
            self.blink_at = now + (0.3 if random.random() < 0.25 else random.uniform(2.5, 6))
        self.update_anim(dt)

    def update_anim(self, dt):
        """Springy squash/stretch, wandering glances, ear flicks."""
        now = time.time()
        dt = min(dt, 0.1)
        self.sqv += (-self.sq * 170 - self.sqv * 11) * dt
        self.sq += self.sqv * dt
        if now > self.twitch_at:
            self.twitch_t0 = now
            self.twitch_at = now + random.uniform(3, 9)
        if now > self.glance_at:
            self.glance = random.choice([(0, 0), (0, 0), (1, 0), (-1, 0.3), (0.6, -0.6)])
            self.glance_at = now + random.uniform(1.5, 4)

    # ---------------- rendering
    def draw_body(self, P, pose, flags):
        """Paints the whole silhouette with P.col; returns the head centre."""
        st, t, now = self.state, self.t, time.time()
        angry, moving, held, happy = flags
        if pose == "loaf":
            br = math.sin(t * 2) * 1.2
            P.rrect(-56, -46 - br, 46, 0, 23)
            hx, hy = 34, -42 - br * 0.6
            P.ellipse(hx, hy, 31, 27)
            P.ears(hx, hy, tilt=-2)
            P.tube([(-50, -8), (-36, -1), (0, -3), (22, -6)], 7)
            return hx, hy
        if pose == "sit":
            sway = math.sin(t * 1.6) * 4
            P.tube([(-30, -9), (-62, -8), (-48, -7), (-6 + sway, -7)], 7)
            P.ellipse(-16, -26, 34, 26)
            P.ellipse(4, -52, 27, 36)
            for i, lx in enumerate((10, 25)):
                if i == 1 and self.paw_tip:
                    continue  # that paw is up (waving / swatting), drawn over the face later
                ey = -7.5
                if st == "knead":
                    ey -= max(0.0, math.sin(t * 7 + i * math.pi)) * 6
                P.tube([(lx, -40), (lx, ey)], 7.5)
            hx, hy = 16, -98 + (3 if happy else 0)
            if st == "knead":
                hy += math.sin(t * 14) * 0.8
            if self.bf:  # head up a touch, watching the butterfly
                hy -= 2
            P.ellipse(hx, hy, 33, 29)
            P.ears(hx, hy, tilt=2 if happy else 0)
            return hx, hy

        hang = st in HANG_STATES
        lift = 9 if angry else 0
        legs = [-42, -26, 20, 36]
        bob = -abs(math.sin(self.phase)) * 2.5 if moving else 0.0
        for i, lx in enumerate(legs):
            if held:
                ex, ey = lx * 1.05 + math.sin(t * 7 + i) * 3, 2 + math.sin(t * 7 + i * 2) * 3
            elif moving:
                sw = math.sin(self.phase + (0 if i in (0, 3) else math.pi))
                ex, ey = lx + sw * 7, -7.5 - max(0.0, sw) * 5
            else:
                ex, ey = lx, -7.5
            if hang and i >= 2:  # front paws up, hooked onto the tab
                ex, ey = (PAW[0] - 14, PAW[1] + 6) if i == 2 else PAW
                if i == 3 and st == "mission_swipe":
                    ey = PAW[1] - abs(math.sin(now * 11)) * 16
                P.tube([(lx, -58), (ex, ey)], 8)
                continue
            P.tube([(lx, -36 - lift + bob), (ex, ey)], 8)
        by = -lift + bob
        P.rrect(-58, -80 + by, 48, -28 + by, 26)
        if angry:
            P.ellipse(-8, -78 + by, 42, 18)
            for i in range(9):  # puffed-up fluff along the back
                a = math.pi * (1.05 + i * 0.11)
                P.ellipse(-8 + math.cos(a) * 46, -66 + by + math.sin(a) * 26, 7, 7)
            P.tube([(-54, -60 + by), (-64, -86 + by), (-62, -116 + by),
                    (-58 + math.sin(t * 30) * 1.5, -134 + by)], 11)
        elif happy:
            P.tube([(-54, -60 + by), (-66, -88 + by), (-64, -118 + by), (-44, -122 + by)], 7.5)
        elif hang:
            P.tube([(-54, -60), (-68, -40), (-62, -14), (-56 + math.sin(t * 3) * 6, 6)], 7.5)
        else:
            sway = math.sin(t * (6 if moving else 2.2)) * (6 if moving else 9)
            P.tube([(-54, -60 + by), (-76, -62 + by), (-82, -92 + by), (-70 + sway, -112 + by)], 7.5)
        hx, hy = 40, -78 + by + (math.sin(self.phase * 2) if moving else 0)
        P.ellipse(hx, hy, 33, 29)
        P.ears(hx, hy, tilt=-3 if angry else 0)
        return hx, hy

    def render(self):
        st, t, now, s = self.state, self.t, time.time(), self.s
        fur, ink, blush = COATS.get(self.settings["coat"], COATS["Mochi (white)"])
        angry = st in ("angry", "storm")
        moving = st in ("walk", "storm", "mission_go")
        hang = st in HANG_STATES
        held = st in ("held", "fall") or hang
        fierce = angry or st == "mission_swipe"
        dizzy = st == "dizzy" or (st in ("held", "fall") and self.spin > 500 * s)
        happy = st == "happy"
        if st in ("knead", "wave", "butterfly"):
            pose = "sit"
        elif st == "hop":
            pose = "stand"
        else:
            pose = "loaf" if st == "sleep" else "sit" if (st in ("idle", "happy") and self.pose == "sit") else "stand"
        flags = (angry, moving, held, happy)

        # where the butterfly is (cat-local units), and the raised paw
        bfp = None
        self.paw_tip = None
        if st == "butterfly" and self.bf:
            bf = self.bf
            age = now - bf["t0"]
            sd = bf["seed"]
            bx = 72 + math.sin(age * 1.3 + sd) * 26
            by = -150 + math.sin(age * 2.3 + sd) * 12
            if age > bf["swat"]:  # she swatted: it zips off up and away
                e = age - bf["swat"]
                bx += e * 70
                by -= e * e * 60
            bfp = (bx, by)
            sw = age - bf["swat"]
            if -0.6 < sw < 0.5:
                reach = math.sin(math.pi * (sw + 0.6) / 1.1)
                self.paw_tip = (34 + reach * 38, -60 - reach * 52)
        elif st == "wave":
            self.paw_tip = (64 + math.sin(t * 11) * 6, -100 + abs(math.cos(t * 11)) * 3)

        # squash & stretch (springy landings, breathing)
        breathe = math.sin(t * 2.4) * 0.012 if st in ("idle", "knead", "wave", "butterfly", "happy") else 0.0
        if st == "happy":
            breathe += math.sin(t * 40) * 0.006  # purring rumble
        sq = 0.0 if hang else self.sq + breathe
        hop_y = self.hop_y if st == "hop" else 0.0

        w, h = self.W * SS, self.H * SS
        k = s * SS
        cx, gy = self.W / 2, self.H - FOOT * s
        if angry:
            cx += random.uniform(-1.2, 1.2)
        if st == "dizzy":
            cx += math.sin(t * 5) * 3 * s

        frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(frame)
        if not held:
            sw = (52 if pose != "sit" else 40) * k * (1 - hop_y / 80)
            d.ellipse((cx * SS - sw, gy * SS - 5 * k, cx * SS + sw, gy * SS + 5 * k), fill=(0, 0, 0, 34))

        # body twice: a slightly bigger, darker pass first gives her a soft rim
        P = Painter(frame, s, self.facing, cx, gy - hop_y * s)
        P.kx, P.ky = 1 - sq * 0.5, 1 + sq
        tw = now - self.twitch_t0
        P.twitch = math.sin(tw * 30) * 5 * (1 - tw / 0.35) if tw < 0.35 else 0.0
        P.g, P.col = 1.0, shade(fur, 0.8)
        self.draw_body(P, pose, flags)
        P.g, P.col = 0.0, fur
        hx, hy = self.draw_body(P, pose, flags)
        P.inner_ears(mix(fur, blush, 0.75))

        # pupils follow the cursor (or the butterfly) when it's close
        hpx0, hpy0 = P.p(hx, hy)
        if bfp:
            tx, ty = P.p(*bfp)
            tx, ty = self.x + tx / SS, self.y + ty / SS
        else:
            tx, ty = cursor_pos()
        hsx, hsy = self.x + hpx0 / SS, self.y + hpy0 / SS
        dist = math.hypot(tx - hsx, ty - hsy)
        if bfp or 20 * s < dist < 420 * s:
            want = ((tx - hsx) / dist * self.facing, (ty - hsy) / dist)
        else:
            want = self.glance
        for i in (0, 1):
            self.look[i] += (want[i] - self.look[i]) * 0.25
        lx, ly = self.look[0] * 1.4, self.look[1] * 1.1

        # face
        ex1, ex2, ey, mx = hx + 5, hx + 23, hy + 1, hx + 14
        if pose == "loaf":
            for ex in (ex1, ex2):
                P.arc(ex, ey - 1, 3.6, 20, 160, 1.6, ink)
        elif dizzy:
            for ex in (ex1, ex2):
                pts = [(ex + math.cos(a + t * 9) * (0.3 + a * 0.36), ey + math.sin(a + t * 9) * (0.3 + a * 0.36))
                       for a in [i * 0.35 for i in range(32)]]
                P.stroke(pts, 1.2, ink)
        elif fierce:
            for ex, dd in ((ex1, 1), (ex2, -1)):
                P.stroke([(ex - 3.5 * dd, ey - 3.5), (ex + 2.5 * dd, ey), (ex - 3.5 * dd, ey + 3.5)], 1.8, ink)
        elif happy:
            for ex in (ex1, ex2):
                P.arc(ex, ey + 2, 3.6, 200, 340, 1.8, ink)
        elif now > self.blink_at:
            for ex in (ex1, ex2):
                P.stroke([(ex - 3.4, ey), (ex + 3.4, ey)], 1.6, ink)
        else:
            # big sparkly eyes
            r = 5.3 if held else 4.5
            shine = "#ffffff" if ink[1:3] < "80" else "#2b2926"
            for ex in (ex1, ex2):
                P.ellipse(ex + lx * 0.4, ey + ly * 0.4, r, r * 1.12, ink)
                P.ellipse(ex + 1.5 + lx, ey - 1.7 + ly, r * 0.36, r * 0.36, shine)
                P.ellipse(ex - 1.4 + lx, ey + 1.8 + ly, r * 0.15, r * 0.15, shine)
        # blush (always a little, more when she's happy)
        cheek = mix(fur, blush, 0.85 if (happy or held or pose == "loaf" or st == "knead") else 0.45)
        for ex in (ex1 - 5, ex2 + 5):
            P.ellipse(ex, ey + 7, 4.2, 2.5, cheek)
        P.ellipse(mx, ey + 4.2, 2.0, 1.4, mix(blush, ink, 0.25))  # tiny nose
        if fierce:
            P.ellipse(mx, ey + 8.5, 2.8, 2.4, ink)
        elif held:
            P.ellipse(mx, ey + 8.5, 2.0, 2.4, ink)
        else:
            P.arc(mx - 2.1, ey + 6, 2.1, 10, 170, 1.4, ink)
            P.arc(mx + 2.1, ey + 6, 2.1, 10, 170, 1.4, ink)
        whisk = mix(fur, ink, 0.45)
        P.stroke([(hx + 29, ey + 4), (hx + 42, ey + 1.5)], 0.8, whisk)
        P.stroke([(hx + 29, ey + 7), (hx + 42, ey + 8.5)], 0.8, whisk)

        # the raised paw goes over her cheek, with a toe bean
        if self.paw_tip:
            for g, col in ((1.0, shade(fur, 0.8)), (0.0, fur)):
                P.g, P.col = g, col
                P.tube([(26, -50), self.paw_tip], 7.5)
            P.g = 0.0
            P.ellipse(self.paw_tip[0] + 1, self.paw_tip[1] - 1, 2.6, 2.2, mix(fur, blush, 0.8))
        if bfp:
            bx, by = P.p(*bfp)
            butterfly(d, bx, by, 9.5 * k, abs(math.sin(t * 16)), self.bf["col"])

        hpx, hpy = P.p(hx, hy)
        if dizzy:  # little stars circling her head
            for i in range(3):
                a = t * 4 + i * 2.094
                sx, sy = P.p(hx + math.cos(a) * 28, hy - 36 + math.sin(a) * 6)
                pts = [(sx + math.cos(j * math.pi / 5 - math.pi / 2) * (5 if j % 2 == 0 else 2.2) * k,
                        sy + math.sin(j * math.pi / 5 - math.pi / 2) * (5 if j % 2 == 0 else 2.2) * k)
                       for j in range(10)]
                d.polygon(pts, fill="#f6c945")
        if fierce:  # little anger mark
            ax, ay = hpx + 30 * k * self.facing, hpy - 30 * k
            for (dx, dy), a0 in (((-1, -1), 0), ((1, -1), 90), ((1, 1), 180), ((-1, 1), 270)):
                ox, oy, rr = ax + dx * 7 * k, ay + dy * 7 * k, 5.5 * k
                d.arc((ox - rr, oy - rr, ox + rr, oy + rr), a0 - 5, a0 + 95, fill="#e0574f",
                      width=max(1, int(2.2 * k)))
        if pose == "loaf":
            for i in range(3):
                ph = (t * 0.5 + i / 3) % 1
                d.text((hpx + (22 + ph * 26) * k * self.facing, hpy - (16 + ph * 36) * k), "z",
                       font=self.zfont, fill=(150, 160, 190, int(255 * (1 - ph))), anchor="mm")
        if st == "knead" or happy:
            for i in range(2):
                ph = (t * 0.45 + i / 2) % 1
                note(d, hpx - (30 + ph * 14) * k * self.facing, hpy - (24 + ph * 34) * k, 4 * k,
                     (150, 140, 175, int(230 * (1 - ph))))
        if happy:
            for i in range(3):
                ph = (t * 0.7 + i / 3) % 1
                heart(d, hpx + (-14 + i * 14) * k, hpy - (30 + ph * 30) * k, 5 * k,
                      shade(blush, 1.0) + (int(255 * (1 - ph)),))
        if st == "mission_go":
            d.text((hpx, hpy - 46 * k), "!", font=self.font, fill="#e0574f", anchor="mm")
        if st == "mission_swipe":
            px, py = P.p(*PAW)
            for i in (-1, 0, 1):
                d.line((px + i * 9 * k, py - 14 * k, px + i * 13 * k, py - 22 * k), fill="#e0574f",
                       width=int(2 * k))

        if self.bubble and now < self.bubble_until:
            self.draw_bubble(d, self.bubble, hpx, hpy - 36 * k, "#2b2926")

        return to_bgra(frame, SS)

    def draw_bubble(self, d, text, ax, ay, ink):
        k = self.s * SS
        maxw = (self.W - 24 * self.s) * SS
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if d.textlength(trial, font=self.font) > maxw - 24 * k and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
        txt = "\n".join(lines)
        x1, y1, x2, y2 = d.multiline_textbbox((0, 0), txt, font=self.font, spacing=2 * k)
        tw, th = x2 - x1, y2 - y1
        bw, bh = tw + 22 * k, th + 14 * k
        W = self.W * SS
        bx = min(max(ax - bw / 2, 4 * k), W - bw - 4 * k)
        by = max(4 * k, ay - bh - 10 * k)
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=12 * k, fill="#fffdf8",
                            outline="#d8d3c6", width=int(1.5 * k))
        tx = min(max(ax, bx + 16 * k), bx + bw - 16 * k)
        d.polygon([(tx - 7 * k, by + bh - 1.5 * k), (tx + 7 * k, by + bh - 1.5 * k), (tx, by + bh + 8 * k)],
                  fill="#fffdf8")
        d.line([(tx - 7 * k, by + bh), (tx, by + bh + 8 * k), (tx + 7 * k, by + bh)], fill="#d8d3c6",
               width=int(1.5 * k))
        d.multiline_text((bx + 11 * k - x1, by + 7 * k - y1), txt, font=self.font, fill=ink,
                         spacing=2 * k, align="center")

    def present(self, data):
        self.surface.show(data, self.x, self.y)

    # ---------------- main loop
    def loop(self):
        if QUIT_EVENT and kernel32.WaitForSingleObject(QUIT_EVENT, 0) == 0:
            self.quit()  # another Charles (probably a newer one) is taking over
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        self.t += dt
        if now > self.screen_check_at:
            self.screen_check_at = now + 1
            self.check_screen()
        self.track_reels(dt)
        self.check_updater()
        self.check_petting()
        self.update(dt)
        self.present(self.render())
        self.root.after(self.frame_ms(), self.loop)

    def frame_ms(self):
        """30fps while anything's happening; drawing is the expensive part, so she
        breathes and naps at a lower rate when nobody's near her."""
        if self.state not in ("idle", "sleep"):
            return 33
        cx, cy = cursor_pos()
        if self.x - 40 < cx < self.x + self.W + 40 and self.y - 40 < cy < self.y + self.H + 40:
            return 33  # she's watching your cursor, or being petted
        return 100 if self.state == "sleep" else 66


# ---------------------------------------------------------------- first-run tutorial
class Welcome:
    """The tutorial she shows the first time: what she does, the reels rule, and buttons for
    a desktop icon and starting with Windows. Drawn with Pillow into a layered window, like her."""

    W, H, M = 640, 480, 28        # logical size, and the margin the card's soft shadow sits in
    R = 2                         # supersampling
    CREAM, CARD, CHOC, INK, SOFT = "#fff6ea", "#fffdf8", "#5b3a29", "#3b2a22", "#8a6b5a"
    PINK, BUTTER, SKY, MINT, LINE = "#f7a8c4", "#f8d27a", "#a9c9f5", "#b8e6cf", "#ecdccb"
    FONTS = {"regular": "segoeui.ttf", "semi": "seguisb.ttf", "bold": "segoeuib.ttf", "hand": "segoepr.ttf"}

    def __init__(self, cat):
        self.cat = cat
        self.u = UI_SCALE
        self.k = self.u * self.R
        self.pw, self.ph = int(self.W * self.u), int(self.H * self.u)
        wa = work_area()
        self.x, self.y = (wa[0] + wa[2] - self.pw) // 2, (wa[1] + wa[3] - self.ph) // 2
        self.win = tk.Toplevel(cat.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{self.pw}x{self.ph}+{self.x}+{self.y}")
        self.win.update_idletasks()
        self.surface = Surface(int(self.win.wm_frame(), 16))
        self.surface.resize(self.pw, self.ph)
        self.page, self.hover, self.pressed, self.drag, self.hits = 0, None, None, None, []
        self.fonts, self.pics, self.cache = {}, {}, {}
        self.desktop, self.startup = has_desktop_icon(), in_startup()
        self.updates = bool(cat.settings["check_updates"])
        self.pages = (self.page_hello, self.page_friends, self.page_rule, self.page_home)
        self.base = self.paint_base()
        self.data = self.render()
        self.alpha, self.closing = 0, False
        for ev, fn in (("<Motion>", self.on_move), ("<Leave>", self.on_leave),
                       ("<ButtonPress-1>", self.on_press), ("<B1-Motion>", self.on_drag),
                       ("<ButtonRelease-1>", self.on_release), ("<Key>", self.on_key)):
            self.win.bind(ev, fn)
        self.win.focus_force()
        self.fade(0, 1)

    # ---------------- drawing helpers (all in logical units)
    def box(self, *v):
        return tuple(x * self.k for x in v)

    def font(self, size, style="regular"):
        key = (size, style)
        if key not in self.fonts:
            try:
                self.fonts[key] = ImageFont.truetype(self.FONTS[style], int(size * self.k))
            except OSError:
                self.fonts[key] = ImageFont.truetype("segoeui.ttf", int(size * self.k))
        return self.fonts[key]

    def text(self, d, x, y, s, size, style="regular", fill=None, width=None, center=False):
        """Wrapped text, top-left (or top-centre) at x, y. Returns its height."""
        f = self.font(size, style)
        lines = []
        for para in s.split("\n"):
            cur = ""
            for word in para.split():
                trial = (cur + " " + word).strip()
                if width and cur and d.textlength(trial, font=f) > width * self.k:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        txt = "\n".join(lines)
        kw = dict(font=f, spacing=size * 0.28 * self.k, anchor="ma" if center else "la",
                  align="center" if center else "left")
        d.multiline_text((x * self.k, y * self.k), txt, fill=fill or self.INK, **kw)
        x1, y1, x2, y2 = d.multiline_textbbox((x * self.k, y * self.k), txt, **kw)
        return (y2 - y * self.k) / self.k

    def pic(self, img, name, cx, cy, w, h):
        """One of her poses, fitted into a w x h box centred on cx, cy."""
        key = (name, w, h)
        if key not in self.pics:
            try:
                p = Image.open(os.path.join(ASSETS, name + ".png")).convert("RGBA")
                p = p.crop(p.getbbox())
                f = min(w * self.k / p.width, h * self.k / p.height)
                self.pics[key] = p.resize((max(1, round(p.width * f)), max(1, round(p.height * f))), Image.LANCZOS)
            except OSError:
                self.pics[key] = None  # her pictures are missing: the words still work
        p = self.pics[key]
        if p:
            img.alpha_composite(p, (int(cx * self.k - p.width / 2), int(cy * self.k - p.height / 2)))

    def button(self, d, x1, y1, x2, y2, label, name, primary=True):
        hot = self.hover == name
        r = (y2 - y1) / 2 * self.k
        if primary:  # a chunky chocolate pill, like the website's
            d.rounded_rectangle(self.box(x1, y1 + 3, x2, y2 + 3), radius=r, fill="#3b2418")
            lift = -1 if hot else 0
            d.rounded_rectangle(self.box(x1, y1 + lift, x2, y2 + lift), radius=r,
                                fill="#6e4835" if hot else self.CHOC)
            fg, cy = self.CREAM, (y1 + y2) / 2 + lift
        else:
            if hot:
                d.rounded_rectangle(self.box(x1, y1, x2, y2), radius=r, fill="#f5e6d6")
            fg, cy = self.CHOC, (y1 + y2) / 2
        d.text(((x1 + x2) / 2 * self.k, cy * self.k), label, font=self.font(15, "semi"), fill=fg, anchor="mm")
        self.hits.append(((x1, y1, x2, y2 + 3), name))

    def heading(self, d, kicker, title, x=None, y=44):
        center = x is None
        x = self.W / 2 if center else x
        self.text(d, x, y, kicker, 16, "hand", fill="#d9779b", center=center)
        return y + 32 + self.text(d, x, y + 32, title, 30, "bold", fill=self.CHOC, center=center)

    def paint_base(self):
        """The card, its shadow and polka dots: the same on every page."""
        M, W, H = self.M, self.W, self.H
        size = (int(W * self.k), int(H * self.k))
        shadow = Image.new("L", size, 0)
        ImageDraw.Draw(shadow).rounded_rectangle(self.box(M + 4, M, W - M - 4, H - M + 6),
                                                 radius=30 * self.k, fill=90)
        img = Image.new("RGBA", size, (59, 36, 24, 0))
        img.putalpha(shadow.filter(ImageFilter.GaussianBlur(14 * self.k)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(self.box(M, M - 8, W - M, H - M - 4), radius=28 * self.k, fill=self.CREAM,
                            outline=self.LINE, width=max(1, int(1.5 * self.k)))
        for gy in range(M + 14, H - M - 14, 22):
            for gx in range(M + 16 + (gy // 22 % 2) * 11, W - M - 12, 22):
                d.ellipse(self.box(gx - 1.6, gy - 1.6, gx + 1.6, gy + 1.6), fill="#f7e8d6")
        return img

    def render(self):
        key = (self.page, self.hover, self.desktop, self.startup, self.updates)
        if key not in self.cache:
            img = self.base.copy()
            d = ImageDraw.Draw(img)
            self.hits = []
            self.pages[self.page](img, d)
            self.nav(d)
            self.cache[key] = (to_bgra(img, self.R), self.hits)
        data, self.hits = self.cache[key]
        return data

    def nav(self, d):
        W, y = self.W, self.H - self.M - 46
        if self.page:
            self.button(d, 58, y - 18, 148, y + 18, "← back", "back", primary=False)
        n = len(self.pages)
        for i in range(n):
            cx = W / 2 + (i - (n - 1) / 2) * 20
            if i == self.page:
                d.rounded_rectangle(self.box(cx - 10, y - 4, cx + 10, y + 4), radius=4 * self.k, fill=self.CHOC)
            else:
                d.ellipse(self.box(cx - 4, y - 4, cx + 4, y + 4), fill="#e6d2bf")
        last = self.page == n - 1
        self.button(d, W - 58 - (150 if last else 116), y - 20, W - 58, y + 18,
                    "let's go! :3" if last else "next  →", "next")
        cx, cy = W - self.M - 30, self.M + 18  # close (x)
        if self.hover == "close":
            d.ellipse(self.box(cx - 15, cy - 15, cx + 15, cy + 15), fill="#f5e6d6")
        for a, b in ((-5, 5), (5, -5)):
            d.line(self.box(cx - 5, cy + a, cx + 5, cy + b), fill=self.SOFT, width=max(1, int(2 * self.k)))
        self.hits.append(((cx - 16, cy - 16, cx + 16, cy + 16), "close"))

    # ---------------- the pages
    def page_hello(self, img, d):
        d.ellipse(self.box(76, 120, 304, 348), fill="#fde9b9")
        d.ellipse(self.box(84, 118, 104, 138), fill=self.PINK)
        d.ellipse(self.box(282, 326, 296, 340), fill=self.SKY)
        d.ellipse(self.box(292, 134, 302, 144), fill=self.MINT)
        self.pic(img, "wave", 190, 228, 230, 230)
        x, w = 336, 236
        self.text(d, x, 92, "welcome home", 16, "hand", fill="#d9779b")
        y = 120 + self.text(d, x, 120, "hi, I'm\nCharles!", 36, "bold", fill=self.CHOC) + 14
        y += self.text(d, x, y, "Charles Chocolate the Charles the IInd, if we're being formal. "
                       "I live at the bottom of your screen now.", 15, width=w) + 12
        self.text(d, x, y, "I nap, I knead, I chase butterflies, and I have one very important job.",
                  15, width=w)

    def page_friends(self, img, d):
        top = self.heading(d, "the basics", "how to be my friend") + 16
        items = [("happy", "wiggle your cursor on me", "I purr and make hearts", self.PINK),
                 ("angry", "click me", "I get very offended", self.BUTTER),
                 ("dizzy", "pick me up and shake", "I get dizzy. obviously.", self.SKY),
                 ("idle", "right-click me", "my menu: coats, sizes, reels rules", self.MINT)]
        tw, th, gap = 250, 112, 12
        x0 = (self.W - tw * 2 - gap) / 2
        for i, (name, title, sub, col) in enumerate(items):
            x1, y1 = x0 + (i % 2) * (tw + gap), top + (i // 2) * (th + gap)
            d.rounded_rectangle(self.box(x1, y1, x1 + tw, y1 + th), radius=20 * self.k, fill=self.CARD,
                                outline=self.LINE, width=max(1, int(1.2 * self.k)))
            d.rounded_rectangle(self.box(x1 + 9, y1 + 9, x1 + 99, y1 + th - 9), radius=15 * self.k,
                                fill=mix(col, "#ffffff", 0.45))
            self.pic(img, name, x1 + 54, y1 + th / 2, 82, th - 26)
            y = y1 + 22
            y += self.text(d, x1 + 112, y, title, 15, "bold", fill=self.CHOC, width=128) + 4
            self.text(d, x1 + 112, y, sub, 13, fill=self.SOFT, width=128)

    def page_rule(self, img, d):
        s = self.cat.settings
        lm, ws = int(s["limit_minutes"]), int(s["warning_seconds"])
        d.ellipse(self.box(66, 128, 270, 332), fill="#fcd9e6")
        d.ellipse(self.box(250, 140, 262, 152), fill=self.BUTTER)
        self.pic(img, "mission", 168, 236, 196, 190)
        x = 296
        y = self.heading(d, "my one job", "the reels rule", x=x, y=78) + 14

        def span(secs):
            return "a minute" if secs == 60 else f"{secs // 60} minutes" if secs % 60 == 0 else f"{secs} seconds"

        steps = [(self.PINK, f"you scroll Reels, Shorts or TikTok for {lm} minute{'s' * (lm != 1)}"),
                 (self.BUTTER, f"I warn you {span(ws)} before" if 0 < ws < lm * 60 else "(you turned my warning off)"),
                 (self.SKY, {"close": "I run over and swat the tab closed",
                             "block": "I sit on your scroll wheel. no more scrolling.",
                             "nag": "I tell you off. sternly."}[s["action"]])]
        for i, (col, line) in enumerate(steps):
            d.ellipse(self.box(x, y, x + 26, y + 26), fill=col)
            d.text(((x + 13) * self.k, (y + 13) * self.k), str(i + 1), font=self.font(13, "bold"),
                   fill=self.CHOC, anchor="mm")
            y += max(30, self.text(d, x + 38, y + 1, line, 15, width=232) + 12)
        self.text(d, x, y + 4, "change any of it:\nright-click me → Reels rules", 13, "hand",
                  fill=self.SOFT, width=290)

    def page_home(self, img, d):
        top = self.heading(d, "last thing!", "make yourself at home") + 18
        tiles = [("desktop", self.desktop, "desktop icon", "a little me to double-click", "add me", "added"),
                 ("startup", self.startup, "start with Windows", "I'll be here every morning", "turn on", "on")]
        if self.cat.updater:
            tiles.append(("updates", self.updates, "stay up to date",
                          "I peek at GitHub once a day for a newer me", "turn on", "on"))
        gap = 14 if len(tiles) == 3 else 20
        tw, th = (172 if len(tiles) == 3 else 228), 196
        x0 = (self.W - tw * len(tiles) - gap * (len(tiles) - 1)) / 2
        for i, (name, on, title, sub, off_label, on_label) in enumerate(tiles):
            x1, y1 = x0 + i * (tw + gap), top
            hot = self.hover == name
            lift = -2 if hot else 0
            d.rounded_rectangle(self.box(x1, y1 + 4, x1 + tw, y1 + th + 4), radius=22 * self.k,
                                fill="#efdfcf")
            d.rounded_rectangle(self.box(x1, y1 + lift, x1 + tw, y1 + th + lift), radius=22 * self.k,
                                fill="#e6f6ec" if on else self.CARD,
                                outline=self.MINT if on else ("#dcc3ad" if hot else self.LINE),
                                width=max(1, int(2 * self.k)))
            cx, cy = x1 + tw / 2, y1 + 46 + lift
            if name == "desktop":
                if "icon" not in self.pics:
                    self.pics["icon"] = portrait(int(58 * self.k))
                ic = self.pics["icon"]
                img.alpha_composite(ic, (int(cx * self.k - ic.width / 2), int(cy * self.k - ic.height / 2)))
            elif name == "startup":  # a little sun
                for j in range(8):
                    a = j * math.pi / 4
                    d.line(self.box(cx + math.cos(a) * 21, cy + math.sin(a) * 21,
                                    cx + math.cos(a) * 29, cy + math.sin(a) * 29),
                           fill="#f0b94a", width=max(1, int(3.5 * self.k)))
                d.ellipse(self.box(cx - 16, cy - 16, cx + 16, cy + 16), fill=self.BUTTER, outline="#f0b94a",
                          width=max(1, int(2 * self.k)))
            else:  # sparkles: something new
                for sx, sy, r in ((cx - 4, cy + 2, 22), (cx + 20, cy - 16, 10), (cx - 22, cy - 18, 7)):
                    pts = [(sx + math.cos(j * math.pi / 4 - math.pi / 2) * (r if j % 2 == 0 else r * 0.32),
                            sy + math.sin(j * math.pi / 4 - math.pi / 2) * (r if j % 2 == 0 else r * 0.32))
                           for j in range(8)]
                    d.polygon([(px * self.k, py * self.k) for px, py in pts], fill="#bfa8f2")
            y = y1 + 86 + lift
            y += self.text(d, cx, y, title, 16, "bold", fill=self.CHOC, center=True, width=tw - 20) + 4
            self.text(d, cx, y, sub, 13, fill=self.SOFT, center=True, width=tw - 24)
            py = y1 + th - 26 + lift
            pw = 96
            if on:
                d.rounded_rectangle(self.box(cx - pw / 2, py - 14, cx + pw / 2, py + 14), radius=14 * self.k,
                                    fill=self.MINT)
                f = self.font(13, "semi")
                tx = cx + 8 - d.textlength(on_label, font=f) / self.k / 2  # label, after a drawn tick
                d.line(self.box(tx - 17, py, tx - 13, py + 4, tx - 6, py - 4), fill="#2f6b4c",
                       width=max(1, int(2.2 * self.k)), joint="curve")
                d.text((tx * self.k, py * self.k), on_label, font=f, fill="#2f6b4c", anchor="lm")
            else:
                d.rounded_rectangle(self.box(cx - pw / 2, py - 14, cx + pw / 2, py + 14), radius=14 * self.k,
                                    fill=self.CHOC if hot else None, outline=self.CHOC,
                                    width=max(1, int(1.5 * self.k)))
                d.text((cx * self.k, py * self.k), off_label, font=self.font(13, "semi"),
                       fill=self.CREAM if hot else self.CHOC, anchor="mm")
            self.hits.append(((x1, y1, x1 + tw, y1 + th), name))
        self.text(d, self.W / 2, top + th + 14, "you can change these any time from my right-click menu",
                  13, "hand", fill=self.SOFT, center=True)

    # ---------------- behaviour
    def show(self):
        self.data = self.render()
        if not self.closing:
            self.surface.show(self.data, self.x, self.y, self.alpha)

    def fade(self, frm, to, t0=None):
        """Fade (and float) in or out over a quarter of a second."""
        t0 = t0 or time.time()
        u = min(1.0, (time.time() - t0) / 0.25)
        e = 1 - (1 - u) ** 3
        a = frm + (to - frm) * e
        self.alpha = int(255 * a)
        self.surface.show(self.data, self.x, self.y + (1 - a) * 14 * self.u, self.alpha)
        if u < 1:
            self.win.after(15, self.fade, frm, to, t0)
        elif to == 0:
            self.win.destroy()
            self.cat.welcome_closed()

    def close(self):
        if not self.closing:
            self.closing = True
            self.fade(1, 0)

    def go(self, page):
        self.page = max(0, min(len(self.pages) - 1, page))
        self.hover = None
        self.show()

    def click(self, name):
        if name == "next":
            self.close() if self.page == len(self.pages) - 1 else self.go(self.page + 1)
        elif name == "back":
            self.go(self.page - 1)
        elif name == "close":
            self.close()
        elif name == "desktop":
            self.cat.toggle_desktop_icon(not self.desktop)
            self.desktop = has_desktop_icon()
            self.show()
        elif name == "startup":
            self.cat.toggle_startup(not self.startup)
            self.startup = in_startup()
            self.show()
        elif name == "updates":
            self.cat.toggle_updates(not self.updates)
            self.updates = bool(self.cat.settings["check_updates"])
            self.show()

    def hit(self, e):
        x, y = e.x / self.u, e.y / self.u
        for (x1, y1, x2, y2), name in self.hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return None

    def on_move(self, e):
        name = self.hit(e)
        if name != self.hover and not self.drag:
            self.hover = name
            self.win.configure(cursor="hand2" if name else "")
            self.show()

    def on_leave(self, e):
        if self.hover:
            self.hover = None
            self.show()

    def on_press(self, e):
        self.pressed = self.hit(e)
        if not self.pressed:  # grab the card anywhere else to move it
            self.drag = (e.x_root, e.y_root, self.x, self.y)

    def on_drag(self, e):
        if self.drag:
            sx, sy, ox, oy = self.drag
            self.x, self.y = ox + e.x_root - sx, oy + e.y_root - sy
            self.surface.show(self.data, self.x, self.y, self.alpha)

    def on_release(self, e):
        if self.pressed and self.hit(e) == self.pressed:
            self.click(self.pressed)
        self.pressed = self.drag = None

    def on_key(self, e):
        if e.keysym == "Escape":
            self.close()
        elif e.keysym in ("Right", "Return", "space"):
            self.click("next")
        elif e.keysym == "Left" and self.page:
            self.go(self.page - 1)


if __name__ == "__main__":
    _mutex = claim_single_instance()
    Cat().root.mainloop()
