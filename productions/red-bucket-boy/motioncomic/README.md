# Motion comic: episodio 1 senza crediti AI

Versione completa di *La Reliquia* (57 s, 9:16), prodotta solo con codice open source.
Nessun generatore di immagini o video.

| File | Cosa fa |
|---|---|
| `render.py` | Pipeline completa: scontorni, 9 shot, voci, musica, montaggio con `../assemble.py` |
| `look.py` | Resa "3D materica" delle scenografie, coerente con le schede dei personaggi |
| `build/red-bucket-boy_ep01_motioncomic.mp4` | Episodio finito, con sottotitoli |

## Come funziona

- **Personaggi.** Vengono scontornati dalle schede con rembg (`characters/red-bucket-boy_sheet_v1_full.jpg`,
  `characters/paco_sheet_v2.jpg`) e animati a marionetta: spostamenti, rotazioni, salti,
  battito di ciglia disegnato. Ogni personaggio riceve il color grading della scena e un *light wrap*,
  cioè la luce dell'ambiente che entra sui bordi.
- **Scenografie** (`look.py`).
  - Montagne, roccia, neve e nuvole sono rilievi da rumore frattale, illuminati dall'alto a sinistra
    come nelle schede.
  - Gli oggetti di scena (influencer, alieni, astronave, archi, piedistallo, rocce, telefono)
    sono sagome "gonfiate" in volumi di plastilina, con luce, riflesso speculare, rim light e grana del materiale.
  - In post: bloom, profondità di campo, vignettatura e grana.
- **Voci.** Piper TTS in italiano (`it_IT-riccardo-x_low`), con un filtro diverso per ogni personaggio.
- **Musica.** Beat lo-fi a 88 BPM sintetizzato con numpy, tagliato a 48 s come da copione.

## Uso

```bash
pip install rembg onnxruntime piper-tts scipy pillow numpy
python3 motioncomic/render.py                  # tutto (circa 10-12 minuti su CPU)
python3 motioncomic/render.py --only 04 07     # rifà solo alcuni shot, poi rimonta
python3 motioncomic/render.py --bandana red    # fazzoletto di Paco rosso come nella scheda
```

Scontorni, voci scaricate e file intermedi stanno in `cutouts/`, `voices/` e `build/`,
esclusi da git e rigenerati in automatico.

## Scelte da confermare

- **Fazzoletto di Paco:** è ricolorato senape (`--bandana mustard`, il default). Il motivo è
  lasciare il rosso solo al cappello, che nella storia è "la Reliquia".
- **Anatomia di Paco:** è tolta dalla vista frontale, per una distribuzione social o per famiglie.
- **Ragazzo senza cappello (shot 9b):** i capelli sono ridisegnati sopra lo scontorno. È un ripiego:
  una vista senza cappello nella scheda darebbe un risultato migliore.

## Limiti

È un motion comic, non animazione. I personaggi non muovono bocca, braccia e gambe. Per
farlo servono clip generate (vedi `../PROMPTS.md`, `../KLING.md`, `../GEMINI.md`) oppure un rig
2D/3D vero. Il montaggio accetta comunque entrambe le strade: `assemble.py --clips-dir` legge
qualunque cartella di clip `shot<ID>.mp4`.
