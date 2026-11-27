# Red Bucket Boy su Gemini (Nano Banana + Veo 3.1)

Si lavora in due passaggi, perché Veo da solo non tiene coerenti i personaggi:

1. **Immagini (Nano Banana, nella chat di Gemini):** per ogni shot crei un fotogramma
   chiave 9:16, allegando le due schede personaggio.
2. **Video (Veo 3.1, con "Crea video"):** animi ogni fotogramma chiave.
   - Usa il fotogramma come immagine iniziale. Oppure, in modalità "ingredienti",
     usa fotogramma + scheda ragazzo + scheda Paco: al massimo 3 immagini.
   - Formato **9:16**.
   - I video con immagini di riferimento durano **8 s fissi**: va bene, il
     montaggio taglia ogni clip alla sua durata.

Veo genera anche l'audio. Ogni prompt chiede solo rumori d'ambiente, niente
dialoghi e niente musica: voci e musica si aggiungono in montaggio, con i tempi
esatti.

---

## Passo 0 — Correggi le schede (consigliato, 3 immagini)

Allega la scheda indicata e incolla il prompt.

**0A · Ragazzo in stile piatto** (allega scheda ragazzo + scheda Paco)
```
Redraw the character turnaround from image 1 (FRONT, 3/4 FRONT, SIDE, BACK) in exactly the rendering style of image 2: flat cel colors, thin uniform black outlines, minimal shading, no texture, no grain. Keep every costume detail identical. In every view: deadpan dry half-smile with mouth closed, heavy droopy eyelids. Neon green shoelaces in every view, including BACK. Off-white background, view labels on top.
```

**0B · Ragazzo senza cappello** (allega la scheda 0A)
```
Same character as the attached sheet, but WITHOUT the hat: head and shoulders, FRONT and 3/4 views side by side. Messy dark hair flattened and dented in a ring where the bucket hat used to sit, a few strands sticking up. Confused expression: eyebrows raised, tiny pupils, mouth slightly open. Same flat cel style, off-white background.
```

**0C · Pose di Paco** (allega scheda Paco)
```
Pose sheet of this exact dog, three poses side by side: 3/4 front standing happy with tongue out; sitting and barking urgently straight up at the sky with mouth wide open; mid-air leap. White chest patch and small red bandana visible in every pose. No genitals. Same flat cel style, thin black outlines, off-white background, no text.
```

Da qui in avanti, "scheda ragazzo" significa la 0A, se l'hai fatta.

---

## Passo 1 — Fotogrammi chiave (Nano Banana)

Allega **scheda ragazzo** (immagine 1) e **scheda Paco** (immagine 2), poi incolla
**prima** il blocco fisso e **sotto** la scena dello shot.

**Blocco fisso**
```
Create one vertical 9:16 frame. Use the attached sheets as exact character references: image 1 is the young man, image 2 is the black Labrador Paco. Same 2D adult animated sci-fi comedy cartoon style: thin uniform black outlines, flat cel colors, minimal shading, no texture, wobbly organic linework, large round eyes with tiny pupils, droopy eyelids. Keep the outfits identical (red frayed bucket hat, teal jacket with purple chevron band, off-white tee, sand cargo pants, brown boots with neon green laces, grey crossbody bag; dog with white chest patch and small red bandana). The man's expression is deadpan, mouth closed. Palette red, teal, purple, sand, off-white; alien elements acid green. No text.
```

| Shot | Scena (sotto il blocco fisso) |
|---|---|
| 01 | `Scene: night, low angle looking up. The man floats inside a narrow acid-green tractor beam high above a snowy summit, gripping his hat brim with both hands, legs dangling, bored. Paco floats beside him, happy, tongue out. Starry deep-purple sky.` |
| 03 | `Scene: daytime rocky mountain trail, snowy peaks. Foreground right, seen from behind: an influencer in flip-flops and shorts holding a selfie stick with a ring light (face not visible). Midground left: the man and Paco walking on the trail, unimpressed.` |
| 04 | `Scene: mountain summit, clear sky. Over-the-shoulder from behind the man holding his phone up for a selfie; the phone screen shows his face and red hat with a sparkly beauty filter. Paco sits beside him. Wind lifts the hat brim.` |
| 05 | `Scene: close-up of Paco, low angle, barking urgently up at the sky, mouth wide open. Background blurred: the man staring down at his phone, face lit by the screen.` |
| 06 | `Scene: wide shot of the snowy summit. A glowing acid-green rift tears the sky open; a clunky, lumpy, asymmetrical alien spaceship with mismatched lights emerges. Far below, three tiny hikers raise their phones to film it. (Do not draw the man or the dog.)` |
| 07 | `Scene: low angle. A narrow acid-green tractor beam hits the man's red bucket hat; he grips it with both hands, heels just leaving the ground. Paco crouches below, about to leap at his ankle.` |
| 08 | `Scene: static close-up from above of a smartphone lying face up on a grey rock; the glowing screen shows a selfie of the man and Paco. Green spaceship lights reflected on the glass. (Draw only the phone and the rock.)` |
| 09a | `Scene: dark temple-like spaceship interior, organic arches. Center: the red bucket hat glowing on a stone pedestal under a spotlight; rows of strange diverse aliens kneel and bow toward it. Far background, small: the man WITHOUT a hat, hair dented, confused, next to Paco.` |
| 09b | `Scene: medium shot in the dark green-lit alien temple. The man WITHOUT a hat (messy dark hair dented in a ring where the hat was) stands next to Paco, confused deadpan. Blurred rows of bowing aliens in the foreground.` |

Per 09a e 09b allega anche la scheda 0B (testa senza cappello), se l'hai fatta.

---

## Passo 2 — Video (Veo 3.1)

Allega il fotogramma chiave dello shot. Se usi la modalità "ingredienti", aggiungi
anche le due schede. Formato 9:16.

**SHOT 01** — tieni 3 s
```
2D flat cel cartoon, thin black outlines, deadpan comedy. Static low-angle camera. The young man and the black Labrador drift slowly upward inside the shimmering acid-green tractor beam above the snowy summit. He keeps gripping his hat with both hands, bored, and blinks once slowly. The dog wags its tail and paddles its legs happily. Audio: low electronic hum of the beam, soft wind. No dialogue, no music.
```

**SHOT 03** — tieni 8 s
```
2D flat cel cartoon, thin black outlines, deadpan comedy. Tracking shot moving left to right along the mountain trail. In the foreground the influencer, back to camera, gestures enthusiastically at his ring-light phone. Behind him the young man and the dog hike past at a steady pace, glance at him with flat unimpressed faces, then look ahead. Audio: wind, footsteps on gravel, distant muffled vlogger chatter. No clear dialogue, no music.
```

**SHOT 04** — tieni 8 s
```
2D flat cel cartoon, thin black outlines, deadpan comedy. Nearly static over-the-shoulder shot. On the phone screen colorful beauty filters switch rapidly every half second: rainbow sparkles, puppy ears, glitter, sepia. The frayed hat brim flutters in the wind. The dog sits panting, then glances up at the sky. Audio: strong mountain wind, soft phone shutter clicks. No dialogue, no music.
```
Variante consigliata, da aggiungere prima di "Audio": `The last filter is an acid-green aura glow that makes the red hat shine like a beacon; a faint green glint pulses off the real hat.`

**SHOT 05** — tieni 6 s
```
2D flat cel cartoon, thin black outlines, deadpan comedy. Static close-up. The black Labrador barks urgently and repeatedly at the sky, head jerking with each bark, ears flapping. In the blurred background the young man never looks up from his phone. Audio: loud urgent dog barks, wind. No human speech, no music.
```

**SHOT 06** — tieni 7 s
```
2D flat cel cartoon, thin black outlines, satirical sci-fi. Slow push-in. The acid-green rift widens with crackling edges; the lumpy asymmetrical spaceship descends, wobbling, its mismatched lights blinking out of sync. Far below, three tiny hikers raise their phones higher; nobody runs. Audio: deep wobbly sci-fi drone, electric crackle. No dialogue, no music.
```
Variante consigliata, da aggiungere prima di "Audio": `The ship turns slightly, as if homing in on a small green glint on the summit.`

**SHOT 07** — tieni 8 s
```
2D flat cel cartoon, thin black outlines, deadpan comedy. Low angle, camera tilting upward with the motion. The green beam pulls the red bucket hat upward; the young man refuses to let go and is lifted off the ground, legs dangling, deadpan. His phone slips from his hand and falls out of frame. The dog leaps, bites his boot at the ankle and is lifted along, dangling and wagging. Audio: rising tractor-beam hum, a small yelp, wind. No dialogue, no music.
```

**SHOT 08** — tieni 6 s
```
2D flat cel cartoon, thin black outlines. Static close-up of the phone on the rock. An upload progress bar fills, the selfie posts itself, small heart icons pop up. Reflections of green spaceship lights slide across the glass and fade away. No readable text. Audio: soft notification pings, a fading spaceship whoosh. No dialogue, no music.
```

**SHOT 09a** — tieni 5,5 s
```
2D flat cel cartoon, thin black outlines, satirical sci-fi. Slow reveal pan through the dark alien temple. Lights switch on one by one along the hall, revealing row after row of strange diverse aliens bowing in unison toward the glowing red bucket hat on the pedestal. Audio: heavy clunks of lights switching on, low reverent alien murmur. No clear words, no music.
```

**SHOT 09b** — tieni 3,5 s
```
2D flat cel cartoon, thin black outlines, deadpan comedy. Static medium shot. The hatless young man looks at the bowing aliens, then straight at the camera, blinks slowly, mouth closed. The dog tilts its head. Audio: near silence, faint room tone. No dialogue, no music.
```

---

## Dopo la generazione

Scarica i clip, rinominali `shot01.mp4`, `shot03.mp4`, `shot04.mp4`, `shot05.mp4`,
`shot06.mp4`, `shot07.mp4`, `shot08.mp4`, `shot09a.mp4`, `shot09b.mp4`, e caricali in
chat oppure mettili in `clips/` e lancia `python3 assemble.py`.

Il montaggio fa tutto il resto:
- taglia ogni clip alla sua durata;
- aggiunge il title card "20 MINUTI PRIMA";
- aggiunge le voci in italiano e la musica lo-fi, con il silenzio totale dallo shot 9.

Per ora l'audio originale dei clip viene scartato.
