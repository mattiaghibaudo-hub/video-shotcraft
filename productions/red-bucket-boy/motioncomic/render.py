#!/usr/bin/env python3
"""Motion comic di "Red Bucket Boy — La Reliquia", senza generatori AI e senza crediti.

Ogni shot di ../shots.json viene ricostruito in codice:
  - personaggi scontornati dalle schede (rembg), animati a marionetta
    (traslazioni, rotazioni, salti, battito di ciglia disegnato), con light wrap
    e color grading della scena;
  - scenografie con la stessa resa 3D materica delle schede (look.py): montagne
    con rilievo illuminato, neve, roccia, nuvole, oggetti "in plastilina" gonfiati
    dalle sagome, bloom, profondità di campo e grana;
  - voci italiane in locale con Piper TTS, musica lo-fi sintetizzata con numpy;
  - montaggio finale con ../assemble.py (title card, mix audio, sottotitoli).

Uso:
  pip install rembg onnxruntime piper-tts scipy pillow numpy
  python3 motioncomic/render.py                 # tutto: scontorni, shot, audio, montaggio
  python3 motioncomic/render.py --only 04 07    # rifà solo alcuni shot, poi rimonta
  python3 motioncomic/render.py --bandana red   # fazzoletto di Paco rosso come nella scheda

Uscita: motioncomic/build/red-bucket-boy_ep01_motioncomic.mp4
"""
import argparse
import json
import math
import random
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CUT = HERE / "cutouts"
BUILD = HERE / "build"
CLIPS = BUILD / "clips"
VO = BUILD / "audio" / "vo"
MUSIC = BUILD / "audio" / "music.mp3"
VOICES = HERE / "voices"

W, H, FPS = 1080, 1920, 24
GREEN = (157, 255, 58)
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"

SHEETS = {
    "boy": ROOT / "characters" / "red-bucket-boy_sheet_v1_full.jpg",
    "paco": ROOT / "characters" / "paco_sheet_v2.jpg",
}
VIEWS = {"boy": ["front", "34", "side", "back"], "paco": ["front", "side", "back"]}


# --------------------------------------------------------------------------- utilità

def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def vgrad(w, h, stops):
    ys = np.linspace(0, 1, h)
    pos = [p for p, _ in stops]
    cols = np.array([c for _, c in stops], dtype=np.float32)
    rgb = np.stack([np.interp(ys, pos, cols[:, i]) for i in range(3)], axis=1)
    arr = np.repeat(rgb[:, None, :], w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def grain(img, amount=7, seed=0):
    rng = np.random.default_rng(seed)
    a = np.asarray(img).astype(np.int16)
    n = rng.normal(0, amount, a.shape[:2])[:, :, None]
    return Image.fromarray(np.clip(a + n, 0, 255).astype(np.uint8), img.mode)


def ridge(w, base, amp, seed, rough=0.55, levels=8):
    rng = random.Random(seed)
    pts = [(-80, base + rng.uniform(-amp, amp) * 0.3), (w + 80, base + rng.uniform(-amp, amp) * 0.3)]
    disp = amp
    for _ in range(levels):
        new = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            new.append((x0, y0))
            new.append(((x0 + x1) / 2, (y0 + y1) / 2 + rng.uniform(-disp, disp)))
        new.append(pts[-1])
        pts = new
        disp *= rough
    return pts


def grade(spr, mul=(1, 1, 1), add=(0, 0, 0)):
    a = np.asarray(spr).astype(np.float32)
    a[:, :, :3] = np.clip(a[:, :, :3] * np.array(mul) + np.array(add), 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def fade(spr, k):
    if k >= 1:
        return spr
    a = np.asarray(spr).copy()
    a[:, :, 3] = (a[:, :, 3] * max(0.0, k)).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


_cache = {}


def scaled(spr, height, key=None):
    h = max(2, int(round(height)))
    k = (key or id(spr), h)
    if k not in _cache:
        w = max(2, int(round(spr.width * h / spr.height)))
        im = spr.resize((w, h), Image.LANCZOS)
        if h > spr.height * 1.3:
            im = im.filter(ImageFilter.UnsharpMask(2, 60, 2))
        _cache[k] = im
    return _cache[k]


def place(frame, spr, x, y, height=None, rot=0.0, anchor="bottom", key=None, flip=False, alpha=1.0):
    im = scaled(spr, height, key) if height else spr
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        im = fade(im, alpha)
    if anchor == "bottom":
        pos = (int(x - im.width / 2), int(y - im.height))
    elif anchor == "top":
        pos = (int(x - im.width / 2), int(y))
    else:
        pos = (int(x - im.width / 2), int(y - im.height / 2))
    frame.paste(im, pos, im)
    return pos, im.size


def shadow(frame, x, y, w, h, a=110):
    s = soft_ellipse((int(w), int(h)), (0, 0, 0), a, 14)
    frame.paste(s, (int(x - s.width / 2), int(y - s.height / 2)), s)


VIG = None


def vignette(frame, strength=0.38):
    global VIG
    if VIG is None:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.72)) ** 2)
        VIG = np.clip(1 - strength * r ** 2.2, 0.35, 1)[:, :, None].astype(np.float32)
    a = np.asarray(frame).astype(np.float32) * VIG
    return Image.fromarray(a.astype(np.uint8), "RGB")


def zoom(frame, z, cx=W / 2, cy=H / 2):
    if z <= 1.0001:
        return frame
    w, h = W / z, H / z
    x0 = min(max(0.0, cx - w / 2), W - w - 0.01)
    y0 = min(max(0.0, cy - h / 2), H - h - 0.01)
    box = (x0, y0, x0 + w, y0 + h)
    return frame.resize((W, H), Image.BICUBIC, box=box)


# --------------------------------------------------------------------------- personaggi

def make_cutouts(bandana):
    CUT.mkdir(parents=True, exist_ok=True)
    need = [f"{n}_{v}.png" for n in VIEWS for v in VIEWS[n]]
    if not all((CUT / f).exists() for f in need):
        from rembg import new_session, remove
        from scipy import ndimage
        sess = new_session("isnet-general-use")
        for name, path in SHEETS.items():
            print(f"  scontorno {path.name} ...")
            out = np.asarray(remove(Image.open(path).convert("RGB"), session=sess))
            lab, n = ndimage.label(out[:, :, 3] > 40)
            sizes = ndimage.sum(np.ones(lab.shape), lab, range(1, n + 1))
            objs = ndimage.find_objects(lab)
            big = sorted([(i, objs[i]) for i in range(n) if sizes[i] > 0.01 * lab.size], key=lambda t: t[1][1].start)
            if len(big) != len(VIEWS[name]):
                sys.exit(f"{path.name}: trovate {len(big)} viste invece di {len(VIEWS[name])}")
            for view, (i, sl) in zip(VIEWS[name], big):
                arr = out.copy()
                arr[:, :, 3] = np.where(lab == i + 1, arr[:, :, 3], 0)
                Image.fromarray(arr).crop((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)).save(CUT / f"{name}_{view}.png")
    S = {f[:-4]: Image.open(CUT / f).convert("RGBA") for f in need}

    # Paco, vista frontale: via l'anatomia tra le zampe (versione social / family)
    p = np.asarray(S["paco_front"]).copy()
    h, w = p.shape[:2]
    p[int(h * 0.662):int(h * 0.75), int(w * 0.512):int(w * 0.628), 3] = 0
    S["paco_front"] = Image.fromarray(p)

    # fazzoletto: il rosso resta solo al cappello (il cappello è "la Reliquia")
    if bandana != "red":
        hue = {"mustard": 30, "orange": 18, "teal": 125}[bandana]
        for k in ("paco_front", "paco_side", "paco_back"):
            rgba = np.asarray(S[k])
            hsv = np.asarray(S[k].convert("RGB").convert("HSV")).copy()
            m = ((hsv[:, :, 0] < 14) | (hsv[:, :, 0] > 240)) & (hsv[:, :, 1] > 115) & (hsv[:, :, 2] > 45)
            hsv[:, :, 0] = np.where(m, hue, hsv[:, :, 0])
            hsv[:, :, 1] = np.where(m, np.minimum(255, hsv[:, :, 1].astype(int) + 20), hsv[:, :, 1])
            hsv[:, :, 2] = np.where(m, np.minimum(255, hsv[:, :, 2].astype(int) + 35), hsv[:, :, 2])
            rgb = np.asarray(Image.fromarray(hsv, "HSV").convert("RGB"))
            S[k] = Image.fromarray(np.dstack([rgb, rgba[:, :, 3]]), "RGBA")

    boy = S["boy_front"]
    bw, bh = boy.size
    sx, sy = bw / 425, bh / 1226  # coordinate misurate sulla scheda a 2576 px

    # battito di ciglia (palpebre chiuse disegnate sopra gli occhi)
    def blinked(im):
        im = im.copy()
        d = ImageDraw.Draw(im)
        for ex in (170, 245):
            cx, cy = ex * sx, 158 * sy
            d.ellipse((cx - 24 * sx, cy - 17 * sy, cx + 24 * sx, cy + 15 * sy), fill=(196, 144, 120, 255))
            d.arc((cx - 23 * sx, cy - 6 * sy, cx + 23 * sx, cy + 15 * sy), 15, 165, fill=(70, 45, 35, 255), width=max(2, int(3 * sx)))
        return im
    S["boy_blink"] = blinked(boy)

    # il cappello da solo (per il piedistallo) e il ragazzo senza cappello
    a = np.asarray(boy).copy()
    hsv = np.asarray(boy.convert("RGB").convert("HSV"))
    yy = np.arange(bh)[:, None]
    # rosso del cappello: tinta < 10° (la pelle sta intorno ai 15°)
    red = ((hsv[:, :, 0] < 7) | (hsv[:, :, 0] > 245)) & (hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 25) & (yy < 0.17 * bh) & (a[:, :, 3] > 0)
    from scipy import ndimage
    red = ndimage.binary_closing(red, iterations=6) & (a[:, :, 3] > 0)
    red = ndimage.binary_fill_holes(red)
    red = ndimage.binary_dilation(red, iterations=2) & (a[:, :, 3] > 0) & (yy < 0.16 * bh)
    lab, nl = ndimage.label(red)  # tieni solo il pezzo grande (il cappello)
    if nl > 1:
        sz = ndimage.sum(np.ones(lab.shape), lab, range(1, nl + 1))
        red = lab == (int(np.argmax(sz)) + 1)
    hat = a.copy()
    hat[:, :, 3] = np.where(red, hat[:, :, 3], 0)
    hat_im = Image.fromarray(hat)
    S["hat"] = hat_im.crop(hat_im.getbbox())

    nohat = a.copy()
    # anche il bordino chiaro lasciato dallo scontorno attorno al cappello (non pelle, non capelli scuri)
    ring = ndimage.binary_dilation(red, iterations=7) & ~red
    skin = (hsv[:, :, 0] >= 7) & (hsv[:, :, 0] <= 30) & (hsv[:, :, 1] > 60)
    ring &= ~skin & (hsv[:, :, 2] > 70)
    nohat[:, :, 3] = np.where(red | ring, 0, nohat[:, :, 3])
    xx = np.arange(bw)[None, :]
    top = yy < 0.16 * bh
    nohat[:, :, 3] = np.where(top & (nohat[:, :, 3] < 160), 0, nohat[:, :, 3])
    far = (yy < 0.11 * bh) & (np.abs(xx - 212 * sx) > 100 * sx)
    nohat[:, :, 3] = np.where(far, 0, nohat[:, :, 3])
    nohat_im = Image.fromarray(nohat)
    hair = Image.new("RGBA", boy.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(hair)
    hc = (34, 27, 24, 255)
    cx = 212 * sx
    d.ellipse((cx - 94 * sx, 70 * sy, cx + 94 * sx, 205 * sy), fill=hc)
    rng = random.Random(4)
    for i in range(34):  # ciuffi spettinati, piccoli e irregolari
        ang = math.radians(196 + i * 148 / 33 + rng.uniform(-3, 3))
        bx, by = cx + 86 * sx * math.cos(ang), 132 * sy + 58 * sy * math.sin(ang)
        ln = rng.uniform(8, 26) * sy
        tip = (bx + math.cos(ang) * ln + rng.uniform(-10, 10) * sx, by + math.sin(ang) * ln - rng.uniform(2, 10) * sy)
        c = tuple(int(v * rng.uniform(0.8, 1.3)) for v in hc[:3]) + (255,)
        d.polygon([(bx - 7 * sx, by + 4 * sy), tip, (bx + 7 * sx, by + 4 * sy)], fill=c)
    # l'ammaccatura ad anello lasciata dal cappello
    d.arc((cx - 90 * sx, 92 * sy, cx + 90 * sx, 160 * sy), 195, 345, fill=(16, 12, 10, 255), width=max(3, int(5 * sx)))
    hair = hair.filter(ImageFilter.GaussianBlur(1.2))
    hair.alpha_composite(nohat_im)
    S["boy_hatless"] = hair
    S["boy_hatless_blink"] = blinked(hair)

    # primi piani
    S["boy_head"] = boy.crop((0, 0, bw, int(bh * 0.33)))
    pf = S["paco_front"]
    S["paco_head"] = pf.crop((0, 0, pf.width, int(pf.height * 0.47)))
    return S


# --------------------------------------------------------------------------- scenografie (resa 3D materica, vedi look.py)

import look as L

DAY_STOPS = [(0, (58, 124, 206)), (0.55, (148, 194, 232)), (1, (226, 236, 246))]
NIGHT_STOPS = [(0, (9, 7, 28)), (0.55, (38, 25, 74)), (1, (84, 60, 120))]
HAZE_DAY = (172, 196, 228)


def soft_ellipse(size, color, alpha, blur):
    w, h = size
    pad = blur * 3
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), color + (0,))
    ImageDraw.Draw(im).ellipse((pad, pad, pad + w, pad + h), fill=color + (alpha,))
    return im.filter(ImageFilter.GaussianBlur(blur))


def glow(frame, x, y, r, color, alpha):
    g = soft_ellipse((int(r * 2), int(r * 2)), color, int(min(255, alpha)), int(r * 0.35))
    frame.paste(g, (int(x - g.width / 2), int(y - g.height / 2)), g)


def add_glow(arr, x, y, r, color, k):
    """Bagliore additivo su un array float (per le luci)."""
    h, w = arr.shape[:2]
    x0, x1, y0, y1 = max(0, int(x - 3 * r)), min(w, int(x + 3 * r)), max(0, int(y - 3 * r)), min(h, int(y + 3 * r))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    g = np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / (r * r)))[:, :, None] * k
    arr[y0:y1, x0:x1] += np.array(color, np.float32) * g


def post(f, i, sat=1.0, gain=(1, 1, 1), lift=(6, 4, 10), vig=0.36, bloom_k=0.5):
    f = L.bloom(f, 205, bloom_k)
    f = L.grade(f, lift, gain, sat)
    f = vignette(f, vig)
    return L.film_grain(f, 4, i)


def char(spr, mul=(1, 1, 1), add=(0, 0, 0), wrap=None, wrap_k=0.35):
    out = grade(spr, mul, add)
    if wrap:
        out = L.light_wrap(out, wrap, wrap_k)
    return out


def layer(img, blur=0.0):
    return img.filter(ImageFilter.GaussianBlur(blur)) if blur else img


def rgba(arr):
    return L.to_img(arr).convert("RGBA")


# ---- oggetti in "plastilina"

def clay_rock(w, h, seed, col=(126, 120, 116), snow=False):
    rng = random.Random(seed)
    c = L.Clay(w + 20, h + 20)
    pts = []
    for k in range(9):
        a = math.pi + k * math.pi / 8
        r = rng.uniform(0.75, 1.0)
        pts.append((10 + w / 2 + math.cos(a) * w / 2 * r, 10 + h + math.sin(a) * h * r))
    c.part(lambda d: d.polygon(pts, fill=255), col, R=max(8, h * 0.45), spec=0.08, tex=0.14, tex_scale=8, seed=seed)
    if snow:
        c.part(lambda d: d.ellipse((10 + w * 0.2, 10 + h * 0.05, 10 + w * 0.75, 10 + h * 0.35), fill=255), (240, 244, 252),
               R=10, spec=0.1, tex=0.03, shadow=0.15)
    return c.done()


def influencer_body():
    c = L.Clay(700, 1060)
    skin, shirt, shorts, hair = (226, 172, 136), (246, 204, 44), (60, 128, 196), (88, 56, 34)
    c.part(lambda d: d.rounded_rectangle((250, 700, 320, 990), 34, fill=255), skin, R=30, tex=0.03)
    c.part(lambda d: d.rounded_rectangle((370, 700, 440, 990), 34, fill=255), skin, R=30, tex=0.03)
    c.part(lambda d: d.ellipse((225, 970, 335, 1020), fill=255), (36, 168, 228), R=14, spec=0.4)
    c.part(lambda d: d.ellipse((355, 970, 465, 1020), fill=255), (36, 168, 228), R=14, spec=0.4)
    c.part(lambda d: d.polygon([(215, 570), (475, 570), (495, 770), (365, 770), (345, 660), (325, 770), (195, 770)], fill=255),
           shorts, R=40, tex=0.08)
    def torso(d):
        d.polygon([(200, 300), (490, 300), (465, 610), (225, 610)], fill=255)
        d.ellipse((175, 240, 315, 380), fill=255)
        d.ellipse((375, 240, 515, 380), fill=255)
        d.rectangle((250, 245, 440, 320), fill=255)
    c.part(torso, shirt, R=60, tex=0.06, tex_scale=10)
    c.part(lambda d: d.rounded_rectangle((318, 190, 372, 270), 20, fill=255), skin, R=20, shadow=0.2)
    c.part(lambda d: d.ellipse((265, 70, 425, 235), fill=255), hair, R=60, spec=0.12, tex=0.2, tex_scale=5)
    c.part(lambda d: d.chord((258, 58, 432, 205), 180, 360, fill=255), (228, 58, 138), R=30, spec=0.2)
    c.part(lambda d: d.rounded_rectangle((318, 128, 372, 152), 8, fill=255), (250, 250, 250), R=8, shadow=0.2)
    # braccio destro alzato col selfie stick
    c.part(lambda d: d.line([(470, 300), (560, 60)], fill=255, width=62), skin, R=28, tex=0.03)
    c.part(lambda d: d.ellipse((525, 20, 600, 95), fill=255), skin, R=30)
    return c.done()


def influencer_arm():
    c = L.Clay(300, 300)
    c.part(lambda d: d.line([(150, 150), (290, 150)], fill=255, width=58), (226, 172, 136), R=27, tex=0.03)
    c.part(lambda d: d.ellipse((250, 116, 296, 184), fill=255), (226, 172, 136), R=24)
    return c.done()


def draw_influencer(fg, body, arm, x, y, t):
    left, top = int(x - 350), int(y)
    d = ImageDraw.Draw(fg)
    hand = (left + 562, top + 58)
    tip = (hand[0] - 270, hand[1] - 330 + 14 * math.sin(t * 2))
    d.line([hand, tip], fill=(26, 26, 30, 255), width=14)
    rr = 96
    g = soft_ellipse((2 * rr + 70, 2 * rr + 70), (255, 252, 240), 150, 22)
    fg.paste(g, (int(tip[0] - g.width / 2), int(tip[1] - g.height / 2)), g)
    d.ellipse((tip[0] - rr, tip[1] - rr, tip[0] + rr, tip[1] + rr), outline=(255, 252, 244, 255), width=24)
    d.rounded_rectangle((tip[0] - 34, tip[1] - 62, tip[0] + 34, tip[1] + 62), 10, fill=(18, 18, 22, 255))
    ang = 200 + 38 * math.sin(t * 5.5)
    r = arm.rotate(-ang, resample=Image.BICUBIC)
    fg.paste(r, (left + 215 - 150, top + 300 - 150), r)
    fg.paste(body, (left, top), body)


def ship_sprite(scale=1.0):
    w, h = int(780 * scale), int(400 * scale)
    s = scale
    c = L.Clay(w, h)
    metal, dark, light = (112, 100, 132), (70, 62, 88), (150, 140, 172)
    E = lambda b: (lambda d: d.ellipse(tuple(v * s for v in b), fill=255))
    c.part(E((40, 160, 720, 310)), dark, R=60 * s, spec=0.5, shin=30, tex=0.05, rim=(140, 255, 90), rim_k=0.25)
    c.part(E((60, 135, 690, 275)), metal, R=70 * s, spec=0.55, shin=30, tex=0.05)
    c.part(E((20, 190, 210, 295)), metal, R=40 * s, spec=0.5, shin=30)
    c.part(E((560, 200, 750, 285)), dark, R=40 * s, spec=0.5, shin=30)
    c.part(E((120, 100, 430, 205)), light, R=50 * s, spec=0.6, shin=36)
    c.part(E((390, 122, 650, 232)), metal, R=50 * s, spec=0.6, shin=36)
    c.part(lambda d: d.rectangle((606 * s, 58 * s, 618 * s, 140 * s), fill=255), dark, R=6 * s, spec=0.4)
    c.part(E((594, 40, 630, 76)), light, R=16 * s, spec=0.7)
    c.part(E((250, 30, 425, 152)), (90, 196, 96), R=60 * s, spec=0.9, shin=50, tex=0.02, rim=(220, 255, 200), rim_k=0.5)
    c.part(E((240, 272, 530, 345)), (40, 36, 54), R=20 * s, spec=0.3)
    return c.done()


SHIP_LIGHTS = [((90, 236), (157, 255, 58), 1.7), ((205, 258), (255, 70, 200), 2.9), ((335, 266), (255, 220, 60), 1.1),
               ((475, 262), (157, 255, 58), 2.3), ((605, 246), (80, 200, 255), 3.7), ((695, 236), (255, 120, 40), 1.4)]


def ship_frame(ship, t, scale=1.0):
    im = ship.copy()
    d = ImageDraw.Draw(im)
    for (x, y), c, f in SHIP_LIGHTS:
        x, y = x * scale, y * scale
        on = math.sin(t * f * 2 * math.pi + x) > -0.2
        r = (12 if on else 8) * scale
        if on:
            g = soft_ellipse((int(r * 5), int(r * 5)), c, 160, int(r))
            im.alpha_composite(g, (max(0, int(x - g.width / 2)), max(0, int(y - g.height / 2))))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(c + (255,)) if on else (54, 50, 64, 255))
        d.ellipse((x - r * 0.45, y - r * 0.6, x - r * 0.05, y - r * 0.2), fill=(255, 255, 255, 200 if on else 60))
    return im


class Beam:
    """Raggio traente: cilindro di luce con bordi più luminosi, bande e pulviscolo."""

    def __init__(self, seed=0):
        rng = random.Random(seed)
        self.motes = [(rng.random(), rng.random(), rng.uniform(1.5, 4), rng.uniform(0.4, 1.0)) for _ in range(70)]

    def apply(self, frame, top, bottom, t, strength=1.0, speed=260, y0=0, y1=H):
        (tc, tw), (bc, bw) = top, bottom
        f = np.asarray(frame, np.float32).copy()
        ys = np.arange(y0, y1, dtype=np.float32)
        k = (ys - y0) / max(1, (y1 - y0))
        c = tc + (bc - tc) * k
        hw = tw + (bw - tw) * k
        xs = np.arange(W, dtype=np.float32)[None, :]
        u = (xs - c[:, None]) / hw[:, None]
        m = L.smooth(1.05, 0.8, np.abs(u))
        bands = 0.5 + 0.5 * np.sin((ys[:, None] + speed * t) / 30.0)
        a = m * (0.13 + 0.22 * u * u + 0.08 * bands) * strength
        f[y0:y1] = f[y0:y1] * (1 - a[:, :, None]) + np.array(GREEN, np.float32) * a[:, :, None] * 1.1
        for px, py, r, sp in self.motes:
            yy = y1 - ((py * (y1 - y0) + speed * 0.4 * sp * t) % (y1 - y0))
            kk = (yy - y0) / max(1, (y1 - y0))
            xx = tc + (bc - tc) * kk + (px - 0.5) * 1.7 * (tw + (bw - tw) * kk)
            add_glow(f, xx, yy, r * 2.2, (200, 255, 160), 0.5 * strength)
        return Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))


def selfie_screen(S, w, h, mode, t):
    scr = L.to_img(L.sky(w, h, [(0, (80, 150, 222)), (1, (214, 234, 248))]))
    sd = ImageDraw.Draw(scr)
    sd.polygon([(0, h * 0.75), (w * 0.3, h * 0.6), (w * 0.6, h * 0.72), (w, h * 0.58), (w, h), (0, h)], fill=(236, 242, 250))
    head = S["boy_head"]
    hh = int(h * 0.82)
    hd = head.resize((int(head.width * hh / head.height), hh), Image.LANCZOS)
    if mode == "aura":
        g = soft_ellipse((int(hd.width * 1.2), int(hd.height * 0.55)), GREEN, 230, 30)
        scr.paste(g, (int(w / 2 - g.width / 2), int(h - hh - 30)), g)
    scr.paste(hd, (int(w / 2 - hd.width / 2), h - hh), hd)
    rng = random.Random(int(t * 8))
    d = ImageDraw.Draw(scr)
    if mode == "sparkle":
        for _ in range(26):
            x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(4, 13)
            col = rng.choice([(255, 120, 200), (255, 240, 120), (140, 220, 255), (200, 160, 255)])
            d.polygon([(x, y - 2 * r), (x + r * 0.4, y), (x, y + 2 * r), (x - r * 0.4, y)], fill=col)
            d.polygon([(x - 2 * r, y), (x, y + r * 0.4), (x + 2 * r, y), (x, y - r * 0.4)], fill=col)
    elif mode == "ears":
        ex = w / 2
        for s in (-1, 1):
            d.ellipse((ex + s * w * 0.27 - 45, h * 0.12, ex + s * w * 0.27 + 45, h * 0.12 + 150), fill=(150, 96, 60))
        d.ellipse((ex - 26, h * 0.52, ex + 26, h * 0.52 + 36), fill=(30, 20, 20))
    elif mode == "glitter":
        for _ in range(140):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            col = (rng.randint(150, 255), rng.randint(150, 255), rng.randint(150, 255))
            d.rectangle((x, y, x + 5, y + 5), fill=col)
    elif mode == "sepia":
        a = np.asarray(scr).astype(np.float32)
        g = a.mean(axis=2, keepdims=True)
        scr = Image.fromarray(np.clip(g * np.array([1.08, 0.88, 0.66]), 0, 255).astype(np.uint8))
    return scr


def phone_body(w, h, rot=0):
    c = L.Clay(w + 40, h + 40)
    c.part(lambda d: d.rounded_rectangle((20, 20, w + 19, h + 19), 56, fill=255), (24, 24, 30), R=26, spec=0.7, shin=40,
           tex=0.02, rim=(120, 120, 140), rim_k=0.4)
    return c.done()


def heart(d, x, y, s, col):
    d.ellipse((x - s, y - s * 0.6, x, y + s * 0.3), fill=col)
    d.ellipse((x, y - s * 0.6, x + s, y + s * 0.3), fill=col)
    d.polygon([(x - s, y - s * 0.1), (x + s, y - s * 0.1), (x, y + s)], fill=col)


# ---- paesaggi riutilizzati

def summit_night(w, h, seed=1, peak_x=560, base=1900, peak_y=1560, far_y=1660):
    bg = rgba(L.night_sky(w, h, NIGHT_STOPS, seed))
    far = L.mountain(w, h, L.ridge_top(w, far_y, 110, seed + 2), (52, 52, 88), (176, 186, 226), (70, 76, 130), seed=seed + 2,
                     haze=((60, 44, 100), 0.35), snow_depth=140, amb=0.28)
    near = L.mountain(w, h, L.ridge_top(w, base, 30, seed + 4, peaks=[(peak_x, peak_y, 430)]), (44, 42, 74), (214, 218, 246),
                      (84, 92, 150), seed=seed + 4, snow_depth=230, amb=0.26)
    bg.alpha_composite(layer(far, 1.2))
    bg.alpha_composite(near)
    return bg


def summit_day(w, h, seed=20, sea_y=(1150, 1300), clouds=0.9):
    bg = rgba(L.sky(w, h, DAY_STOPS, sun=(w * 0.2, 260, 520, (255, 250, 232), 0.45), clouds=clouds, seed=seed))
    for k, base in enumerate(sea_y):
        lay = L.mountain(w, h, L.ridge_top(w, base, 120 - 30 * k, seed + k), (124, 132, 168), (244, 246, 252), (160, 172, 212),
                         seed=seed + k, haze=(HAZE_DAY, 0.5 - 0.2 * k), snow_depth=170)
        bg.alpha_composite(layer(lay, 2.0 - k))
    return bg


# --------------------------------------------------------------------------- shot

NIGHT = dict(mul=(0.62, 0.66, 0.84), add=(8, 22, 10), wrap=(120, 230, 90))
TEMPLE = dict(mul=(0.5, 0.64, 0.52), add=(6, 20, 6), wrap=(120, 220, 90))
DAYC = dict(mul=(1.0, 1.0, 1.02), add=(0, 0, 0), wrap=(200, 220, 245), wrap_k=0.25)


def shot01(S, n):
    bg = summit_night(W, H, 1)
    a = np.asarray(bg.convert("RGB"), np.float32).copy()
    add_glow(a, 560, 1580, 300, (60, 140, 30), 0.9)  # il raggio illumina la vetta
    bg = L.to_img(a)
    boy, boyb, paco = char(S["boy_front"], **NIGHT), char(S["boy_blink"], **NIGHT), char(S["paco_side"], **NIGHT)
    beam = Beam(1)
    tw = random.Random(9)
    tw_pts = [(tw.uniform(0, W), tw.uniform(0, H * 0.6)) for _ in range(30)]
    for i in range(n):
        t = i / FPS
        f = bg.copy()
        d = ImageDraw.Draw(f)
        for k, (x, y) in enumerate(tw_pts):
            if math.sin(t * 5 + k * 1.7) > 0.6:
                d.ellipse((x - 2.5, y - 2.5, x + 2.5, y + 2.5), fill=(255, 255, 230))
        f = beam.apply(f, (540, 130), (540, 390), t)
        rise = 46 * t
        place(f, paco, 800, 1080 - rise + 10 * math.sin(t * 3), 430, rot=7 * math.sin(t * 7), anchor="center", key="p1")
        spr = boyb if 1.55 < t < 1.75 else boy
        place(f, spr, 470, 1610 - rise, 1000, rot=1.6 * math.sin(t * 1.2), key="b1" + str(spr is boyb))
        yield post(f, i)


def shot03(S, n):
    pw = W + 900
    sky = rgba(L.sky(pw, H, DAY_STOPS, sun=(260, 240, 520, (255, 250, 232), 0.45), clouds=1.0, seed=2))
    far = layer(L.mountain(pw, H, L.ridge_top(pw, 930, 240, 11), (122, 130, 166), (244, 246, 252), (160, 172, 212),
                           seed=11, haze=(HAZE_DAY, 0.45), snow_depth=220), 1.6)
    mid = layer(L.mountain(pw, H, L.ridge_top(pw, 1230, 120, 12), (116, 104, 94), (238, 242, 250), (150, 160, 200), seed=12,
                           haze=(HAZE_DAY, 0.18), snow_depth=110, rock2=(98, 94, 108)), 0.8)
    gr = L.ground(pw, H, 1380, (150, 134, 112), (122, 114, 104), seed=4)
    path = L.ground(pw, H, 1462, (192, 176, 148), seed=5, scale=40)
    pa = np.asarray(path).copy()
    yy = np.arange(H)[:, None]
    pa[:, :, 3] = (pa[:, :, 3] * np.clip((1612 - yy) / 6, 0, 1)).astype(np.uint8)
    gr.alpha_composite(Image.fromarray(pa))
    rng = random.Random(13)
    for k in range(34):
        x, y = rng.uniform(0, pw), rng.uniform(1395, H)
        if 1440 < y < 1640:
            continue
        s = (0.4 + 0.9 * (y - 1380) / 540) * rng.uniform(30, 80)
        r = clay_rock(int(s * 1.6), int(s), 100 + k)
        gr.paste(r, (int(x), int(y - s)), r)
    paco = char(S["paco_side"].transpose(Image.FLIP_LEFT_RIGHT), **DAYC)
    side, b34 = char(S["boy_side"], **DAYC), char(S["boy_34"], **DAYC)
    body, arm = influencer_body(), influencer_arm()
    for i in range(n):
        t = i / FPS
        cam = 55 * t
        f = sky.crop((int(0.05 * cam), 0, int(0.05 * cam) + W, H))
        f.paste(far, (int(-0.15 * cam), 0), far)
        f.paste(mid, (int(-0.4 * cam), 0), mid)
        f.paste(gr, (int(-cam), 0), gr)
        f = f.convert("RGB")
        bx = 110 + 52 * t
        step = abs(math.sin(t * math.pi * 1.9))
        glance = 2.8 < t < 4.6
        spr = b34 if glance else side
        shadow(f, bx, 1532, 190, 34)
        place(f, spr, bx, 1535 - 12 * step, 760, rot=1.2 * math.sin(t * math.pi * 1.9), key="b3" + str(glance))
        px = bx + 300
        shadow(f, px, 1548, 280, 30)
        place(f, paco, px, 1550 - 10 * abs(math.sin(t * math.pi * 2.6 + 1)), 360, key="p3")
        fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_influencer(fg, body, arm, 1010 - 18 * t, 860, t)
        fg = fg.filter(ImageFilter.GaussianBlur(6))
        f.paste(fg, (0, 0), fg)
        yield post(f, i, vig=0.3, lift=(8, 6, 4))


def shot04(S, n):
    bg = summit_day(W, H, 20)
    snow = L.ground(W, H, 1440, (238, 242, 252), (220, 228, 244), seed=24, scale=90, snow=True)
    bg.alpha_composite(snow)
    bg = bg.convert("RGB")
    back = char(S["boy_back"], **DAYC)
    paco = char(S["paco_front"], **DAYC)
    pw_, ph_ = 330, 610
    body = phone_body(pw_, ph_)
    flakes = [(random.uniform(0, W), random.uniform(0, H), random.uniform(2, 5)) for _ in range(90)]
    modes = ["none", "sparkle", "ears", "glitter", "sepia"]
    for i in range(n):
        t = i / FPS
        f = bg.copy()
        place(f, paco, 905, 1110 + 6 * math.sin(t * 11), 900, anchor="top",
              rot=(-5 * ease((t - 4.4) * 3) * (1 - ease((t - 5.6) * 3))), key="p4")
        breath = 4 * math.sin(t * 1.6)
        ph = body.copy()
        mode = (modes[int(t / 0.5) % len(modes)] if t > 0.5 else "none") if t < 6.0 else "aura"
        scr = selfie_screen(S, pw_ - 26, ph_ - 26, mode, t).convert("RGBA")
        sm = Image.new("L", scr.size, 0)
        ImageDraw.Draw(sm).rounded_rectangle((0, 0, scr.width - 1, scr.height - 1), 40, fill=255)
        ph.paste(scr, (33, 33), sm)
        ImageDraw.Draw(ph).polygon([(40, 40), (150, 40), (60, 300), (40, 300)], fill=(255, 255, 255, 26))  # riflesso sul vetro
        ph = ph.rotate(-5, resample=Image.BICUBIC, expand=True)
        f.paste(ph, (int(735 - ph.width / 2), int(560 + breath - ph.height / 2)), ph)
        hat_c = (360, 760 + breath + 2240 * 0.085)
        if t > 6.3:
            k = 0.5 + 0.5 * math.sin((t - 6.3) * 9)
            glow(f, hat_c[0], hat_c[1], 330, GREEN, 120 + 90 * k)
        place(f, back, 360, 760 + breath, 2240, anchor="top", key="b4")
        d = ImageDraw.Draw(f)
        for j, (x, y, r) in enumerate(flakes):
            xx = (x - 90 * t + 30 * math.sin(t + j)) % W
            yy = (y + 140 * t) % H
            d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(255, 255, 255))
        yield post(f, i, vig=0.3)


def shot05(S, n):
    bg = rgba(L.sky(W, H, DAY_STOPS, sun=(800, 300, 500, (255, 250, 232), 0.4), clouds=0.9, seed=51))
    lay = L.mountain(W, H, L.ridge_top(W, 1420, 140, 52), (124, 132, 168), (244, 246, 252), (160, 172, 212), seed=52,
                     haze=(HAZE_DAY, 0.35), snow_depth=200)
    bg.alpha_composite(lay)
    bg.alpha_composite(L.ground(W, H, 1600, (238, 242, 252), seed=53, snow=True))
    bg = bg.convert("RGB")
    pos, size = place(bg, char(S["boy_front"], **DAYC), 300, 1640, 1150, key="b5")
    glow(bg, pos[0] + size[0] * 0.5, pos[1] + size[1] * 0.13, 130, (170, 210, 255), 60)
    bg = bg.filter(ImageFilter.GaussianBlur(12))
    head = char(S["paco_head"], **DAYC)
    period = 0.55
    for i in range(n):
        t = i / FPS
        f = bg.copy()
        p = (t % period) / period
        jerk = math.exp(-p * 6)
        nb = int(t / period)
        place(f, head, 580, 1990 - 45 * jerk, 1050 * (1 + 0.03 * jerk), rot=-4 + 4 * jerk * (1 if nb % 2 else -1))
        if jerk > 0.25:  # linee dell'abbaio
            d = ImageDraw.Draw(f)
            for k in range(3):
                r = 120 + 70 * k + 140 * (1 - jerk)
                d.arc((560 - r, 980 - r, 560 + r, 980 + r), 235, 305, fill=(255, 255, 255), width=10)
            x = 160 if nb % 2 else 640
            d.text((x, 560 - 30 * (1 - jerk)), "WOF!", font=font(130), fill=(255, 255, 255), stroke_width=10,
                   stroke_fill=(20, 20, 20))
        yield post(f, i, vig=0.3)


def shot06(S, n):
    day = L.sky(W, H, DAY_STOPS, sun=(300, 300, 500, (255, 246, 226), 0.4), clouds=0.7, seed=60)
    eve = L.night_sky(W, H, NIGHT_STOPS, 61, stars=260)
    land = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    land.alpha_composite(layer(L.mountain(W, H, L.ridge_top(W, 1250, 120, 61), (124, 128, 166), (240, 244, 252), (156, 166, 210),
                                          seed=61, haze=(HAZE_DAY, 0.4), snow_depth=150), 1.2))
    land.alpha_composite(L.mountain(W, H, L.ridge_top(W, 1760, 30, 62, peaks=[(540, 1330, 540)]), (100, 94, 112), (242, 244, 252),
                                    (150, 160, 206), seed=62, snow_depth=320))
    la = np.asarray(land).astype(np.float32)
    land_eve = la.copy()
    land_eve[:, :, :3] = land_eve[:, :, :3] * np.array([0.52, 0.5, 0.78]) + np.array([10, 8, 30])
    hikers = [(360, 1452), (432, 1462), (500, 1450)]
    rift = ridge(W, 330, 60, 63, rough=0.6, levels=6)
    rift = [(x, y) for x, y in rift if 130 < x < 950]
    ship = ship_sprite()
    for i in range(n):
        t = i / FPS
        k = ease(t / 3.5)
        sky_a = day * (1 - k) + eve * k
        f = L.to_img(sky_a)
        wdt = 6 + 70 * ease(t / 3)
        rl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x0, x1 = rift[0][0], rift[-1][0]
        tap = [math.sin(math.pi * (x - x0) / (x1 - x0)) ** 0.7 for x, _ in rift]
        top = [(x, y - wdt * tp * (0.7 + 0.3 * math.sin(x * 0.09 + t * 9))) for (x, y), tp in zip(rift, tap)]
        bot = [(x, y + wdt * tp * (0.7 + 0.3 * math.cos(x * 0.07 + t * 7))) for (x, y), tp in zip(rift, tap)]
        ImageDraw.Draw(rl).polygon(top + bot[::-1], fill=GREEN + (255,))
        gl = rl.filter(ImageFilter.GaussianBlur(40))
        f.paste(gl, (0, 0), gl)
        f.paste(rl, (0, 0), rl)
        core = [(x, y - wdt * tp * 0.25) for (x, y), tp in zip(rift, tap)] + [(x, y + wdt * tp * 0.25) for (x, y), tp in zip(rift, tap)][::-1]
        ImageDraw.Draw(f).polygon(core, fill=(236, 255, 220))
        if t > 0.9:
            s = ease((t - 0.9) / 5.2)
            sc = 0.28 + 0.72 * s
            shp = ship_frame(ship, t).resize((int(ship.width * sc), int(ship.height * sc)), Image.LANCZOS)
            place(f, shp, 540 + 30 * math.sin(t * 1.3), 340 + 440 * s + 10 * math.sin(t * 3.1), rot=4 * math.sin(t * 2.3),
                  anchor="center", alpha=min(1, (t - 0.9) * 2))
        lm = la * (1 - k) + land_eve * k
        lim = Image.fromarray(lm.astype(np.uint8), "RGBA")
        f.paste(lim, (0, 0), lim)
        if k > 0.3:  # luce verde dello squarcio sulla neve
            a = np.asarray(f, np.float32).copy()
            add_glow(a, 540, 1340, 420, (50, 120, 20), 0.6 * k)
            f = L.to_img(a)
        d = ImageDraw.Draw(f)
        for j, (x, y) in enumerate(hikers):
            c = (36, 30, 48)
            d.ellipse((x - 9, y - 70, x + 9, y - 52), fill=c)
            d.rounded_rectangle((x - 10, y - 52, x + 10, y - 16), 6, fill=c)
            d.line([(x - 5, y - 16), (x - 9, y)], fill=c, width=6)
            d.line([(x + 5, y - 16), (x + 9, y)], fill=c, width=6)
            lift = ease((t - 1.2 - 0.4 * j) / 1.5) + 0.3 * ease((t - 4 - 0.3 * j) / 1.5)
            hy = y - 40 - 50 * lift
            d.line([(x + 8, y - 46), (x + 16, hy)], fill=c, width=6)
            d.rectangle((x + 10, hy - 14, x + 24, hy), fill=(220, 240, 255))
        f = zoom(f, 1 + 0.1 * ease(t / 7), 540, 1000)
        yield post(f, i)


def shot07(S, n):
    TH = H + 900
    tall = rgba(L.night_sky(W, TH, NIGHT_STOPS, 71, stars=500))
    tall.alpha_composite(layer(L.mountain(W, TH, L.ridge_top(W, 2520, 110, 72), (52, 52, 88), (176, 186, 226), (70, 76, 130),
                                          seed=72, haze=((60, 44, 100), 0.35), snow_depth=140, amb=0.28), 1.2))
    tall.alpha_composite(L.ground(W, TH, 2610, (206, 212, 240), (186, 194, 230), seed=73, scale=80, snow=True))
    tall = tall.convert("RGB")
    boy = char(S["boy_front"], mul=(0.74, 0.8, 0.9), add=(8, 24, 6), wrap=(140, 255, 90), wrap_k=0.45)
    paco = char(S["paco_side"], mul=(0.74, 0.8, 0.9), add=(8, 24, 6), wrap=(140, 255, 90), wrap_k=0.4)
    ship = ship_sprite(2.0)
    beam = Beam(7)
    for i in range(n):
        t = i / FPS
        lift = 700 * ease((t - 1.4) / 6.0)
        cam = 0.8 * lift
        f = tall.crop((0, int(900 - cam), W, int(900 - cam) + H))
        ground_y = 1710 + cam
        feet = ground_y - lift
        bx = 520 + 8 * math.sin(t * 2.2) * (lift > 5)
        hat_y = feet - 1000 * 0.985
        f = beam.apply(f, (540, 60), (bx, 150), t, 1.3, speed=-320, y0=0, y1=max(10, int(hat_y + 90)))
        if ground_y < H + 40:  # luce verde sulla neve
            a = np.asarray(f, np.float32).copy()
            add_glow(a, bx, ground_y, 260, (40, 110, 20), 0.7)
            f = L.to_img(a)
        glow(f, bx, hat_y + 50, 210, GREEN, 120 + 60 * math.sin(t * 10))
        shp = ship_frame(ship, t, 2.0)
        f.paste(shp, (int(540 - shp.width / 2), -560), shp)
        if lift < 5:
            shadow(f, bx, feet, 220, 34)
        place(f, boy, bx, feet, 1000, rot=2 * math.sin(t * 1.7) * min(1, lift / 100), key="b7")
        if t > 2.6:
            tt = t - 2.6
            px, py = bx + 150 + 60 * tt, feet - 520 + 900 * tt * tt
            phn = phone_body(60, 120)
            if py < H + 100:
                place(f, phn, px, py, rot=tt * 260, anchor="center")
        boot = (bx + 70, feet - 30)
        if t < 3.1:
            sq = 1 - 0.1 * ease((t - 2.4) / 0.6)
            shadow(f, 820, ground_y, 280, 30)
            place(f, paco, 820, ground_y, 400 * sq, key="p7" + str(round(sq, 2)))
        elif t < 3.7:
            k = (t - 3.1) / 0.6
            x = 820 + (boot[0] + 120 - 820) * k
            y = (ground_y - 200) * (1 - k) + boot[1] * k - 260 * math.sin(math.pi * k)
            place(f, paco, x, y, 400, rot=-35 * k, anchor="center", key="p7j")
        else:
            wig = 9 * math.sin(t * 9)
            ph = scaled(paco, 400, "p7j")
            r = ph.rotate(-68 + wig, resample=Image.BICUBIC, expand=True)
            f.paste(r, (int(boot[0] - r.width * 0.55), int(boot[1] - 40)), r)
        yield post(f, i)


def shot08(S, n):
    hf = L.fbm(H, W, 220, 7, 81, 0.55) * 120 + L.fbm(H, W, 30, 4, 82, 0.5) * 18
    cracks = L.fbm(H, W, 260, 5, 83, 0.5, ridged=True)
    hf -= L.smooth(0.82, 0.97, cracks) * 26
    nn = L.normals(hf)
    li = L.lit(nn, 0.36, 0.8)
    rock = np.array((132, 128, 134), np.float32)
    lich = L.smooth(0.68, 0.8, L.fbm(H, W, 70, 5, 84))[:, :, None]
    rgb = rock * li[:, :, None] * (1 - lich) + np.array((168, 162, 92), np.float32) * li[:, :, None] * lich
    speck = L.fbm(H, W, 3, 2, 85)[:, :, None]
    rgb *= 0.9 + 0.2 * speck
    bg = rgba(rgb)
    # neve residua negli avvallamenti: chiazze irregolari, gonfiate
    yy = np.linspace(0, 1, H)[:, None]
    edge = np.maximum(L.smooth(0.16, 0.0, yy), L.smooth(0.84, 1.0, yy))
    sn = (L.fbm(H, W, 160, 5, 86, 0.55) + 0.45 * edge - 0.15 * L.smooth(0.3, 0.0, np.abs(yy - 0.5))) > 0.78
    bg.alpha_composite(L.inflate(sn, (242, 246, 252), R=22, spec=0.18, tex=0.05, tex_scale=6, seed=87, amb=0.5))
    bg = bg.convert("RGB")
    shot_img = selfie_screen(S, 520, 520, "aura", 0)
    pacoh = S["paco_head"]
    ph = pacoh.resize((int(pacoh.width * 300 / pacoh.height), 300), Image.LANCZOS)
    shot_img.paste(ph, (330, 230), ph)
    hearts = [(random.uniform(60, 500), random.uniform(0.0, 3.4)) for _ in range(16)]
    lights = [(GREEN, 0.0), ((255, 70, 200), 0.6), ((255, 220, 60), 1.3), ((80, 200, 255), 2.0)]
    sw, sh = 580, 1140
    body = phone_body(sw, sh)
    for i in range(n):
        t = i / FPS
        f = bg.copy()
        scr = Image.new("RGB", (sw, sh), (16, 16, 20))
        sd = ImageDraw.Draw(scr)
        sd.ellipse((24, 40, 84, 100), fill=(214, 38, 30))
        sd.text((100, 50), "redbuket", font=font(38), fill=(240, 240, 240))
        scr.paste(shot_img, (30, 140))
        prog = ease((t - 0.4) / 1.8)
        if prog < 1:
            sd.text((30, 700), "Caricamento…", font=font(40), fill=(200, 200, 200))
            sd.rounded_rectangle((30, 770, 550, 790), 10, fill=(60, 60, 66))
            sd.rounded_rectangle((30, 770, 30 + 520 * prog, 790), 10, fill=GREEN)
        else:
            sd.text((30, 700), "Pubblicato ✓", font=font(44), fill=GREEN)
            likes = int(1284 * ease((t - 2.3) / 3.3) ** 1.6)
            heart(sd, 50, 800, 34, (255, 80, 110))
            sd.text((100, 790), f"{likes:,}".replace(",", "."), font=font(48), fill=(245, 245, 245))
            sd.text((30, 880), "Contenuto autentico. Zero filtri.", font=font(30), fill=(190, 190, 190))
            for hx, h0 in hearts:
                tt = t - 2.3 - h0
                if 0 < tt < 1.2:
                    heart(sd, hx, 660 - 260 * tt, 26 * (1 - tt / 1.6), (255, 80, 110))
        scr = scr.convert("RGBA")
        ref = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        for col, off in lights:
            tt = t - off
            k = max(0.0, 1 - t / 6.0)
            e = soft_ellipse((260, 120), col, int(150 * k), 30)
            ref.paste(e, (int(-200 + 260 * tt), int(-100 + 380 * tt)), e)
        ImageDraw.Draw(ref).polygon([(0, 0), (220, 0), (0, 700)], fill=(255, 255, 255, 18))
        scr.alpha_composite(ref)
        phone = body.copy()
        m = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, sw - 1, sh - 1), 44, fill=255)
        phone.paste(scr, (20, 20), m)
        phone = phone.rotate(-7, resample=Image.BICUBIC, expand=True)
        shadow(f, 580, 1000, 700, 1240, 150)
        f.paste(phone, (int(540 - phone.width / 2), int(960 - phone.height / 2)), phone)
        yield post(f, i, vig=0.32)


# ---- tempio alieno

def temple_static(width):
    bg = L.sky(width, H, [(0, (5, 9, 7)), (0.6, (10, 20, 14)), (1, (16, 28, 20))])
    fog = L.fbm(H, width, 300, 5, 90, 0.55, sx=2.2)
    bg += (L.smooth(0.45, 0.8, fog) * 26)[:, :, None] * np.array([0.5, 1.0, 0.6])
    img = rgba(bg)
    vx, vy = width / 2, 900
    c = L.Clay(width, H)
    for i in range(7, -1, -1):
        s = 0.25 + 0.14 * i
        w_, h_ = 1400 * s, 2000 * s
        box = (vx - w_ / 2, vy - h_ * 0.62, vx + w_ / 2, vy + h_ * 0.62)
        c.part(lambda d, box=box, s=s: d.arc(box, 180, 360, fill=255, width=int(120 * s)), (58, 66, 58), R=60 * s, spec=0.12,
               tex=0.18, tex_scale=10, rim=(70, 170, 60), rim_k=0.35, amb=0.22, dif=0.6, seed=i)
        for side in (-1, 1):  # colonne
            x = vx + side * (w_ / 2 - 60 * s)
            c.part(lambda d, x=x, s=s: d.rectangle((x - 60 * s, vy, x + 60 * s, 1450 + 40 * s), fill=255), (54, 62, 54),
                   R=50 * s, spec=0.1, tex=0.18, tex_scale=10, rim=(70, 170, 60), rim_k=0.3, amb=0.22, dif=0.6, seed=10 + i)
    img.alpha_composite(c.done())
    fl = L.ground(width, H, 1450, (26, 40, 30), seed=91, scale=120)
    img.alpha_composite(fl)
    return img, [(vx, vy, 0.25 + 0.14 * i, i) for i in range(8)]


def temple_frame(base, arches, t_lights, lit_all, hat_glow=1.0):
    a = np.asarray(base.convert("RGB"), np.float32).copy()
    for vx, vy, s, i in arches:
        on = lit_all or (t_lights is not None and t_lights > 0.45 * (7 - i))
        if not on:
            continue
        w_, h_ = 1400 * s, 2000 * s
        for side in (-1, 1):
            lx, ly = vx + side * w_ / 2, vy + h_ * 0.1
            add_glow(a, lx, ly, 26 * s + 6, (120, 255, 80), 1.4)
            add_glow(a, lx, ly, 120 * s + 20, (40, 120, 30), 0.6)
            add_glow(a, lx, 1500 + 160 * s, 50 * s + 10, (40, 120, 30), 0.35)  # riflesso sul pavimento
    if hat_glow:
        add_glow(a, vx, 960, 220, (190, 40, 20), 0.9 * hat_glow)
        add_glow(a, vx, 1560, 120, (150, 30, 15), 0.5 * hat_glow)  # riflesso
    return L.to_img(a)


def alien_kit(seed):
    rng = random.Random(seed)
    kit = []
    for k in range(8):
        bw_, bh_ = rng.uniform(120, 170), rng.uniform(190, 260)
        col = (rng.randint(44, 64), rng.randint(70, 92), rng.randint(52, 70))
        body = L.Clay(int(bw_) + 20, int(bh_) + 20).part(
            lambda d: d.ellipse((10, 10, bw_ + 10, bh_ + 10), fill=255), col, R=50, spec=0.25, shin=16, tex=0.12, tex_scale=8,
            rim=(110, 230, 80), rim_k=0.5, amb=0.25, seed=seed + k).done()
        kind = rng.choice(["round", "tall", "antenna", "wide"])
        hr = rng.uniform(42, 60)
        hw, hh = {"round": (2 * hr, 2 * hr), "tall": (1.4 * hr, 2.5 * hr), "antenna": (2 * hr, 2 * hr), "wide": (3 * hr, 1.4 * hr)}[kind]
        extra = 2.2 * hr if kind == "antenna" else 0
        hc = L.Clay(int(hw + 40), int(hh + extra + 40))
        if kind == "antenna":
            for s in (-1, 1):
                ax = 20 + hw / 2 + s * hw * 0.35
                hc.part(lambda d, ax=ax, s=s: d.line([(ax, 20 + extra + hh * 0.2), (ax + s * hr * 0.4, 30)], fill=255, width=10),
                        col, R=5, rim=(110, 230, 80), amb=0.25)
                hc.part(lambda d, ax=ax, s=s: d.ellipse((ax + s * hr * 0.4 - 11, 19, ax + s * hr * 0.4 + 11, 41), fill=255),
                        GREEN, R=8, spec=0.8, amb=0.9, shadow=0)
        hc.part(lambda d: d.ellipse((20, 20 + extra, 20 + hw, 20 + extra + hh), fill=255), col, R=40, spec=0.3, tex=0.1,
                tex_scale=8, rim=(110, 230, 80), rim_k=0.55, amb=0.25)
        kit.append((body, hc.done(), bh_))
    return kit


def alien_row(f, kit, y, n, scale, t, seed, blur=0):
    rng = random.Random(seed)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bow = 0.5 - 0.5 * math.cos(2 * math.pi * t / 2.2)
    for k in range(n):
        body, head, bh_ = kit[rng.randrange(len(kit))]
        x = (k + 0.5) * W / n + rng.uniform(-30, 30)
        b = body.resize((int(body.width * scale), int(body.height * scale)), Image.BILINEAR)
        hd = head.resize((int(head.width * scale), int(head.height * scale)), Image.BILINEAR)
        hy = y - bh_ * scale * 0.95 + 60 * scale * bow
        lay.paste(hd, (int(x - hd.width / 2), int(hy - hd.height * 0.7)), hd)
        lay.paste(b, (int(x - b.width / 2), int(y - b.height * 0.75)), b)
    if blur:
        lay = lay.filter(ImageFilter.GaussianBlur(blur))
    f.paste(lay, (0, 0), lay)


def shot09a(S, n):
    width = W + 300
    base, arches = temple_static(width)
    hat = S["hat"]
    ped = L.Clay(240, 540)
    ped.part(lambda d: d.rectangle((50, 50, 190, 540), fill=255), (60, 66, 60), R=50, spec=0.2, tex=0.16, tex_scale=8,
             rim=(200, 70, 40), rim_k=0.35, amb=0.25)
    ped.part(lambda d: d.rounded_rectangle((10, 10, 230, 64), 18, fill=255), (72, 78, 72), R=24, spec=0.3, tex=0.16,
             tex_scale=8, rim=(220, 80, 40), rim_k=0.4, amb=0.3)
    ped = ped.done()
    kit = alien_kit(95)
    motes = [(random.uniform(-200, 200), random.uniform(0, 1100), random.uniform(1, 3)) for _ in range(60)]
    for i in range(n):
        t = i / FPS
        world = temple_frame(base, arches, t, False, 1.0)
        cx = width / 2
        cone = Image.new("RGBA", world.size, (0, 0, 0, 0))
        ImageDraw.Draw(cone).polygon([(cx - 40, 0), (cx + 40, 0), (cx + 250, 1120), (cx - 250, 1120)], fill=(255, 236, 200, 44))
        cone = cone.filter(ImageFilter.GaussianBlur(24))
        world.paste(cone, (0, 0), cone)
        d = ImageDraw.Draw(world)
        for mx, my, r in motes:
            yy = (my + 30 * t) % 1100
            xx = cx + mx * (yy / 1100)
            d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(255, 240, 210))
        world.paste(ped, (int(cx - 120), 1000), ped)
        place(world, hat, cx, 1030, 220, rot=2 * math.sin(t * 1.5), key="hat")
        off = 300 * (1 - ease(t / 5.5))
        f = world.crop((int(off), 0, int(off) + W, H))
        alien_row(f, kit, 1660, 6, 1.0, t, 91, blur=1)
        alien_row(f, kit, 1900, 4, 1.45, t - 0.1, 92, blur=3)
        yield post(f, i, vig=0.5, bloom_k=0.7)


def shot09b(S, n):
    base, arches = temple_static(W)
    bg = temple_frame(base, arches, None, True, 0.7).filter(ImageFilter.GaussianBlur(7))
    boy = char(S["boy_hatless"], **TEMPLE)
    boyb = char(S["boy_hatless_blink"], **TEMPLE)
    paco = char(S["paco_front"], **TEMPLE)
    kit = alien_kit(95)
    for i in range(n):
        t = i / FPS
        f = bg.copy()
        place(f, paco, 840, 1180, 980, anchor="top", rot=10 * ease((t - 1.0) / 0.6), key="p9")
        spr = boyb if 2.1 < t < 2.3 else boy
        place(f, spr, 400, 470, 2150, anchor="top", key="b9" + str(spr is boyb))
        alien_row(f, kit, 2020, 4, 1.7, t, 93, blur=10)
        yield post(f, i, vig=0.5, bloom_k=0.6)


SHOTS = {"01": shot01, "03": shot03, "04": shot04, "05": shot05, "06": shot06, "07": shot07,
         "08": shot08, "09a": shot09a, "09b": shot09b}


def render_shot(sid, fn, S, dur):
    CLIPS.mkdir(parents=True, exist_ok=True)
    n = int(round(dur * FPS))
    out = CLIPS / f"shot{sid}.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for k, fr in enumerate(fn(S, n)):
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    _cache.clear()
    print(f"  shot {sid}: {n} frame -> {out.relative_to(ROOT)}")


# --------------------------------------------------------------------------- audio

VOICE_SPEC = {
    # id voce: (modello, length_scale, filtro ffmpeg)
    "red": ("it_IT-riccardo-x_low", 1.18, "asetrate=22050*0.94,aresample=48000,atempo=1.0638"),
    "infl": ("it_IT-riccardo-x_low", 0.82, "asetrate=22050*1.16,aresample=48000,atempo=0.862,volume=1.2"),
    "alien": ("it_IT-riccardo-x_low", 1.35, "asetrate=22050*0.72,aresample=48000,atempo=1.389,aecho=0.8:0.7:60|120:0.35|0.25,volume=1.4"),
    "small": ("it_IT-riccardo-x_low", 1.25, "asetrate=22050*0.96,aresample=48000,atempo=1.0417,volume=0.8"),
}
VO_VOICE = {"01": "red", "03": "infl", "04": "red", "05": "red", "09a": "alien", "09b": "small"}


def fetch_voice(name):
    VOICES.mkdir(parents=True, exist_ok=True)
    onnx = VOICES / f"{name}.onnx"
    if not onnx.exists():
        spk, q = name.split("-")[1], name.split("-")[2]
        base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/{spk}/{q}/{name}"
        for ext in (".onnx", ".onnx.json"):
            subprocess.run(["curl", "-sSfL", "-o", str(VOICES / (name + ext)), base + ext], check=True)
    return onnx


def make_vo(spec):
    VO.mkdir(parents=True, exist_ok=True)
    for v in spec["vo"]:
        model, ls, af = VOICE_SPEC[VO_VOICE[v["id"]]]
        raw = VO / f"{v['id']}_raw.wav"
        subprocess.run([sys.executable, "-m", "piper", "-m", str(fetch_voice(model)), "--length-scale", str(ls),
                        "-f", str(raw)], input=v["text"].encode(), check=True, stderr=subprocess.DEVNULL)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", af + ",highpass=f=90",
                        "-ar", "48000", str(VO / f"{v['id']}.wav")], check=True)
        raw.unlink()
    print(f"  voci: {len(spec['vo'])} battute -> {VO.relative_to(ROOT)}")


def make_music(seconds=48.5, bpm=88, sr=44100):
    rng = np.random.default_rng(7)
    n = int(seconds * sr)
    out = np.zeros(n, np.float32)
    beat = 60 / bpm
    t_ = np.arange(int(sr * 0.5)) / sr

    def add(sig, at):
        i = int(at * sr)
        j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[: j - i]

    kick = np.sin(2 * np.pi * (48 + 90 * np.exp(-t_ * 28)) * t_) * np.exp(-t_ * 9) * 0.9
    noise = rng.normal(0, 1, len(t_)).astype(np.float32)
    snare = (np.convolve(noise, np.ones(3) / 3, "same") * np.exp(-t_ * 22) * 0.35 + np.sin(2 * np.pi * 190 * t_) * np.exp(-t_ * 30) * 0.3)
    hat = np.diff(noise, prepend=0) * np.exp(-t_ * 90) * 0.12
    chords = [[57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 65], [52, 55, 59, 62]]  # Am7 Fmaj7 G7 Em7
    bars = int(seconds / (4 * beat)) + 1
    for b in range(bars):
        t0 = b * 4 * beat
        notes = chords[b % 4]
        dur = 4 * beat
        tt = np.arange(int(dur * sr)) / sr
        pad = np.zeros_like(tt)
        for m in notes:
            fr = 440 * 2 ** ((m - 69) / 12)
            for det in (-0.12, 0.1):
                pad += np.sign(np.sin(2 * np.pi * fr * (1 + det / 100) * tt)) * 0.5 + np.sin(2 * np.pi * fr * tt)
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (dur - tt) / 0.3)
        pad = np.convolve(pad, np.ones(28) / 28, "same") * env * 0.028
        add(pad.astype(np.float32), t0)
        for k in range(4):
            bt = t0 + k * beat
            add(kick if k in (0, 2) else snare, bt + (0.012 if k % 2 else 0))
            if k == 2 and b % 2:
                add(kick * 0.6, bt + beat * 0.5)
            for h8 in range(2):
                add(hat * (1 if h8 == 0 else 0.6), bt + h8 * beat * 0.55)
        if b % 2 == 1:  # bip giocosi
            for k, m in enumerate([81, 84, 79]):
                fr = 440 * 2 ** ((m - 69) / 12)
                bl = np.sin(2 * np.pi * fr * t_[: int(sr * 0.12)]) * np.exp(-t_[: int(sr * 0.12)] * 25) * 0.12
                add(bl.astype(np.float32), t0 + 2 * beat + k * beat * 0.5)
    out = np.tanh(out * 1.3) * 0.8
    MUSIC.parent.mkdir(parents=True, exist_ok=True)
    wav = MUSIC.with_suffix(".wav")
    with wave.open(str(wav), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", "lowpass=f=7000,aecho=0.6:0.4:180:0.2",
                    "-ac", "2", "-b:a", "192k", str(MUSIC)], check=True)
    wav.unlink()
    print(f"  musica: {seconds:.1f}s -> {MUSIC.relative_to(ROOT)}")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="id degli shot da rifare (es. 04 07)")
    ap.add_argument("--bandana", default="mustard", choices=["mustard", "orange", "teal", "red"])
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--no-subs", action="store_true")
    args = ap.parse_args()

    spec = json.loads((ROOT / "shots.json").read_text(encoding="utf-8"))
    print("personaggi ...")
    S = make_cutouts(args.bandana)
    for shot in spec["shots"]:
        sid = shot["id"]
        if sid not in SHOTS or (args.only and sid not in args.only):
            continue
        render_shot(sid, SHOTS[sid], S, shot["end"] - shot["start"])
    if not args.no_audio:
        make_vo(spec)
        make_music(spec["music"]["cut_at"] + 0.5)
    out = BUILD / "red-bucket-boy_ep01_motioncomic.mp4"
    master = BUILD / "master.mp4"
    cmd = [sys.executable, str(ROOT / "assemble.py"), "--clips-dir", str(CLIPS), "--vo-dir", str(VO),
           "--music", str(MUSIC), "--out", str(master)]
    if not args.no_subs:
        cmd.append("--subs")
    subprocess.run(cmd, check=True)
    # la grana per-frame gonfia il bitrate: versione di consegna a ~6 Mbit/s (adatta a TikTok/Reels/Shorts)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(master), "-c:v", "libx264", "-preset", "slow",
                    "-crf", "21", "-maxrate", "6M", "-bufsize", "12M", "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", str(out)], check=True)
    print(f"-> {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
