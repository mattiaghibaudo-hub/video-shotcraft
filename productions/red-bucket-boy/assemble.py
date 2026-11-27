#!/usr/bin/env python3
"""Monta "Red Bucket Boy — La Reliquia" (9:16, 57 s) da shots.json.

Per ogni shot usa, in ordine di priorità:
  1. clips/shot<ID>.mp4        clip video generato (tagliato alla durata di timeline)
  2. keyframes/shot<ID>.png    fotogramma chiave con lento zoom (animatic avanzato)
  3. un cartello di animatic   numero shot, timecode, descrizione, battuta
Lo shot 02 (title card) è sempre generato qui, in locale.

Audio: audio/music.mp3 fino a music.cut_at (poi silenzio totale) +
audio/vo/<id>.wav|mp3 posizionati a vo[].at. I file mancanti vengono saltati.

Uso:
  python3 assemble.py                 # build/red-bucket-boy.mp4
  python3 assemble.py --subs          # sottotitoli bruciati con le battute
  python3 assemble.py --font /path/Bold.ttf
Richiede solo ffmpeg e Python 3.8+.
"""
import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
TMP = BUILD / "tmp"

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

CARD_COLORS = ["#2E1F47", "#0F5257", "#3B2A5C", "#14454A", "#4A2350", "#1D3F4F", "#2A2140"]


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.stderr.write(" ".join(map(str, cmd)) + "\n" + r.stderr[-3000:])
        sys.exit(r.returncode)


def find_font(override):
    if override:
        return override
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    sys.exit("Nessun font trovato: passa --font /percorso/font-bold.ttf")


def esc(path):
    # percorso dentro un filtergraph ffmpeg
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def write_text(name, text):
    p = TMP / name
    p.write_text(text, encoding="utf-8")
    return p


def video_args(fps):
    return ["-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18", "-an"]


def seg_titlecard(shot, dur, cfg, font, out):
    W, H, fps = cfg["width"], cfg["height"], cfg["fps"]
    t = write_text(f"title_{shot['id']}.txt", shot["text"])
    # piccolo "pop" iniziale: il testo scala da 0.92 a 1.0 nei primi 6 frame
    vf = (
        f"drawtext=fontfile='{esc(font)}':textfile='{esc(t)}':fontcolor={shot['fg']}:"
        f"fontsize='110*min(1,0.92+0.08*n/6)':x=(w-text_w)/2:y=(h-text_h)/2"
    )
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={shot['bg']}:s={W}x{H}:r={fps}:d={dur}",
         "-vf", vf, "-t", str(dur), *video_args(fps), str(out)])


def seg_clip(src, dur, cfg, out):
    W, H, fps = cfg["width"], cfg["height"], cfg["fps"]
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setsar=1"
    run(["ffmpeg", "-y", "-i", str(src), "-t", str(dur), "-vf", vf, *video_args(fps), str(out)])


def seg_keyframe(src, dur, cfg, out):
    W, H, fps = cfg["width"], cfg["height"], cfg["fps"]
    frames = int(round(dur * fps))
    vf = (
        f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
        f"zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps},setsar=1"
    )
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-vf", vf, "-frames:v", str(frames), *video_args(fps), str(out)])


def seg_card(shot, idx, dur, cfg, font, vo_lines, out):
    W, H, fps = cfg["width"], cfg["height"], cfg["fps"]
    color = CARD_COLORS[idx % len(CARD_COLORS)]
    head = f"SHOT {shot['id']}   {shot['start']:.1f}s - {shot['end']:.1f}s"
    desc = textwrap.fill(shot.get("keyframe_prompt", ""), 44)
    lines = "\n".join(textwrap.fill(f"{v['speaker']}: \u201c{v['text']}\u201d", 30) for v in vo_lines)
    th = write_text(f"card_{shot['id']}_h.txt", head)
    td = write_text(f"card_{shot['id']}_d.txt", desc)
    filters = [
        f"drawtext=fontfile='{esc(font)}':textfile='{esc(th)}':fontcolor=#9DFF3A:fontsize=56:x=80:y=140",
        f"drawtext=fontfile='{esc(font)}':textfile='{esc(td)}':fontcolor=#F6F1E7@0.85:fontsize=38:line_spacing=14:x=80:y=280",
        # barra di avanzamento dello shot
        f"drawbox=x=80:y={H-120}:w='({W-160})*t/{dur}':h=10:color=#9DFF3A:t=fill",
    ]
    if lines:
        tl = write_text(f"card_{shot['id']}_l.txt", lines)
        filters.append(
            f"drawtext=fontfile='{esc(font)}':textfile='{esc(tl)}':fontcolor=#FFFFFF:fontsize=50:"
            f"line_spacing=16:x=80:y={H-560}:box=1:boxcolor=#000000@0.45:boxborderw=24"
        )
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={fps}:d={dur}",
         "-vf", ",".join(filters), "-t", str(dur), *video_args(fps), str(out)])


def find_audio(base):
    for ext in (".wav", ".mp3", ".m4a", ".aac"):
        p = base.with_suffix(ext)
        if p.exists():
            return p
    return None


def build_audio(spec, total, out):
    inputs, chains, labels = [], [], []
    music = ROOT / spec["music"]["file"]
    if music.exists():
        cut = spec["music"]["cut_at"]
        inputs += ["-i", str(music)]
        n = len(inputs) // 2 - 1
        # taglio netto (5 ms anti-click) al cut_at: dallo shot 9 silenzio totale
        chains.append(f"[{n}:a]atrim=0:{cut},asetpts=N/SR/TB,volume={spec['music']['volume']},afade=t=out:st={cut-0.005}:d=0.005[m]")
        labels.append("[m]")
    for v in spec["vo"]:
        f = find_audio(ROOT / "audio" / "vo" / v["id"])
        if not f:
            continue
        inputs += ["-i", str(f)]
        n = len(inputs) // 2 - 1
        ms = int(v["at"] * 1000)
        chains.append(f"[{n}:a]aresample=48000,adelay={ms}|{ms}[v{n}]")
        labels.append(f"[v{n}]")
    if not labels:
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(total), "-c:a", "aac", str(out)])
        return False
    mix = ";".join(chains) + ";" + "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,apad,atrim=0:{total}[a]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", mix, "-map", "[a]", "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(out)])
    return True


def burn_subs(spec, src, font, out):
    filters = []
    for i, v in enumerate(spec["vo"]):
        t = write_text(f"sub_{i}.txt", textwrap.fill(v["text"], 26))
        # durata stimata, mai oltre la fine dello shot che la contiene
        shot_end = next(s["end"] for s in spec["shots"] if s["start"] <= v["at"] < s["end"])
        end = min(v["at"] + 0.075 * len(v["text"]) + 0.5, shot_end)
        filters.append(
            f"drawtext=fontfile='{esc(font)}':textfile='{esc(t)}':fontcolor=#FFFFFF:fontsize=58:"
            f"borderw=5:bordercolor=#000000:x=(w-text_w)/2:y=h*0.72:enable='between(t,{v['at']},{end:.2f})'"
        )
    run(["ffmpeg", "-y", "-i", str(src), "-vf", ",".join(filters), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "18", "-c:a", "copy", str(out)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font")
    ap.add_argument("--subs", action="store_true", help="brucia le battute come sottotitoli")
    ap.add_argument("--out", default=str(BUILD / "red-bucket-boy.mp4"))
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg non trovato nel PATH")
    spec = json.loads((ROOT / "shots.json").read_text(encoding="utf-8"))
    cfg = spec["format"]
    font = find_font(args.font)
    TMP.mkdir(parents=True, exist_ok=True)

    segs, report = [], []
    for idx, shot in enumerate(spec["shots"]):
        dur = round(shot["end"] - shot["start"], 3)
        out = TMP / f"seg_{shot['id']}.mp4"
        clip = ROOT / "clips" / f"shot{shot['id']}.mp4"
        key = ROOT / "keyframes" / f"shot{shot['id']}.png"
        if shot.get("local") == "titlecard":
            seg_titlecard(shot, dur, cfg, font, out); src = "title card (locale)"
        elif clip.exists():
            seg_clip(clip, dur, cfg, out); src = f"clip {clip.name}"
        elif key.exists():
            seg_keyframe(key, dur, cfg, out); src = f"keyframe {key.name}"
        else:
            vo_lines = [] if args.subs else [v for v in spec["vo"] if shot["start"] <= v["at"] < shot["end"]]
            seg_card(shot, idx, dur, cfg, font, vo_lines, out); src = "cartello animatic"
        segs.append(out)
        report.append(f"  shot {shot['id']:>3}  {shot['start']:5.1f}-{shot['end']:5.1f}s  {src}")

    concat = TMP / "concat.txt"
    concat.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    video = TMP / "video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video)])

    total = spec["total_seconds"]
    audio = TMP / "audio.m4a"
    has_audio = build_audio(spec, total, audio)

    final = Path(args.out)
    final.parent.mkdir(parents=True, exist_ok=True)
    muxed = TMP / "muxed.mp4" if args.subs else final
    run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "copy", "-t", str(total), "-movflags", "+faststart", str(muxed)])
    if args.subs:
        burn_subs(spec, muxed, font, final)

    print("\n".join(report))
    print(f"  audio: {'mix musica/VO' if has_audio else 'traccia muta (nessun file audio trovato)'}")
    print(f"-> {final}")


if __name__ == "__main__":
    main()
