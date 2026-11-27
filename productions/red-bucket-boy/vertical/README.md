# Montaggio verticale delle clip Gemini (Veo)

Cinque clip 16:9 da 10 s (`clips/clip01-05.mp4`, in ordine di racconto), montate in un
video 9:16 da 50 s con sottotitoli in italiano.

| Clip | Contenuto | Battute |
|---|---|---|
| 01 | Salita in montagna | "Forza! Ancora un ultimo sforzo! Ci siamo quasi, amico mio!" |
| 02 | Vetta di notte, rapimento nel raggio | "Guarda lassù, Paco! Ma cos'è? … Ci stanno portando via!" |
| 03 | Interno dell'astronave, ologrammi | "Dove siamo finiti, Paco? … c'è persino GTA 6!" |
| 04 | Console, finestra sulla Terra | "Guarda quante luci, Paco … Guarda la Terra com'è bella!" |
| 05 | Lo "spazio" era uno schermo, città futuristica | "Ma allora era solo una televisione? … Siamo in un mondo futuristico!" |

## Uso

```bash
pip install rembg onnxruntime faster-whisper pillow numpy scipy
python3 vertical_edit.py clips/clip0*.mp4 -o build/red-buket_ep01_verticale.mp4 --words clips/words.json
```

- Senza `--words` trascrive di nuovo con faster-whisper (`--model medium`).
- `--fix "vecchio=nuovo"` corregge il testo dei sottotitoli.
- `--no-subs` monta senza sottotitoli.

## Cosa fa lo script

- **Inquadratura.** Una maschera di salienza (rembg) trova il ragazzo e Paco 6 volte al secondo.
  Il taglio verticale li segue e si allarga quando sono lontani tra loro (da 405 a 830 px dei 1280
  originali). Sopra e sotto c'è lo stesso fotogramma sfocato, così non restano bande nere.
- **Sottotitoli.** Blocchi da 2-4 parole in maiuscolo, con la parola pronunciata evidenziata in giallo.
  I blocchi non finiscono mai su "il", "di", "e" e simili.
- **Audio.** Le clip sono montate in sequenza con micro-dissolvenze anti-click e normalizzate
  a -14 LUFS (lo standard di TikTok, Reels e Shorts).
