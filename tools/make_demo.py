"""
Renders docs/img/demo.gif and docs/img/demo.webp: Charles noticing a Reels
binge, warning you, then jumping up and swatting the tab closed.

She's drawn by the real desk_cat.py code (states, physics, speech bubbles),
driven by a virtual clock over a mock browser, so the demo always matches
what she actually looks like. Windows only, like Charles.

Run:  python tools/make_demo.py
"""

import importlib.util
import os
import random
import types

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("desk_cat", os.path.join(ROOT, "desk_cat.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

FPS = 30              # her movement is per-frame, tuned for the app's ~30fps
CW, CH = 960, 640                      # canvas = a tiny pretend desktop
WIN = (40, 96, 920, 588)               # browser window
TASKBAR = 46
REEL_TAB = (WIN[0] + 12, WIN[1] + 8, WIN[0] + 252, WIN[1] + 40)
REEL_X = (REEL_TAB[2] - 22, (REEL_TAB[1] + REEL_TAB[3]) // 2)   # its close button

clock = [0.0]
cursor = [600.0, 360.0]
dc.time = types.SimpleNamespace(time=lambda: clock[0], sleep=lambda s: None)
dc.cursor_pos = lambda: (int(cursor[0]), int(cursor[1]))
dc.ReelsWatcher = lambda: types.SimpleNamespace(block_hwnd=None)   # no hooks, no UI Automation
dc.Cat.loop = lambda self: None
dc.Cat.save_settings = lambda self: None
random.seed(7)

F = lambda size, bold=False: ImageFont.truetype("segoeuib.ttf" if bold else "segoeui.ttf", size)
EMOJI = ImageFont.truetype("seguiemj.ttf", 64)
REELS = [("🕺", "#ff9a8b", "guy dances in a kitchen"), ("🍝", "#f8d27a", "pasta but it's ASMR"),
         ("🐕", "#a9c9f5", "dog meets a cucumber"), ("💄", "#f7a8c4", "get ready with me (pt 47)"),
         ("🤡", "#bfa8f2", "you won't BELIEVE what"), ("🍳", "#ffb38a", "egg hack (real??)"),
         ("🦆", "#9ad8e6", "duck. just a duck.")]


def desktop(scroll, closed, timer, warn):
    img = Image.new("RGB", (CW, CH), "#f6e9dc")
    d = ImageDraw.Draw(img)
    for x in range(0, CW, 28):           # the website's polka dots
        for y in range(0, CH, 28):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#efdccb")
    l, t, r, b = WIN
    d.rounded_rectangle((l + 4, t + 8, r + 4, b + 8), 14, fill="#e3cdb9")
    d.rounded_rectangle(WIN, 12, fill="#ffffff", outline="#d6c7b8", width=2)
    d.rounded_rectangle((l, t, r, t + 48), 12, fill="#efe7df")
    d.rectangle((l, t + 30, r, t + 48), fill="#efe7df")

    tabs = [] if closed else [("Reels • Instagram", REEL_TAB)]
    other = (REEL_TAB[0] + (0 if closed else 248), REEL_TAB[1], REEL_TAB[2] + (0 if closed else 248), REEL_TAB[3])
    tabs.append(("Cat facts - Wikipedia", other))
    for i, (name, (x1, y1, x2, y2)) in enumerate(tabs):
        active = i == 0
        d.rounded_rectangle((x1, y1, x2, y2 + 8), 9, fill="#ffffff" if active else "#e4d9cf")
        d.text((x1 + 14, (y1 + y2) // 2), name, font=F(14, active), fill="#3b2a22", anchor="lm")
        cx, cy = x2 - 22, (y1 + y2) // 2
        d.line((cx - 5, cy - 5, cx + 5, cy + 5), fill="#7a5340", width=2)
        d.line((cx - 5, cy + 5, cx + 5, cy - 5), fill="#7a5340", width=2)
    d.rectangle((l + 2, t + 48, r - 2, t + 92), fill="#ffffff")
    d.rounded_rectangle((l + 92, t + 56, r - 20, t + 84), 14, fill="#f3ede7")
    url = "en.wikipedia.org/wiki/Cat" if closed else "instagram.com/reels/"
    d.text((l + 112, t + 70), url, font=F(15), fill="#3b2a22", anchor="lm")
    for i, dx in enumerate((1, -1)):     # back / forward arrows
        x, y = l + 24 + i * 26, t + 70
        d.line((x - 5 * dx, y, x + 5 * dx, y - 6), fill="#9a8577", width=2)
        d.line((x - 5 * dx, y, x + 5 * dx, y + 6), fill="#9a8577", width=2)
    d.arc((l + 68, t + 63, l + 82, t + 77), 40, 330, fill="#9a8577", width=2)

    body = (l + 2, t + 94, r - 2, b - 2)
    if closed:
        d.text((l + 60, t + 130), "Cat", font=F(34, True), fill="#3b2a22")
        for i in range(7):
            d.rounded_rectangle((l + 60, t + 190 + i * 30, r - 120 - (i * 53) % 180, t + 202 + i * 30), 6,
                                fill="#ece4dc")
    else:
        pw, ph = 236, body[3] - body[1] - 24
        px, py = (l + r) // 2 - pw // 2, body[1] + 12
        feed = Image.new("RGB", (pw, ph), "#2d2230")
        fd = ImageDraw.Draw(feed)
        n = len(REELS)
        for k in range(-1, 3):
            idx = (int(scroll) + k) % n
            y = int((k - (scroll % 1)) * ph)
            emoji, col, cap = REELS[idx]
            fd.rectangle((0, y, pw, y + ph), fill=col)
            fd.text((pw // 2, y + ph // 2 - 10), emoji, font=EMOJI, embedded_color=True, anchor="mm")
            fd.text((14, y + ph - 34), cap, font=F(14, True), fill="#ffffff")
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), 22, fill=255)
        img.paste(feed, (px, py), mask)

        # the reels timer, as shown in her right-click menu
        tx, ty = r - 170, body[1] + 20
        d.rounded_rectangle((tx, ty, tx + 140, ty + 56), 14, fill="#f8d27a" if warn else "#fffdf8",
                            outline="#5b3a29", width=3)
        d.text((tx + 70, ty + 15), "reels timer", font=F(12, True), fill="#7a5340", anchor="mm")
        m, s = divmod(int(timer), 60)
        d.text((tx + 70, ty + 36), f"{m}:{s:02d} / 5:00", font=F(20, True), fill="#5b3a29", anchor="mm")

    d.rectangle((0, CH - TASKBAR, CW, CH), fill="#e9ddd1")
    for i in range(5):
        x = CW // 2 - 90 + i * 40
        d.rounded_rectangle((x, CH - TASKBAR + 9, x + 28, CH - 9), 6, fill="#d9c6b4")
    return img


def draw_cursor(img):
    x, y = cursor
    pts = [(x, y), (x, y + 20), (x + 5, y + 15), (x + 9, y + 23), (x + 12, y + 21), (x + 8, y + 14), (x + 14, y + 14)]
    ImageDraw.Draw(img).polygon(pts, fill="#ffffff", outline="#2b2926")


def cat_sprite(cat):
    data = cat.render()
    b, g, r, a = Image.frombytes("RGBA", (cat.W, cat.H), data).split()
    return Image.merge("RGBa", (r, g, b, a)).convert("RGBA")


def main():
    cat = dc.Cat()
    cat.root.withdraw()
    cat.settings.update(coat="Mochi (white)", size="Large")
    cat.apply_size()
    cat.wa = (0, 0, CW, CH - TASKBAR)
    cat.x, cat.y = float(CW - cat.W - 40), float(cat.floor())
    cat.facing, cat.pose = -1, "sit"
    cat.set_state("idle", 99)
    cat.bubble = None

    # where the hang has to be so her paw lands on the reels tab's X (same maths as plan_jump)
    px, py = REEL_X
    facing = -1
    hang = (px - cat.W / 2 - dc.PAW[0] * cat.s * facing, py - (cat.H - dc.FOOT * cat.s) - dc.PAW[1] * cat.s)

    closed = [False]

    def swat():
        closed[0] = True
        cat.land_msg = "go touch grass :3"
        cat.set_state("mission_letgo", 0.5)
    cat.close_target = swat

    frames, states, scroll, timer = [], [], 0.0, 228.0
    dt = 1 / FPS
    events = {0.6: "warn", 4.4: "limit", 5.6: "go"}
    fired = set()
    total = 14.5
    while clock[0] < total:
        t = clock[0]
        for at, ev in events.items():
            if t >= at and ev not in fired:
                fired.add(ev)
                if ev == "warn":
                    timer = 240
                    cat.say("one more minute of reels...", 3)
                elif ev == "limit":
                    cat.pose = "stand"
                    cat.say("okay. that's enough reels.", 2.5)
                    cat.set_state("angry", 1.2)
                elif ev == "go":
                    cat.hang_pos, cat.hang_facing = hang, facing
                    cat.walk_to(min(max(hang[0], cat.wa[0] - cat.W / 3), cat.wa[2] - cat.W * 2 / 3),
                                speed=8, state="mission_go")
        if not closed[0] and t < 4.4:
            # sped-up doom-scroll: a new reel every 0.55s, eased, timer racing to 5:00
            u = t / 0.55
            scroll = int(u) + min(1.0, (u % 1) * 3) ** 2
            timer = min(300, 240 + (t - 0.6) / 3.8 * 60) if t > 0.6 else 228 + t * 20
            cursor[0], cursor[1] = 520 + (t * 40) % 6, 360 + (u % 1 < 0.33) * 6
        elif t >= 4.4:
            timer = 300
        cat.update(dt)
        cat.t += dt
        if cat.state == "idle" and t > 8:
            cat.state_until = t + 99      # stay put for the ending
        frame = desktop(scroll, closed[0], timer, 240 <= timer < 300 or (timer >= 300 and not closed[0]))
        spr = cat_sprite(cat)
        frame.paste(spr, (int(cat.x), int(cat.y)), spr)
        if not closed[0]:
            draw_cursor(frame)
        frames.append(frame)
        states.append(cat.state)
        clock[0] += dt

    out = os.path.join(ROOT, "docs", "img")
    small = [f.resize((CW * 3 // 4, CH * 3 // 4), Image.LANCZOS) for f in frames[::2]]   # 15fps
    pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in small]
    pal[0].save(os.path.join(out, "demo.gif"), save_all=True, append_images=pal[1:],
                duration=int(2000 / FPS), loop=0, optimize=True, disposal=1)
    frames[0].save(os.path.join(out, "demo.webp"), save_all=True, append_images=frames[1:],
                   duration=int(1000 / FPS), loop=0, quality=80, method=4)
    hung = next(i for i, f in enumerate(states) if f == "mission_swipe")
    frames[hung + 10].save(os.path.join(out, "demo-still.png"))
    print(f"{len(frames)} frames ->", out)
    os._exit(0)


if __name__ == "__main__":
    main()
