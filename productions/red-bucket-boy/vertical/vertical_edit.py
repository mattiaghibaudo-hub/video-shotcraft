#!/usr/bin/env python3
"""Monta clip orizzontali (16:9) in un video verticale 9:16 con sottotitoli parola per parola.

Per ogni clip:
  1. trova i personaggi con una maschera di salienza (rembg, 6 fps) e calcola un'inquadratura
     che li segue (centro e larghezza levigati nel tempo);
  2. compone il 9:16: l'inquadratura a tutta larghezza, sopra e sotto lo stesso fotogramma
     sfocato e scurito (niente bande nere);
  3. trascrive i dialoghi con faster-whisper (tempi per parola) e brucia sottotitoli
     brevi stile Shorts, con la parola pronunciata evidenziata.
Audio: le clip in sequenza con micro-dissolvenze anti-click, normalizzato a -14 LUFS.

Uso:
  pip install rembg onnxruntime faster-whisper pillow numpy scipy
  python3 vertical_edit.py clip1.mp4 clip2.mp4 ... -o episodio.mp4
  python3 vertical_edit.py clips/*.mp4 -o ep.mp4 --fix "come è bella=com'è bella"   # correzioni al testo

Versione TikTok (sottotitoli nella zona sicura dell'app, tagli, gancio e invito finale):
  python3 vertical_edit.py clips/*.mp4 -o tiktok.mp4 --tiktok --trim 1=3.0:10 \
      --badge "PARTE 1" --hook "RAPITI DAGLI ALIENI" --cta "SEGUI PER LA PARTE 2"
"""
import argparse
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

W, H, FPS = 1080, 1920, 24
FONT_DIR = "/usr/share/fonts/opentype/inter"
FONT = "Inter Display"
FG_CENTER = 0.44  # l'inquadratura sta un po' sopra il centro: sotto c'è spazio per i sottotitoli


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True).stdout
    j = json.loads(out)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


# --------------------------------------------------------------------------- inquadratura

def track(path, sw, sh, session):
    from rembg import remove
    tw, th = 640, int(640 * sh / sw)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps=6,scale={tw}:{th}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, th, tw, 3)
    k = sw / tw
    pts = []
    for f in frames:
        a = np.asarray(remove(Image.fromarray(f), session=session, only_mask=True), np.float32) / 255
        cols = a.sum(axis=0)
        if cols.sum() < 50:
            pts.append(None)
            continue
        xs = np.where(cols > cols.max() * 0.08)[0]
        cx = float((cols * np.arange(tw)).sum() / cols.sum())
        pts.append((cx * k, xs.min() * k, xs.max() * k))
    return pts


def crop_path(pts, n_frames, sw, sh):
    """Centro e larghezza del ritaglio per ogni fotogramma a 24 fps."""
    t6 = np.arange(len(pts)) / 6.0
    good = [i for i, p in enumerate(pts) if p is not None]
    if not good:
        return np.full(n_frames, sw / 2), np.full(n_frames, sh * 9 / 16)
    cx = np.interp(t6, t6[good], [pts[i][0] for i in good])
    lo = np.interp(t6, t6[good], [pts[i][1] for i in good])
    hi = np.interp(t6, t6[good], [pts[i][2] for i in good])
    mid = (lo + hi) / 2
    cen = 0.6 * mid + 0.4 * cx  # i due personaggi dentro, peso al centro di massa
    min_w, max_w = sh * 9 / 16, min(sw, sh * 1.15)
    wid = np.clip((hi - lo) * 1.22 + 60, min_w, max_w)
    t24 = np.arange(n_frames) / FPS
    cen = ndimage.gaussian_filter1d(np.interp(t24, t6, cen), FPS * 0.5, mode="nearest")
    wid = ndimage.gaussian_filter1d(np.interp(t24, t6, wid), FPS * 0.7, mode="nearest")
    cen = np.clip(cen, wid / 2, sw - wid / 2)
    return cen, wid


def compose(frame, cx, cw, sw, sh):
    src = Image.fromarray(frame)
    # sfondo: stesso fotogramma, 9:16 attorno al soggetto, molto sfocato e scuro
    small = src.resize((sw // 4, sh // 4), Image.BILINEAR)
    bw = small.height * 9 / 16
    bx = min(max(0, cx / 4 - bw / 2), small.width - bw)
    bg = small.crop((int(bx), 0, int(bx + bw), small.height)).filter(ImageFilter.GaussianBlur(6))
    bg = bg.resize((W, H), Image.BILINEAR)
    bg = Image.fromarray((np.asarray(bg, np.float32) * 0.45).astype(np.uint8))
    # primo piano: il ritaglio a tutta larghezza
    x0 = cx - cw / 2
    fh = int(round(sh * W / cw))
    fg = src.resize((W, min(H, fh)), Image.LANCZOS, box=(x0, 0, x0 + cw, sh) if fh <= H else
                    (x0, (sh - cw * H / W) / 2, x0 + cw, (sh + cw * H / W) / 2))
    y = int(H * FG_CENTER - fg.height / 2) if fg.height < H else 0
    y = max(0, min(H - fg.height, y))
    bg.paste(fg, (0, y))
    if fg.height < H:  # sfuma i bordi dell'inquadratura nello sfondo
        a = np.asarray(bg, np.float32)
        for edge, sgn in ((y, 1), (y + fg.height, -1)):
            for k in range(18):
                yy = edge + sgn * k
                if 0 <= yy < H:
                    a[yy] *= 0.55 + 0.45 * k / 18
        bg = Image.fromarray(a.astype(np.uint8))
    return bg


# --------------------------------------------------------------------------- sottotitoli

def transcribe(wavs, model_size):
    from faster_whisper import WhisperModel
    m = WhisperModel(model_size, device="cpu", compute_type="int8")
    out = []
    for p in wavs:
        w = wave.open(str(p))
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        segs, _ = m.transcribe(a, language="it", word_timestamps=True, beam_size=5)
        out.append([(x.start, x.end, x.word.strip()) for s in segs for x in s.words])
    return out


# parole che non devono chiudere una riga ("il", "di", "e"...): passano alla riga dopo
WEAK = {"il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "a", "da", "in", "con", "su", "per", "e", "o",
        "ma", "che", "come", "è", "del", "della", "al", "nel", "non", "ci", "mi", "ti", "si"}


def chunks(words, max_words=4, max_chars=22):
    cur = []
    for w in words:
        cur.append(w)
        text = " ".join(x[2] for x in cur)
        if w[2][-1:] in ".!?,":
            yield cur
            cur = []
        elif len(cur) >= max_words or len(text) >= max_chars:
            carry = []
            while len(cur) > 1 and cur[-1][2].lower() in WEAK:
                carry.insert(0, cur.pop())
            yield cur
            cur = carry
    if cur:
        yield cur


def merge_elisions(words):
    """Whisper spezza "c'è" in "c" + "'è": li riunisce."""
    out = []
    for s, e, w in words:
        if out and w[:1] in "'’":
            ps, _, pw = out[-1]
            out[-1] = (ps, e, pw + w)
        else:
            out.append((s, e, w))
    return out


def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def write_ass(all_words, offsets, path, fixes, tiktok=False, hook=None, badge=None, cta=None, total=0.0):
    # TikTok: la parte bassa (descrizione, musica) e la colonna destra (like, commenti) sono coperte dall'app
    mv, ml, mr = (int(H * 0.31), 90, 170) if tiktok else (int(H * 0.2), 70, 70)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,7,3,2,{ml},{mr},{mv},1
Style: Hook,{FONT},80,&H00FFFFFF,&H00FFFFFF,&H001E26D7,&H001E26D7,1,0,0,0,100,100,0,0,3,18,0,8,90,170,225,1
Style: Badge,{FONT},50,&H00111111,&H00111111,&H002EE8FF,&H002EE8FF,1,0,0,0,100,100,2,0,3,12,0,8,90,170,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if badge:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(2.8)},Badge,,0,0,0,,{{\\fad(0,250)}}{badge}")
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(2.8)},Hook,,0,0,0,,{{\\fscx115\\fscy115\\t(0,160,\\fscx100\\fscy100)\\fad(0,250)}}{hook}")
    if cta:
        lines.append(f"Dialogue: 1,{ass_time(total - 2.4)},{ass_time(total)},Hook,,0,0,0,,{{\\fad(200,0)}}{cta}")
    for words, off in zip(all_words, offsets):
        words = merge_elisions([(s, e, w.strip()) for s, e, w in words if w.strip()])
        groups = list(chunks(words))
        for gi, ch in enumerate(groups):
            nxt = groups[gi + 1][0][0] if gi + 1 < len(groups) else 1e9  # mai sovrapposti al blocco dopo
            toks = [w[2] for w in ch]
            text = " ".join(toks)
            for a, b in fixes:
                text = text.replace(a, b)
            toks = text.split(" ")
            if len(toks) != len(ch):  # una correzione ha cambiato il numero di parole: niente evidenziazione
                lines.append(f"Dialogue: 0,{ass_time(off + ch[0][0])},{ass_time(off + min(ch[-1][1] + 0.25, nxt))},Cap,,0,0,0,,{text.upper()}")
                continue
            for k, (s, e, _) in enumerate(ch):
                end = ch[k + 1][0] if k + 1 < len(ch) else min(e + 0.25, nxt)
                styled = " ".join(("{\\c&H2EE8FF&}" + tk.upper() + "{\\c&HFFFFFF&}") if j == k else tk.upper()
                                  for j, tk in enumerate(toks))
                pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
                lines.append(f"Dialogue: 0,{ass_time(off + s)},{ass_time(off + end)},Cap,,0,0,0,,{pop}{styled}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--model", default="medium", help="modello faster-whisper (small/medium/large-v3)")
    ap.add_argument("--fix", action="append", default=[], help='correzione al testo, es. "come è=com\'è"')
    ap.add_argument("--words", help="json di parole già trascritte (salta whisper)")
    ap.add_argument("--no-subs", action="store_true")
    ap.add_argument("--tiktok", action="store_true", help="sottotitoli e testi nella zona sicura di TikTok")
    ap.add_argument("--trim", action="append", default=[], help="taglio di una clip: N=inizio:fine in secondi (N da 1)")
    ap.add_argument("--hook", help="titolo a schermo nei primi 2,8 s")
    ap.add_argument("--badge", help="etichetta sopra il titolo (es. PARTE 1)")
    ap.add_argument("--cta", help="invito negli ultimi 2,4 s (es. SEGUI PER LA PARTE 2)")
    args = ap.parse_args()
    fixes = [tuple(f.split("=", 1)) for f in args.fix]

    tmp = Path(tempfile.mkdtemp(prefix="vert_"))
    info = [probe(c) for c in args.clips]
    cuts = [(0.0, d) for _, _, d in info]
    for t in args.trim:
        n, rng = t.split("=")
        a, b = rng.split(":")
        cuts[int(n) - 1] = (float(a or 0), min(float(b or 1e9), info[int(n) - 1][2]))
    durs = [b - a for a, b in cuts]
    offsets = list(np.cumsum([0] + durs[:-1]))
    total = sum(durs)

    print("audio ...")
    wavs = []
    for i, c in enumerate(args.clips):
        p = tmp / f"a{i}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", c, "-ac", "1", "-ar", "16000", str(p)], check=True)
        wavs.append(p)
    parts = []
    for i, c in enumerate(args.clips):
        d = durs[i]
        p = tmp / f"m{i}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(cuts[i][0]), "-t", str(d), "-i", c,
                        "-af", f"afade=t=in:d=0.03,afade=t=out:st={d - 0.04}:d=0.04",
                        "-ar", "48000", "-ac", "2", str(p)], check=True)
        parts.append(p)
    concat = tmp / "a.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in parts))
    audio = tmp / "audio.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", str(audio)], check=True)

    subs = None
    if not args.no_subs:
        print("trascrizione ...")
        words = json.loads(Path(args.words).read_text()) if args.words else transcribe(wavs, args.model)
        if isinstance(words, dict):
            words = [words[k] for k in sorted(words, key=int)]
        # solo le parole dentro il taglio, con i tempi spostati all'inizio del taglio
        words = [[(s - a, e - a, w) for s, e, w in ws if s >= a - 0.05 and e <= b + 0.15] for ws, (a, b) in zip(words, cuts)]
        subs = tmp / "subs.ass"
        n = write_ass(words, offsets, subs, fixes, args.tiktok, args.hook, args.badge, args.cta, total)
        print(f"  {n} eventi di sottotitolo")

    print("inquadrature ...")
    from rembg import new_session
    sess = new_session("isnet-general-use")
    vf = f"ass={subs}:fontsdir={FONT_DIR}" if subs else "null"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-i", str(audio), "-vf", vf, "-map", "0:v", "-map", "1:a",
                            "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "8M", "-bufsize", "16M",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}",
                            "-movflags", "+faststart", args.out], stdin=subprocess.PIPE)
    for i, c in enumerate(args.clips):
        sw, sh, d = info[i]
        pts = track(c, sw, sh, sess)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", c, "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        frames = np.frombuffer(raw, np.uint8).reshape(-1, sh, sw, 3)
        cen, wid = crop_path(pts, len(frames), sw, sh)
        k0, k1 = int(round(cuts[i][0] * FPS)), min(len(frames), int(round(cuts[i][1] * FPS)))
        for k in range(k0, k1):
            enc.stdin.write(compose(frames[k], cen[k], wid[k], sw, sh).tobytes())
        print(f"  clip {i + 1}: {len(frames)} frame, larghezza ritaglio {wid.min():.0f}-{wid.max():.0f}px")
    enc.stdin.close()
    enc.wait()
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
