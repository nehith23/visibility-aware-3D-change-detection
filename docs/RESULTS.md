# Results in detail

The README has the summary. This page has every comparison.

How to read a result line: each detected change gets a number, a type (moved, added, removed) and a confidence score from 0 to 1. A score of 0.5 or more counts as a confident change. Anything lower is listed separately as "low confidence". The names come from CLIP and are often wrong. The position and size come from the 3D geometry and are more reliable.

## 1. My room (held-out test)

### Setup

Four videos of my bedroom, about 3 x 3 m, after clearing out the bike and loose clutter. iPhone 15 Pro, 0.5x lens, landscape, 1080p at 30 fps, phone at about 1.20 m, about 55 s each. Path A starts at the door and goes desk, bed, wardrobe. Path B goes the other way round.

| video | content |
|---|---|
| `before_A`, `before_B` | the room before the changes, two different paths |
| `after_A`, `after_B` | the room after the changes, two different paths |

What I changed between "before" and "after":

1. Removed the water filter jug from the black side table.
2. Moved the black backpack from the bed to the folding chair, about 1.7 m (measured with a tape).
3. Moved the grey storage box from the chair seat down to the floor next to the chair.
4. Added a black duffel bag on the bed.

### Why this counts as held out

I developed and tuned everything on the corridor recordings, on earlier failed recordings of this same room, and on a synthetic room. Then I froze the code and saved a hash of every file in [heldout/FREEZE.json](../heldout/FREEZE.json). Only after that did I record and analyse these room videos, once each. `python scripts/verify_freeze.py` checks the detection code still matches the frozen hashes. This tests new recordings of a room I had used before, in a different state. It is not a test on a room the system has never seen.

### What it found

| real change | room_A (before_A vs after_A) | room_B (before_B vs after_B) | room_cross (before_A vs after_B) |
|---|---|---|---|
| jug removed | found, but low confidence (0.44) and wrongly linked to an empty spot | found (0.50), but named "printer" | found, low confidence (0.44) |
| backpack, bed to chair | its removal from the bed is found (0.55); its arrival on the chair only at low confidence (0.45); the two are not linked | its arrival is wrongly linked to the box leaving the same seat (0.59); its old spot is missed | its old spot is wrongly linked to the duffel bag on the bed (0.65); its arrival is low confidence (0.42) |
| box, seat to floor | found as a move of 0.4 m (0.76), named "laundry basket" | its new spot is found (0.68); its old spot is used in the wrong link above | found as a move: 0.2 m sideways, 0.3 m down (0.70) |
| duffel bag added | found (0.71), but named "bed" | found (0.81), named "black bag" | used in the wrong link above |

Nothing changed (`room_null`, before_A vs before_B): no confident changes. Four low-confidence candidates, the highest at 0.33.

### What I take from it

* **Where something changed is right.** All nine confident predictions sit on a spot where something really changed, and the no-change comparison reports nothing confident.
* **Which object went where is the weak part.** Both wrong links happen where two things change in the same place: two dark bags on the bed, and two objects swapping places on the chair seat. The matcher links a removal to an addition when size, colour, appearance and height agree, and here they do. It has no way to say "a different object replaced this one".
* **The same situation hides changes.** The backpack sits where the box used to be, so most of its volume is in space that was already full. Only a 14 cm slice above the old box counts as new. That slice is too small and too light in colour for the matcher to link it to the backpack's removal.
* **Names are unreliable.** The best view of a duffel bag on a bed is mostly bed, so CLIP says "bed". The jug's view is mostly the 3D printer next to it.
* **Distances are about right.** The backpack's measured move is 1.58 m against 1.7 m by tape, 7% off. The only scale input is the 1.20 m phone height.
* **The wide lens helped.** The footage check said the camera mostly turned on the spot, but the 0.5x lens still gave enough overlap and depth in a small room. The passes lined up to within 0.3% of the room size, against 0.7 to 1.6% in the corridor.

Counted over the three comparisons with changes (12 real changes in total): 5 are reported as the right confident event, 2 more are found at one end only, and the rest are low confidence, wrongly linked or missed.

## 2. The corridor (where the method was developed)

Four videos of the corridor in my flat, about 10 m long. iPhone 15 Pro, portrait, 1x lens, 1080p at 30 fps, phone at about 1.20 m, 45 to 50 s each. The `Left` and `Right` clips walk the corridor in opposite directions.

Before: a brown suitcase, a black folding chair with a cardboard box on it, and a black backpack. After: suitcase and chair removed, backpack moved further down.

![Corridor inputs](../examples/corridor_right/inputs.jpg)

| comparison | walking directions | real changes found (confident) | confident predictions with no real change |
|---|---|---|---|
| `corridor_right`: before_Right vs after_Right | same | 3 of 3: suitcase (0.76), chair with box (0.67), backpack moved 3.5 m (0.55) | 0 |
| `corridor_same`: before_Left vs after_Left | same | 2 of 3: suitcase (0.63), chair with box (0.68). The backpack is only "removed" at 0.49, because this video never films where it went | 0 |
| `corridor_cross`: before_Left vs after_Right | opposite | 3 of 3: backpack moved 3.8 m (0.74), suitcase (0.70), chair with box (0.66) | 1, a door frame "moved" (0.58) |
| `corridor_null`: before_Left vs before_Right | opposite, nothing changed | | 1, half of the unchanged suitcase (0.50) |

I tuned the settings on these recordings, so this shows what the method can do, not how well it generalises.

* **Same walking direction works cleanly.**
* **Opposite directions are harder.** Walking one way, then back, gives few shared views of the same surfaces, so the two recordings line up less precisely: about 2 to 3 degrees of correction, against 0.2 degrees for the same direction. Door frames a few metres away end up a few centimetres off and look changed. Most of these false alarms are now filtered out, but not all.
* **Names:** "brown storage box" for the chair with the box on it is fair. The suitcase is brown, but CLIP calls it black in the dim light.

![Corridor evidence](../examples/corridor_right/evidence.png)

## 3. Is the visibility test doing the work?

[examples/ablation.md](../examples/ablation.md) compares four versions on the same data: a plain "is there a point nearby in the other scan" diff, the visibility test alone, the full pipeline with every candidate, and the full pipeline's confident changes only.

In the room's no-change comparison they report 23, 3, 4 and 0 false changes. In corridor_right they report 40, 3, 7 and 0, and all four still hit every real change. That page also explains the limits of this check.

## 4. The first attempt, which failed

My first recordings were of the same bedroom before I cleared it, in portrait on the 1x lens. The camera mostly turned on the spot, and the room was full of thin, see-through things: a bike, bed slats, cables. The 3D model did not look like the room, the no-change test produced many false alarms, and CLIP called the water jug a "kettle". Several filters, the fix for portrait video, and the footage checker came out of working out why. Clearing the room and switching to the 0.5x lens in landscape is what made the held-out test possible.

## 5. Synthetic room

`python -m roomdiff demo` renders a fake room with known changes, adds depth noise, and hides the scale and the direction of gravity, so the pipeline has to recover them.

| change | found | confidence | position error (horizontal / vertical) |
|---|---|---|---|
| chair moved 1.3 m and turned 90 degrees | yes, turn estimated at 90 degrees | 0.99 | 0.00 m / 0.01 m |
| box removed | yes | 0.50 (just under the threshold) | 0.01 m / 0.00 m |
| backpack added on the floor | yes | 0.58 | 0.01 m / 0.00 m |
| bottle added on a table | yes | 0.13 (low) | 0.00 m / 0.00 m |
| bin seen only in "before" | correctly not reported; all of its points marked "not verified" | | |

All four changes are found and nothing else is reported. Two of the four are below the confidence threshold, because the synthetic objects are flat colours and the appearance check has little to work with. This only tests the geometry, not the depth model.
