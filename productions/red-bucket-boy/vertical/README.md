# Montaggio verticale delle clip Gemini (Veo)

Sei clip 16:9 da 10 s (`clips/clip01-06.mp4`, in ordine di racconto), montate in verticale 9:16.

| Uscita | Cosa è |
|---|---|
| `build/red-buket_ep01_verticale.mp4` | Clip 1-5, 50 s, sottotitoli |
| `build/red-buket_ep01_tiktok.mp4` | Clip 1-6, 56 s, versione TikTok: sottotitoli nella zona sicura dell'app, primi 3 s della salita tagliati, gancio "PARTE 1 · RAPITI DAGLI ALIENI", invito finale "SEGUI PER LA PARTE 2" |

| Clip | Contenuto | Battute |
|---|---|---|
| 01 | Salita in montagna | "Forza! Ancora un ultimo sforzo! Ci siamo quasi, amico mio!" |
| 02 | Vetta di notte, rapimento nel raggio | "Guarda lassù, Paco! Ma cos'è? … Ci stanno portando via!" |
| 03 | Interno dell'astronave, ologrammi | "Dove siamo finiti, Paco? … c'è persino GTA 6!" |
| 04 | Console, finestra sulla Terra | "Guarda quante luci, Paco … Guarda la Terra com'è bella!" |
| 05 | Lo "spazio" era uno schermo, città futuristica | "Ma allora era solo una televisione? … Siamo in un mondo futuristico!" |
| 06 | Arriva il robot | "Ciao a tutti, sono Lisebot (?) … vi aiuterò io a tornare a casa." |

## Uso

```bash
pip install rembg onnxruntime faster-whisper pillow numpy scipy
python3 vertical_edit.py clips/clip0*.mp4 -o build/red-buket_ep01_verticale.mp4 --words clips/words.json
```

- Senza `--words` trascrive di nuovo con faster-whisper (`--model medium`).
- `--fix "vecchio=nuovo"` corregge il testo dei sottotitoli.
- `--no-subs` monta senza sottotitoli.

Versione TikTok:

```bash
python3 vertical_edit.py clips/clip0*.mp4 -o build/red-buket_ep01_tiktok.mp4 --words clips/words.json \
  --tiktok --trim 1=3.0:10.1 --trim 5=0:9.0 --fix "Bucket=Buket" \
  --badge "PARTE 1" --hook 'RAPITI DAGLI\NALIENI' --cta 'SEGUI PER LA\NPARTE 2'
```

## Cosa fa lo script

- **Inquadratura.** Una maschera di salienza (rembg) trova il ragazzo e Paco 6 volte al secondo.
  Il taglio verticale li segue e si allarga quando sono lontani tra loro (da 405 a 830 px dei 1280
  originali). Sopra e sotto c'è lo stesso fotogramma sfocato, così non restano bande nere.
- **Sottotitoli.** Blocchi da 2-4 parole in maiuscolo, con la parola pronunciata evidenziata in giallo.
  I blocchi non finiscono mai su "il", "di", "e" e simili.
- **Audio.** Le clip sono montate in sequenza con micro-dissolvenze anti-click e normalizzate
  a -14 LUFS (lo standard di TikTok, Reels e Shorts).
