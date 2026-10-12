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
import json
import math
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
import winreg
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import uiautomation as auto  # reads the browser address bar
except ImportError:
    auto = None

# ---------------------------------------------------------------- settings
TEST_MODE = "--test" in sys.argv
TEST_LIMIT = 20       # "Test the reels mission": 20s of reels open, scrolling or not
SCROLL_GRACE = 45     # counts as "scrolling" if you scrolled within this many seconds
FORGET_AFTER = 60     # leave reels this long and the timer resets

REEL_URLS = ("instagram.com/reels", "instagram.com/reel/", "youtube.com/shorts",
             "tiktok.com", "facebook.com/reel", "m.facebook.com/reel")
REEL_TITLES = ("reels", "tiktok", "#shorts", "youtube shorts")  # only if the URL can't be read
REEL_EXES = ("tiktok.exe", "instagram.exe")  # desktop apps, matched on the program itself
REEL_STORE_APPS = ("tiktok", "instagram")    # Store apps: exact window title in ApplicationFrameHost
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
            "opera_gx.exe", "vivaldi.exe", "arc.exe", "zen.exe"}

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
            "limit_minutes": 5, "warning_seconds": 60, "action": "close"}

# Next to the script when run from source; in %APPDATA% for the packaged .exe
# (a one-file exe unpacks into a temp folder that's wiped on exit).
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    _dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Charles Chocolate")
    os.makedirs(_dir, exist_ok=True)
    SETTINGS_FILE = os.path.join(_dir, "settings.json")
else:
    SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desk_cat_settings.json")
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

WM_CLOSE = 0x0010
VK_LBUTTON, VK_CONTROL, VK_MENU, VK_W, VK_UP, VK_DOWN = 0x01, 0x11, 0x12, 0x57, 0x26, 0x28
SCROLL_KEYS = {0x21, 0x22, 0x23, 0x24, 0x26, 0x28}  # PgUp, PgDn, End, Home, Up, Down
KEYUP = 0x0002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


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


def work_area():
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
    if user32.GetForegroundWindow() == hwnd:
        return True
    tap(VK_MENU); tap(VK_MENU, up=True)  # Alt tap lets us take focus
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


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


# ---------------------------------------------------------------- reels watcher
def same_page(tab_name, title):
    """Does a tab's name belong to the page the window title shows?"""
    a, b = (tab_name or "").lower().strip()[:24], (title or "").lower()
    return bool(a) and (b.startswith(a) or a in b)


class ReelsWatcher:
    """Background thread: figures out if the focused window is a reels feed,
    plus mouse/keyboard hooks that note when you scroll (and can block it)."""

    def __init__(self):
        self.hwnd = None          # focused reels window, or None
        self.is_browser = False
        self.sure = False         # True if we read the URL (or matched the app's exe)
        self.last_scroll = 0.0
        self.hook_ok = True
        self.block_hwnd = None    # while set, scrolling in this reels window is swallowed
        self.blocked_at = 0.0     # last time we swallowed a scroll
        self._edit_cache = {}
        self.jobs = queue.Queue()
        threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._hooks, daemon=True).start()

    def scrolling(self):
        if not self.hook_ok:
            return True
        if user32.GetAsyncKeyState(VK_DOWN) & 0x8000 or user32.GetAsyncKeyState(VK_UP) & 0x8000:
            self.last_scroll = time.time()
        return time.time() - self.last_scroll < SCROLL_GRACE

    def _blocking(self, hwnd):
        b = self.block_hwnd
        return bool(b) and hwnd == b and self.hwnd == b

    def _hooks(self):
        def mouse(n, w, l):
            if n == 0 and w in (0x020A, 0x020E):  # wheel / horizontal wheel
                self.last_scroll = time.time()
                if self.block_hwnd:
                    under = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(*cursor_pos())), 2)
                    if self._blocking(under):
                        self.blocked_at = time.time()
                        return 1
            return user32.CallNextHookEx(None, n, w, l)

        def keyboard(n, w, l):
            if n == 0 and self.block_hwnd and w in (0x0100, 0x0104):  # WM_KEYDOWN / WM_SYSKEYDOWN
                vk = ctypes.cast(l, ctypes.POINTER(wintypes.DWORD))[0]
                if vk in SCROLL_KEYS and self._blocking(user32.GetForegroundWindow()):
                    self.blocked_at = time.time()
                    return 1
            return user32.CallNextHookEx(None, n, w, l)

        self._procs = HOOKPROC(mouse), HOOKPROC(keyboard)
        mod = kernel32.GetModuleHandleW(None)
        if not user32.SetWindowsHookExW(14, self._procs[0], mod, 0):  # WH_MOUSE_LL
            self.hook_ok = False
            return
        user32.SetWindowsHookExW(13, self._procs[1], mod, 0)  # WH_KEYBOARD_LL
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass

    def _url(self, hwnd):
        if auto is None:
            return ""
        edit = self._edit_cache.get(hwnd)
        try:
            if edit is None or not edit.Exists(0, 0):
                edit = auto.ControlFromHandle(hwnd).EditControl(searchDepth=16)
                self._edit_cache[hwnd] = edit
            return (edit.GetValuePattern().Value or "").lower()
        except Exception:
            self._edit_cache.pop(hwnd, None)
            return ""

    def url_is_reels(self, hwnd):
        url = self._url(hwnd)
        return any(u in url for u in REEL_URLS)

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
                return (hwnd if any(u in url for u in REEL_URLS) else None), True, True
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
        """The active tab's close (X) button and where it is on screen, or None if
        we can't be sure which tab is showing the reels."""
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
                for btn, _ in auto.WalkControl(tab, maxDepth=2):
                    b = btn.BoundingRectangle
                    if btn.ControlTypeName == "ButtonControl" and b.width() > 0:
                        return {"x": (b.left + b.right) // 2, "y": (b.top + b.bottom) // 2,
                                "button": btn, "name": tab.Name}
                return None  # right tab, but no close button we can press
            return None
        return None

    def close_tab(self, hwnd, btn):
        """Close the reels tab, re-checking the address bar right before each attempt.
        Returns "closed", "gone" (you'd already left) or "unsure" (didn't touch anything)."""
        if not user32.IsWindow(hwnd) or not self.url_is_reels(hwnd):
            return "gone"
        if btn is not None:
            try:
                if btn.Exists(0, 0):
                    try:
                        btn.GetInvokePattern().Invoke()
                    except Exception:
                        btn.GetLegacyIAccessiblePattern().DoDefaultAction()
                    return "closed"
            except Exception:
                pass
        # Keyboard fallback: only if that window is in front *and* still on reels.
        if bring_to_front(hwnd) and self.url_is_reels(hwnd) and user32.GetForegroundWindow() == hwnd:
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
                    self.hwnd, self.is_browser, self.sure = self._check()
                except Exception:
                    self.hwnd = None


# ---------------------------------------------------------------- drawing
SS = 3  # supersampling for smooth edges


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


# ---------------------------------------------------------------- the cat
class Cat:
    def __init__(self):
        self.settings = dict(DEFAULTS)
        try:
            with open(SETTINGS_FILE) as f:
                self.settings.update(json.load(f))
        except Exception:
            pass
        if self.settings["action"] not in ACTIONS.values():
            self.settings["action"] = DEFAULTS["action"]

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.update_idletasks()
        self.hwnd = int(self.root.wm_frame(), 16)
        ex = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, ex | 0x80000 | 0x80)  # LAYERED | TOOLWINDOW

        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.dib = None
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
        self.init_anim()

        self.drag = None
        self.root.bind("<ButtonPress-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Button-3>", self.on_menu)
        self.build_menu()

        self.root.geometry(f"{self.W}x{self.H}+{int(self.x)}+{int(self.y)}")
        self.say("mrrp! hi :3", 3)
        self.set_state("wave", 2.6)
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
        self.s = SIZES.get(self.settings["size"], 1.0)
        self.W, self.H = int(280 * self.s), int(230 * self.s)
        self.font = ImageFont.truetype("segoeuib.ttf", int(13 * self.s * SS))
        self.zfont = ImageFont.truetype("segoeuib.ttf", int(12 * self.s * SS))
        bmi = BITMAPINFOHEADER(40, self.W, -self.H, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(self.mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(self.mem_dc, dib)
        if self.dib:
            gdi32.DeleteObject(self.dib)
        self.dib, self.bits = dib, bits
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
        self.startup_var = tk.BooleanVar(value=self.starts_with_windows())
        self.menu.add_checkbutton(label="Start with Windows", variable=self.startup_var,
                                  command=self.toggle_startup)
        self.menu.add_command(label="Test the reels mission", command=self.test_mission)
        self.menu.add_separator()
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

    def startup_command(self):
        if FROZEN:
            return f'"{sys.executable}"'
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}"'

    def starts_with_windows(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, "Charles Chocolate")
            return True
        except OSError:
            return False

    def toggle_startup(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if self.startup_var.get():
                    winreg.SetValueEx(k, "Charles Chocolate", 0, winreg.REG_SZ, self.startup_command())
                    self.say("see you every morning :3", 2.5)
                else:
                    winreg.DeleteValue(k, "Charles Chocolate")
                    self.say("fine. call me when you need me.", 2.5)
        except OSError:
            self.startup_var.set(self.starts_with_windows())
            self.say("hm, Windows said no", 2)

    def floor(self):
        return self.wa[3] - self.H + int((FOOT - 6) * self.s)

    def say(self, text, secs=2.5):
        self.bubble = text
        self.bubble_until = time.time() + secs

    def set_state(self, s, secs=None):
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
        hwnd = self.watcher.hwnd
        if hwnd and (self.testing or self.watcher.scrolling()):
            self.reels_secs += dt
            self.away_secs = 0
        elif not hwnd and not self.testing:
            self.away_secs += dt
            if self.away_secs > FORGET_AFTER:
                self.reels_secs = 0
                self.warned = False
                self.unblock()

        if self.watcher.block_hwnd and time.time() - self.watcher.blocked_at < 0.2 and \
                time.time() > self.bubble_until and not self.state.startswith("mission"):
            self.say(random.choice(["nope.", "no more scrolling.", "I said no.", "*sits on scroll wheel*"]), 2)
            self.set_state("angry", 1.5)

        if self.state.startswith("mission") or self.state == "held" or self.watcher.block_hwnd:
            return
        warn_at = self.warn_at()
        if not self.warned and warn_at is not None and self.reels_secs >= warn_at and hwnd:
            self.warned = True
            left = self.limit() - warn_at
            self.say(f"{left} more seconds..." if left < 60 else
                     "one more minute of reels..." if left == 60 else f"{left // 60} more minutes of reels...", 4)
        if self.reels_secs >= self.limit() and hwnd:
            self.intervene(hwnd)

    def intervene(self, hwnd):
        action = "close" if self.testing else self.settings["action"]
        if action == "nag":
            self.reels_secs = 0
            self.warned = False
            self.say(random.choice(["that's enough reels.", "go touch grass :3", "time's up, scroller."]), 4)
            self.set_state("angry", 3)
        elif action == "block":
            self.block(hwnd, "that's enough. no more scrolling.")
        elif self.watcher.is_browser and not self.watcher.sure:
            # Couldn't read the address bar, so we can't tell which tab is reels.
            self.cant_close(hwnd)
        else:
            self.start_mission(hwnd, self.watcher.is_browser)

    def block(self, hwnd, line):
        self.watcher.block_hwnd = hwnd
        self.testing = False
        self.say(line, 4)
        l, t, r, b = window_rect(hwnd)
        lo, hi = self.wa[0], self.wa[2] - self.W
        self.walk_to(min(max((l + r) / 2 - self.W / 2, lo), hi), speed=7, state="storm")

    def unblock(self):
        self.watcher.block_hwnd = None

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
        self.mission_btn = None
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
            self.mission_btn = found["button"]
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
        return bool(hwnd) and self.watcher.hwnd == hwnd and user32.IsWindow(hwnd)

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
            self.job = self.watcher.submit(self.watcher.close_tab, hwnd, self.mission_btn)
            self.set_state("mission_closing", 6)
            return
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self.land_msg = random.choice(DONE_LINES)
        self.set_state("mission_letgo", 0.5)

    def end_mission(self):
        self.mission_hwnd = None
        self.mission_btn = None
        self.vy = 0
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
                    self.watcher.block_hwnd = self.mission_hwnd
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

        out = frame.convert("RGBa").reduce(SS)
        r, g, b, a = out.split()
        return Image.merge("RGBA", (b, g, r, a)).tobytes()

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
        ctypes.memmove(self.bits, data, len(data))
        blend = BLENDFUNCTION(0, 0, 255, 1)
        pos = wintypes.POINT(int(self.x), int(self.y))
        size = wintypes.SIZE(self.W, self.H)
        src = wintypes.POINT(0, 0)
        user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, ctypes.byref(pos), ctypes.byref(size),
                                   self.mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), 2)

    # ---------------- main loop
    def loop(self):
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        self.t += dt
        self.track_reels(dt)
        self.check_petting()
        self.update(dt)
        self.present(self.render())
        self.root.after(33, self.loop)


if __name__ == "__main__":
    Cat().root.mainloop()
