# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **4** (plus 4 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 72%
* Share of 'after' surfaces observed in 'before': 84%
* Metric scale factor: 5.282 (from a 1.2 m camera height assumption)

1. **Moved** (confidence 0.74): The black backpack moved 3.8 m forward and to the right, and turned about 175 degrees clockwise. It now stands on a surface about 0.11 m high, 6.6 m ahead of and 3.0 m to the right of the starting point.
2. **Removed** (confidence 0.70): A black suitcase (about 55 x 35 x 55 cm) was removed from a surface about 0.10 m high, 5.7 m ahead of and 2.7 m to the right of the starting point.
3. **Removed** (confidence 0.66): A brown storage box (about 50 x 45 x 60 cm) was removed from the floor, 5.5 m ahead of and 0.9 m to the right of the starting point.
4. **Moved** (confidence 0.58): The grey door moved 1.9 m back, down 0.5 m. It now stands on the floor, 3.1 m ahead of the starting point.

## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

5. Moved (confidence 0.25): The grey door moved 3.1 m back, and turned about 90 degrees anticlockwise. It now stands on a surface about 0.09 m high, 6.7 m ahead of and 3.2 m to the right of the starting point.
6. Removed (confidence 0.25): A white door (about 60 x 25 x 105 cm) was removed from a surface about 0.09 m high, 9.5 m ahead of and 2.0 m to the right of the starting point.
7. Removed (confidence 0.25): A grey object (about 35 x 5 x 50 cm) was removed from a surface about 1.03 m high, 3.8 m ahead of the starting point.
8. Removed (confidence 0.10): A grey blurry photo (about 75 x 5 x 45 cm) was removed from a surface about 1.19 m high, 2.5 m ahead of the starting point.

## Suppressed candidates

Regions that changed geometrically but look like bare wall, floor or shadow, usually small alignment or lighting errors:

* before: region at [-0.31, 1.73, 1.53] looked like 'blurry photo' (52%)
* after: region at [0.35, 4.15, 0.81] looked like 'bare floor' (97%)

## Rejected by geometric filters

3 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 2 x planar slice of wall or floor (misregistration)
* 1 x looks the same in the other recording

The larger ones (100 points or more):

* after: region at [1.51, 2.47, 1.25], 3701 points: planar slice of wall or floor (misregistration)
* after: region at [2.64, 5.3, 0.96], 11910 points: planar slice of wall or floor (misregistration)
