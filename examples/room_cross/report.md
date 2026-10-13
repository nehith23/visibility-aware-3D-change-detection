# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **2** (plus 4 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 90%
* Share of 'after' surfaces observed in 'before': 97%
* Metric scale factor: 2.092 (from a 1.2 m camera height assumption)

1. **Moved** (confidence 0.70): The brown trash can moved 0.2 m forward, down 0.3 m. It now stands on the floor, 0.4 m ahead of and 2.1 m to the right of the starting point.
2. **Moved** (confidence 0.65): The black backpack moved 1.1 m forward. It now stands on a surface about 0.52 m high, 2.6 m ahead of and 1.3 m to the right of the starting point.

## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

3. Removed (confidence 0.44): A grey object (about 65 x 25 x 35 cm) was removed from a surface about 0.73 m high, 2.5 m ahead of and 0.3 m to the left of the starting point.
4. Added (confidence 0.42): A black backpack (about 25 x 20 x 20 cm) appeared on a surface about 0.74 m high, 0.2 m ahead of and 2.1 m to the right of the starting point.
5. Removed (confidence 0.28): A grey handbag (about 60 x 35 x 45 cm) was removed from a surface about 0.67 m high, 2.4 m ahead of and 2.0 m to the right of the starting point.
6. Added (confidence 0.00): A small black object (about 10 x 10 x 40 cm) appeared on a surface about 0.71 m high, 0.9 m ahead of the starting point.

## Rejected by geometric filters

10 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 5 x looks the same in the other recording
* 4 x small and evidence not strong enough
* 1 x see-through structure (slats, spokes, cables)

The larger ones (100 points or more):

* before: region at [1.76, 2.72, 0.99], 107 points: looks the same in the other recording (only 30% of the see-through views look different)
