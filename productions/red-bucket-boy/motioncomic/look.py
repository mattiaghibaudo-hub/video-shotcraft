"""Resa "3D materico" per le scenografie del motion comic.

Le schede dei personaggi sono render 3D con materiali morbidi (lana, nylon, velluto)
e luce da studio dall'alto a sinistra. Qui ogni elemento di scena segue la stessa logica:
  - fbm / ridged noise -> rilievi illuminati (montagne, roccia, neve, nuvole);
  - inflate() -> forme 2D gonfiate in volumi "plastilina" con luce, speculare,
    rim light e grana di materiale (influencer, alieni, astronave, archi, piedistallo);
  - post: bloom, profondità di campo, grana, color grading.
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

LIGHT = np.array([-0.52, -0.62, 0.59], np.float32)  # dall'alto a sinistra, come nelle schede
LIGHT /= np.linalg.norm(LIGHT)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def fbm(h, w, scale, octaves=5, seed=0, pers=0.5, ridged=False, sx=1.0, sy=1.0):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cx = max(2, int(w / (scale * sx) * 2 ** o)) + 2
        cy = max(2, int(h / (scale * sy) * 2 ** o)) + 2
        g = rng.random((cy, cx)).astype(np.float32)
        lay = np.asarray(Image.fromarray(g, "F").resize((w, h), Image.BICUBIC), np.float32)
        if ridged:
            lay = (1 - np.abs(2 * lay - 1)) ** 2
        out += amp * lay
        tot += amp
        amp *= pers
    return out / tot


def fbm1d(w, scale, octaves=6, seed=0, pers=0.5):
    rng = np.random.default_rng(seed)
    out = np.zeros(w, np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cx = max(2, int(w / scale * 2 ** o)) + 3
        g = rng.random((1, cx)).astype(np.float32)
        out += amp * np.asarray(Image.fromarray(g, "F").resize((w, 1), Image.BICUBIC), np.float32)[0]
        tot += amp
        amp *= pers
    return out / tot


def normals(hf):
    gy, gx = np.gradient(hf)
    n = np.dstack([-gx, -gy, np.ones_like(hf)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


def lit(n, amb=0.35, dif=0.75, light=LIGHT):
    return amb + dif * np.clip((n * light).sum(axis=2), 0, 1)


def to_img(rgb, alpha=None):
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    if alpha is None:
        return Image.fromarray(rgb, "RGB")
    return Image.fromarray(np.dstack([rgb, np.clip(alpha, 0, 255).astype(np.uint8)]), "RGBA")


# --------------------------------------------------------------------------- cielo

def sky(w, h, stops, sun=None, clouds=0.0, seed=0, cloud_band=(0.05, 0.55), cloud_col=(255, 255, 255),
        cloud_shadow=(176, 190, 220)):
    ys = np.linspace(0, 1, h)
    pos = [p for p, _ in stops]
    cols = np.array([c for _, c in stops], np.float32)
    rgb = np.stack([np.interp(ys, pos, cols[:, i]) for i in range(3)], axis=1)[:, None, :].repeat(w, axis=1)
    if sun:
        sx, sy, r, col, k = sun
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2) / r
        g = np.exp(-d * d)[:, :, None] * k
        rgb = rgb * (1 - g) + np.array(col, np.float32) * g
    if clouds > 0:
        n = fbm(h, w, 340, 6, seed, 0.55, sx=2.6)
        yy = np.linspace(0, 1, h)[:, None]
        band = smooth(cloud_band[0] - 0.05, cloud_band[0] + 0.1, yy) * (1 - smooth(cloud_band[1] - 0.1, cloud_band[1] + 0.05, yy))
        dens = smooth(0.5, 0.72, n) * band * clouds
        shade = np.clip(1 - 2.2 * (dens - np.roll(dens, 14, axis=0)), 0.0, 1.0)  # bordo alto illuminato
        shade = smooth(0.2, 1.0, shade)
        cc = np.array(cloud_shadow, np.float32) + (np.array(cloud_col, np.float32) - np.array(cloud_shadow, np.float32)) * shade[:, :, None]
        rgb = rgb * (1 - dens[:, :, None]) + cc * dens[:, :, None]
    return rgb


def night_sky(w, h, stops, seed=0, nebula=(120, 70, 170), nk=0.25, stars=420):
    rgb = sky(w, h, stops)
    n = fbm(h, w, 420, 6, seed + 1, 0.55, sx=1.8)
    neb = smooth(0.45, 0.85, n)[:, :, None] * nk
    rgb = rgb * (1 - neb) + np.array(nebula, np.float32) * neb
    img = to_img(rgb)
    rng = random.Random(seed)
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    d, dg = ImageDraw.Draw(img), ImageDraw.Draw(glow)
    for _ in range(stars):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.85)
        r = rng.choice([0.8, 1, 1, 1.4, 1.8, 2.4])
        c = rng.randint(180, 255)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(c, c, min(255, c + 25)))
        if r > 1.7:
            dg.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(90, 90, 130))
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    return np.clip(np.asarray(img, np.float32) + np.asarray(glow, np.float32), 0, 255)


# --------------------------------------------------------------------------- montagne

def mountain(w, h, top, rock, snow, snow_shadow, seed=0, snow_depth=260, snow_k=1.0, haze=None, detail=70.0,
             scale=150, light=LIGHT, amb=0.32, dif=0.85, rock2=None):
    """Strato di montagna illuminato. top: array len w con la y della cresta."""
    yy = np.arange(h, dtype=np.float32)[:, None]
    below = yy - top[None, :]
    alpha = np.clip(below + 0.5, 0, 1) * 255
    ts = ndimage.gaussian_filter1d(top.astype(np.float32), 6)
    n = fbm(h, w, scale, 6, seed, 0.52, ridged=True, sx=1.0, sy=2.4)
    hf = -ts[None, :] * 1.0 + np.clip(below, 0, None) * 0.25 + n * detail
    hf = ndimage.gaussian_filter(hf, 0.8)
    nn = normals(hf)
    li = lit(nn, amb, dif, light)
    tex = fbm(h, w, 40, 4, seed + 7, 0.6)
    rc = np.array(rock, np.float32)
    if rock2 is not None:
        mix = smooth(0.35, 0.75, fbm(h, w, 260, 4, seed + 9))[:, :, None]
        rc = rc * (1 - mix) + np.array(rock2, np.float32) * mix
    rgb = rc * li[:, :, None] * (0.85 + 0.3 * tex[:, :, None])
    # neve: sulle facce rivolte verso l'alto, più spessa vicino alla cresta
    up = np.clip(-nn[:, :, 1] * 1.6 + nn[:, :, 2] * 0.5, 0, 2)
    depth = snow_depth * (0.55 + 0.9 * fbm1d(w, 120, 5, seed + 3))[None, :]
    alt = 1 - np.clip(below / depth, 0, 1.5)
    sm = smooth(0.62, 0.82, up * 0.5 + alt * 0.6 + 0.4 * (fbm(h, w, 55, 4, seed + 5) - 0.5)) * snow_k
    sc = np.array(snow_shadow, np.float32) + (np.array(snow, np.float32) - np.array(snow_shadow, np.float32)) * smooth(0.25, 1.0, li)[:, :, None]
    rgb = rgb * (1 - sm[:, :, None]) + sc * sm[:, :, None]
    if haze is not None:
        hc, hk = haze
        k = hk * (0.85 + 0.25 * smooth(0, 500, below))[:, :, None]
        rgb = rgb * (1 - k) + np.array(hc, np.float32) * k
    return to_img(rgb, alpha)


def ridge_top(w, base, amp, seed, scale=380, peaks=()):
    t = base - amp * (fbm1d(w, scale, 6, seed, 0.5) - 0.5) * 2
    xs = np.arange(w, dtype=np.float32)
    for px, py, pw in peaks:  # picchi espliciti
        d = np.abs(xs - px) / pw
        t = np.minimum(t, py + (base - py) * np.clip(d, 0, 1) ** 0.8 + 25 * (fbm1d(w, 60, 4, seed + int(px)) - 0.5))
    return t


def ground(w, h, y0, col, col2=None, seed=0, scale=60, snow=False, tilt=0.0):
    """Terreno visto di taglio (sentiero, neve) con rilievo illuminato."""
    yy = np.arange(h, dtype=np.float32)[:, None]
    alpha = np.clip(yy - (y0 + tilt * np.arange(w)[None, :]) + 0.5, 0, 1) * 255
    persp = 0.35 + 0.65 * np.clip((yy - y0) / max(1, h - y0), 0, 1)  # grana più grande in primo piano
    n = fbm(h, w, scale, 6, seed, 0.55, sx=2.0)
    hf = n * 40 * persp
    li = lit(normals(hf), 0.55 if snow else 0.4, 0.55 if snow else 0.7)
    rgb = np.array(col, np.float32) * li[:, :, None]
    if col2 is not None:
        m = smooth(0.45, 0.7, fbm(h, w, 180, 4, seed + 2, sx=3))[:, :, None]
        rgb = rgb * (1 - m) + np.array(col2, np.float32) * li[:, :, None] * m
    if snow:
        sp = (np.random.default_rng(seed).random((h, w)) > 0.9985) * (li > 0.9)
        rgb[sp] = 255
    return to_img(rgb, alpha)


# --------------------------------------------------------------------------- volumi "plastilina"

def inflate(mask, color, R=40, spec=0.25, shin=20, rim=None, rim_k=0.6, tex=0.08, tex_scale=18, seed=0,
            amb=0.38, dif=0.72, light=LIGHT, color_map=None):
    """mask: array bool/float (h,w). Restituisce RGBA con volume illuminato."""
    m = mask.astype(np.float32)
    if m.max() > 1:
        m /= 255.0
    a = m > 0.5
    d = ndimage.distance_transform_edt(a)
    dd = np.minimum(d, R)
    hf = np.sqrt(np.maximum(0, R * R - (R - dd) ** 2))
    hf = ndimage.gaussian_filter(hf, 1.2)
    n = normals(hf)
    li = lit(n, amb, dif, light)
    base = np.array(color, np.float32)[None, None, :] if color_map is None else color_map
    h, w = m.shape
    t = fbm(h, w, tex_scale, 4, seed, 0.6)
    rgb = base * li[:, :, None] * (1 - tex + 2 * tex * t[:, :, None])
    hv = LIGHT + np.array([0, 0, 1], np.float32)
    hv /= np.linalg.norm(hv)
    sp = np.clip((n * hv).sum(axis=2), 0, 1) ** shin * spec * 255
    rgb += sp[:, :, None]
    if rim is not None:
        fr = (1 - n[:, :, 2]) ** 2 * rim_k
        rgb = rgb * (1 - fr[:, :, None]) + np.array(rim, np.float32) * fr[:, :, None]
    # bordo scuro di occlusione
    ao = smooth(0, 3.5, d)
    rgb *= (0.55 + 0.45 * ao)[:, :, None]
    alpha = ndimage.gaussian_filter(m, 0.7) * 255
    return to_img(rgb, alpha)


class Clay:
    """Compone parti gonfiate una sopra l'altra, con ombra di contatto tra le parti."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    def part(self, draw_fn, color, R=30, shadow=0.35, **kw):
        mk = Image.new("L", (self.w, self.h), 0)
        draw_fn(ImageDraw.Draw(mk))
        m = np.asarray(mk)
        if shadow and self.img.getbbox():
            sh = Image.fromarray(m).filter(ImageFilter.GaussianBlur(9))
            sh = np.asarray(sh, np.float32) / 255 * shadow
            sh = np.roll(np.roll(sh, 7, axis=0), 5, axis=1)
            cur = np.asarray(self.img).astype(np.float32)
            cur[:, :, :3] *= (1 - sh)[:, :, None]
            self.img = Image.fromarray(cur.astype(np.uint8), "RGBA")
        p = inflate(m, color, R, **kw)
        self.img.alpha_composite(p)
        return self

    def done(self):
        return self.img


# --------------------------------------------------------------------------- post

def bloom(frame, thr=200, k=0.55, radius=18):
    small = frame.resize((frame.width // 4, frame.height // 4), Image.BILINEAR)
    a = np.asarray(small, np.float32)
    lum = a.max(axis=2, keepdims=True)
    b = a * smooth(thr, 255, lum)
    b = Image.fromarray(b.astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius / 4)).resize(frame.size, Image.BILINEAR)
    out = np.asarray(frame, np.float32) + np.asarray(b, np.float32) * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def grade(frame, lift=(6, 4, 10), gain=(1.0, 1.0, 1.0), sat=1.0):
    a = np.asarray(frame, np.float32)
    if sat != 1.0:
        g = a.mean(axis=2, keepdims=True)
        a = g + (a - g) * sat
    a = a * np.array(gain) + np.array(lift) * (1 - a / 255)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


_GRAIN = None


def film_grain(frame, amount=5, seed=0):
    global _GRAIN
    if _GRAIN is None or _GRAIN.shape[:2] != (frame.height, frame.width):
        _GRAIN = np.random.default_rng(1).normal(0, 1, (frame.height + 64, frame.width + 64)).astype(np.float32)
    ox, oy = (seed * 37) % 64, (seed * 53) % 64
    g = _GRAIN[oy:oy + frame.height, ox:ox + frame.width, None] * amount
    return Image.fromarray(np.clip(np.asarray(frame, np.float32) + g, 0, 255).astype(np.uint8))


def light_wrap(spr, color, k=0.35, width=6):
    """Fa "entrare" la luce dell'ambiente sui bordi del personaggio."""
    a = np.asarray(spr).astype(np.float32)
    al = a[:, :, 3] / 255
    inner = ndimage.gaussian_filter(al, width)
    edge = np.clip(al - inner, 0, 1) * 2.2 * k
    a[:, :, :3] = a[:, :, :3] * (1 - edge[:, :, None]) + np.array(color, np.float32) * edge[:, :, None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
