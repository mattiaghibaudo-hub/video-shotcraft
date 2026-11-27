# Red Bucket Boy — La Reliquia

Short animato verticale 9:16, 57 s, 9 shot (lo shot 9 è diviso in 09a + 09b).

**Stato:** pacchetto di produzione pronto, nessun clip generato. L'account
Higgsfield ha 0 crediti.

| File | Cosa contiene |
|---|---|
| `shots.json` | Unica fonte di verità: stile fisso, descrizioni fisse dei personaggi, timeline, prompt di keyframe e video per ogni shot, battute con tempi, prompt della musica, correzioni alle schede personaggio |
| `characters/*_sheet_v1.jpg` | Schede personaggio attuali (v1) |
| `assemble.py` | Montaggio completo con ffmpeg: clip, title card, musica, voce fuori campo, sottotitoli opzionali |
| `build/animatic.mp4` | Animatic a cartelli con tempi e battute definitivi |

## Pipeline

1. **Correggi le schede** (`sheet_fixes` in `shots.json`, ~6 immagini, ~15–30 crediti):
   ragazzo ridisegnato a colori piatti con espressione deadpan, versione senza
   cappello, espressioni, pose di Paco, confronto di scala. Le v1 hanno questi problemi:
   - ragazzo disegnato con texture pittorica, Paco a colori piatti: sembrano due serie diverse
   - viste FRONT e 3/4 con sorriso a denti in vista invece di deadpan
   - lacci rosa nella vista BACK invece che verde neon
   - nessun riferimento senza cappello (serve allo shot 9)
   - Paco senza vista 3/4 e senza pose d'azione (servono agli shot 5 e 7)
2. **Keyframe**: un'immagine 9:16 per shot da `keyframe_prompt`, con `style_lock`,
   le descrizioni fisse dei personaggi e i `refs` come riferimento.
   Salva come `keyframes/shot<ID>.png`. Rilanciando `assemble.py` l'animatic usa
   già i keyframe, con un lento zoom.
3. **Video**: per ogni shot `video_prompt` + keyframe come `start_image` + `refs`,
   durata `gen_duration`, audio generato **disattivato**. Salva come `clips/shot<ID>.mp4`.
   Modello consigliato: Seedance 2.5, `omni_reference`, 720p.
4. **Audio**: voce fuori campo in `audio/vo/<id>.wav|mp3` (testo e direzione in `vo`),
   musica in `audio/music.mp3` (prompt in `music`). La musica si taglia di netto
   a 48 s: dallo shot 9 silenzio totale, restano solo le voci.
5. **Montaggio**: `python3 assemble.py` → `build/red-bucket-boy.mp4`
   (`--subs` per bruciare i sottotitoli).

Ogni shot mancante viene sostituito dal suo cartello di animatic, quindi si può
montare in qualunque momento.

## Costo stimato (Higgsfield, preventivi del 27/11/2026)

| Voce | Crediti |
|---|---|
| Correzioni alle schede + 10 keyframe, compresi i rifacimenti | ~50 |
| 57 s di video con Seedance 2.5 a 720p (7 cr/s), una passata | ~400 |
| Con circa il 50% di rifacimenti | ~580 |
| In alternativa, Seedance 2.5 Flash (5 cr/s) | ~280–420 |

Totale circa 450–650 crediti, cioè 22–33 $ a 20 crediti per dollaro.

## Problema aperto nel copione

La battuta d'apertura ("Tecnicamente è colpa del selfie") non viene ripresa nel
finale: il raggio cerca il cappello e il selfie si pubblica solo dopo il rapimento.
Gli shot 04 e 06 hanno un campo `optional_fix`: l'ultimo filtro del selfie è
un'aura verde acido che fa brillare il cappello come un faro, e la nave arriva
verso quel bagliore. Per usarla, aggiungi il testo di `optional_fix` al
`video_prompt` (e al keyframe) di quei due shot.

## Rischi noti

- **Shot 09a:** la rivelazione con centinaia di alieni è lo shot che fallisce più
  spesso. Metti in conto 2–3 tentativi.
- **Labiale dell'alieno:** "La Reliquia. Finalmente." parte durante la rivelazione,
  quando nessun alieno è in primo piano, così il lip-sync non serve.
- **Battuta finale:** dura ~2,3 s e finisce a ~56,5 s, poi il taglio a nero arriva
  alla fine del file, a 57 s.
