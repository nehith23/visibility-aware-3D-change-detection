# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **2** (plus 4 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 97%
* Share of 'after' surfaces observed in 'before': 99%
* Metric scale factor: 5.337 (from a 1.2 m camera height assumption)

1. **Removed** (confidence 0.68): A brown storage box (about 55 x 50 x 60 cm) was removed from the floor, 5.5 m ahead of and 0.9 m to the right of the starting point.
2. **Removed** (confidence 0.63): A black suitcase (about 90 x 30 x 65 cm) was removed from the floor, 5.5 m ahead of and 2.7 m to the right of the starting point.

## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

3. Removed (confidence 0.49): A black backpack (about 40 x 20 x 45 cm) was removed from the floor, 3.7 m ahead of and 0.5 m to the right of the starting point.
4. Removed (confidence 0.00): A dark grey rug (about 15 x 10 x 5 cm) was removed from the floor, 2.3 m ahead of and 0.8 m to the right of the starting point.
5. Removed (confidence 0.00): A dark grey rug (about 30 x 15 x 5 cm) was removed from the floor, 4.6 m ahead of and 1.7 m to the right of the starting point.
6. Added (confidence 0.00): A grey rug (about 50 x 15 x 5 cm) appeared on a surface about 0.08 m high, 4.1 m ahead of and 1.1 m to the right of the starting point.

## Suppressed candidates

Regions that changed geometrically but look like bare wall, floor or shadow, usually small alignment or lighting errors:

* before: region at [3.57, 7.36, 0.42] looked like 'plain wall' (88%)
* after: region at [0.06, 2.78, 0.22] looked like 'shadow on a wall' (54%)
* after: region at [2.77, 6.48, 0.08] looked like 'blurry photo' (54%)

## Rejected by geometric filters

5 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 3 x line-like (tube or cable, below depth resolution)
* 1 x vanishes after local re-registration
* 1 x small and evidence not strong enough
