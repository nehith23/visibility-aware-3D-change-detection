# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **3** (plus 3 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 92%
* Share of 'after' surfaces observed in 'before': 98%
* Metric scale factor: 2.056 (from a 1.2 m camera height assumption)

1. **Moved** (confidence 0.76): The brown laundry basket moved 0.4 m forward. It now stands on the floor, 0.6 m ahead of and 2.1 m to the right of the starting point.
2. **Added** (confidence 0.71): A black bed (about 50 x 40 x 25 cm) appeared on a surface about 0.52 m high, 2.6 m ahead of and 1.3 m to the right of the starting point.
3. **Removed** (confidence 0.55): A black backpack (about 35 x 30 x 35 cm) was removed from a surface about 0.54 m high, 1.4 m ahead of and 1.2 m to the right of the starting point.

## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

4. Added (confidence 0.45): A brown backpack (about 40 x 20 x 15 cm) appeared on a surface about 0.72 m high, 0.2 m ahead of and 2.1 m to the right of the starting point.
5. Moved (confidence 0.44): The grey printer moved 2.2 m to the right, down 0.3 m. It now stands on a surface about 0.51 m high, 2.3 m ahead of and 1.9 m to the right of the starting point.
6. Added (confidence 0.00): A grey printer (about 20 x 10 x 20 cm) appeared on a surface about 0.63 m high, 2.8 m ahead of and 0.3 m to the left of the starting point.

## Rejected by geometric filters

9 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 4 x looks the same in the other recording
* 3 x see-through structure (slats, spokes, cables)
* 1 x line-like (tube or cable, below depth resolution)
* 1 x small and evidence not strong enough

The larger ones (100 points or more):

* after: region at [2.01, 1.85, 1.07], 357 points: looks the same in the other recording (only 42% of the see-through views look different)
