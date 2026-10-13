# Ablation: what each part contributes

```
python scripts/ablation.py examples/ground_truth.json
```

(needs `reconstructions.zip` from the release unzipped into `examples/`; scenes whose reconstruction is missing are skipped). CLIP is off, so move matching and confidence differ slightly from the published reports, which use CLIP. Frozen settings.

Four detectors run on the same reconstruction, the same alignment and the same filtered point clouds (voxel grid, range limit, self-support filter):

1. **nearest-neighbour diff**: a point is changed if the other cloud has no point within 5 cm;
2. **visibility only**: the free-space votes (present / gone / unobserved), no further filters;
3. **full pipeline, every candidate**: everything the pipeline lists, low confidence included;
4. **full pipeline, confident only**: changes at or above the 0.5 threshold.

Methods 1 and 2 are clustered the same way and keep clusters of 120 points or more. Method 3 can also list smaller regions (25 to 120 points) when their evidence is strong, so it is not size-matched to 1 and 2.

"x/y found" counts ground-truth change locations hit by a reported region within 0.5 m (horizontal). A move has two locations, old and new. "spatial FP" counts reported regions that are not near any real change.

## Development set: the corridor

| method | corridor_right (same direction) | corridor_same (same direction) | corridor_cross (opposite directions) | corridor_null (nothing changed) |
|---|---|---|---|---|
| nearest-neighbour diff | 4/4 found, 40 spatial FP | 3/3 found, 27 spatial FP | 3/4 found, 18 spatial FP | 30 spatial FP |
| visibility only | 4/4 found, 3 spatial FP | 3/3 found, 1 spatial FP | 4/4 found, 8 spatial FP | 9 spatial FP |
| full pipeline, every candidate | 4/4 found, 7 spatial FP | 3/3 found, 5 spatial FP | 4/4 found, 6 spatial FP | 7 spatial FP |
| full pipeline, confident only | **4/4 found, 0 spatial FP** | **2/3 found, 0 spatial FP** | **4/4 found, 3 spatial FP** | **1 spatial FP** |

The thresholds were set on these recordings, so this shows what each stage does, not how well it generalises.

## Held-out: new recordings of the room

Recorded and analysed after the settings were frozen (`heldout/FREEZE.json`); nothing was tuned on them. It is the same room used, cluttered and filmed differently, during development. Five change locations per comparison: jug, backpack old spot, chair seat (box old spot and backpack new spot coincide), box new spot, duffel bag.

| method | room_A | room_B | room_cross (different paths) | room_null (nothing changed) |
|---|---|---|---|---|
| nearest-neighbour diff | 5/5 found, 12 spatial FP | 5/5 found, 15 spatial FP | 5/5 found, 20 spatial FP | 23 spatial FP |
| visibility only | 5/5 found, 2 spatial FP | 5/5 found, 1 spatial FP | 5/5 found, 1 spatial FP | 3 spatial FP |
| full pipeline, every candidate | 5/5 found, 1 spatial FP | 4/5 found, 0 spatial FP | 5/5 found, 2 spatial FP | 4 spatial FP |
| full pipeline, confident only | **5/5 found, 1 spatial FP** | **4/5 found, 0 spatial FP** | **4/5 found, 0 spatial FP** | **0 spatial FP** |

The room_A confident spatial FP is the wrong jug pairing's arrival end. It is confident here (0.54) only because CLIP is off; with CLIP it scores 0.44 (see the README).

## Reading it

* **The visibility test is what carries the result.** Against a nearest-neighbour diff on identical clouds it removes 56 to 96% of the spatial false positives (about 90% on a typical pair), held-out pairs included, without losing a change location. A nearest-neighbour diff reports every surface the other video did not happen to see.
* "Every candidate" can exceed "visibility only" because it also lists small regions as low-confidence candidates. None of the extra ones reaches the confident tier.
* The confident tier is clean on same-direction corridor pairs and on every room pair except the CLIP-off jug pairing. Opposite-direction recordings remain the weak case.

## Limits of this comparison

This is a coarse location-coverage check, not object-level precision and recall:

* **The reference locations are not independent measurements.** The ground truth of *what* changed comes from the person who moved the objects, but the (x, y) of each change was read off the pipeline's own change boxes and checked by eye against the evidence crops and videos (`examples/ground_truth.json`). They do not validate geometric accuracy. The one independent measurement is the backpack's move: 1.58 m from the boxes against 1.7 m by tape.
* `score()` ignores change type, object identity and height, and does not penalise several regions near one location.
* A 0.5 m radius can merge nearby changes: in the room, the chair seat and the box's new spot on the floor are 0.41 m apart.
* It cannot tell whether a removal and an addition were **paired** correctly. The two wrong associations in the room count as hits here; the README lists them.

An object-level evaluation would need independent annotations and one-to-one, type-aware matching.
