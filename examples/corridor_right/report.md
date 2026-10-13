# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **3** (plus 6 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 97%
* Share of 'after' surfaces observed in 'before': 97%
* Metric scale factor: 5.088 (from a 1.2 m camera height assumption)

1. **Removed** (confidence 0.76): A black suitcase (about 55 x 25 x 60 cm) was removed from the floor, 5.7 m ahead of and 2.1 m to the left of the starting point.
2. **Removed** (confidence 0.67): A brown storage box (about 100 x 50 x 75 cm) was removed from the floor, 4.5 m ahead of and 3.6 m to the left of the starting point.
3. **Moved** (confidence 0.55): The black backpack moved 3.5 m forward. It now stands on the floor, 6.6 m ahead of and 2.6 m to the left of the starting point.

## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

4. Added (confidence 0.50): A grey door (about 30 x 15 x 80 cm) appeared on a surface about 0.63 m high, 3.3 m ahead of and 3.0 m to the left of the starting point.
5. Added (confidence 0.37): A grey object (about 55 x 25 x 60 cm) appeared on the floor, 3.1 m ahead of and 3.1 m to the left of the starting point.
6. Added (confidence 0.26): A grey door (about 50 x 5 x 100 cm) appeared on a surface about 0.46 m high, 3.0 m ahead of and 2.7 m to the left of the starting point.
7. Added (confidence 0.00): A grey object (probably a blurry photo) (about 30 x 5 x 25 cm) appeared on a surface about 0.31 m high, 3.9 m ahead of and 3.5 m to the left of the starting point.
8. Added (confidence 0.00): A dark grey rug (about 25 x 10 x 5 cm) appeared on the floor, 2.3 m ahead of and 1.8 m to the left of the starting point.
9. Added (confidence 0.00): A dark grey rug (about 20 x 10 x 5 cm) appeared on a surface about 0.09 m high, 2.3 m ahead of and 1.6 m to the left of the starting point.

## Suppressed candidates

Regions that changed geometrically but look like bare wall, floor or shadow, usually small alignment or lighting errors:

* before: region at [-4.23, 5.2, 0.95] looked like 'blurry photo' (57%)
* before: region at [-3.8, 4.39, 1.34] looked like 'blurry photo' (51%)
* before: region at [-2.57, 2.36, 0.93] looked like 'window' (91%)
* after: region at [-2.09, 5.61, 1.37] looked like 'plain wall' (89%)
* after: region at [-2.02, 1.59, 0.42] looked like 'plain wall' (66%)
* after: region at [-1.88, 5.29, 1.33] looked like 'plain wall' (57%)
* after: region at [-1.62, 4.64, 1.64] looked like 'blurry photo' (89%)
* after: region at [-1.62, 4.75, 1.09] looked like 'blurry photo' (67%)
* after: region at [-1.6, 4.65, 1.4] looked like 'blurry photo' (63%)

## Rejected by geometric filters

4 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 2 x line-like (tube or cable, below depth resolution)
* 1 x looks the same in the other recording
* 1 x small and evidence not strong enough

The larger ones (100 points or more):

* before: region at [-3.13, 3.32, 0.75], 447 points: looks the same in the other recording (only 38% of the see-through views look different)
