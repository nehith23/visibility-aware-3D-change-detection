# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **0** (plus 4 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 90%
* Share of 'after' surfaces observed in 'before': 96%
* Metric scale factor: 2.092 (from a 1.2 m camera height assumption)


## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

1. Removed (confidence 0.33): A brown cabinet (about 65 x 40 x 105 cm) was removed from a surface about 0.14 m high, 0.1 m ahead of and 2.0 m to the right of the starting point.
2. Added (confidence 0.17): A grey bed (about 70 x 30 x 35 cm) appeared on a surface about 0.53 m high, 2.3 m ahead of and 1.9 m to the right of the starting point.
3. Removed (confidence 0.00): An orange cabinet (about 20 x 10 x 60 cm) was removed from the floor, 0.1 m behind and 1.3 m to the right of the starting point.
4. Added (confidence 0.00): A grey object (probably a water bottle) (about 20 x 10 x 15 cm) appeared on a surface about 0.71 m high, 2.7 m ahead of the starting point.

## Suppressed candidates

Regions that changed geometrically but look like bare wall, floor or shadow, usually small alignment or lighting errors:

* after: region at [2.04, 1.77, 1.32] looked like 'plain wall' (61%)

## Rejected by geometric filters

8 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 5 x small and evidence not strong enough
* 2 x looks the same in the other recording
* 1 x see-through structure (slats, spokes, cables)

The larger ones (100 points or more):

* before: region at [1.75, 2.64, 0.93], 140 points: looks the same in the other recording (only 18% of the see-through views look different)
