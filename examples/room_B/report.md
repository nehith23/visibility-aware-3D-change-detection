# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **4** (plus 0 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 97%
* Share of 'after' surfaces observed in 'before': 96%
* Metric scale factor: 2.189 (from a 1.2 m camera height assumption)

1. **Added** (confidence 0.81): A black bag (about 45 x 35 x 20 cm) appeared on a surface about 0.53 m high, 1.8 m ahead of and 2.3 m to the left of the starting point.
2. **Added** (confidence 0.68): A brown storage box (about 65 x 40 x 50 cm) appeared on the floor, 2.1 m ahead of the starting point.
3. **Moved** (confidence 0.59): The brown laundry basket moved 0.2 m to the right, up 0.2 m. It now stands on a surface about 0.61 m high, 2.0 m ahead of and 0.4 m to the right of the starting point.
4. **Removed** (confidence 0.50): A grey printer (about 70 x 35 x 30 cm) was removed from a surface about 0.75 m high, 0.3 m ahead of and 2.5 m to the left of the starting point.

## Rejected by geometric filters

14 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 7 x looks the same in the other recording
* 5 x small and evidence not strong enough
* 1 x vanishes after local re-registration
* 1 x see-through structure (slats, spokes, cables)

The larger ones (100 points or more):

* before: region at [-1.38, 2.43, 1.08], 308 points: looks the same in the other recording (only 34% of the see-through views look different)
* before: region at [-1.16, 1.51, 0.74], 1194 points: see-through structure (slats, spokes, cables) (40% of observations on depth edges, 14% expected for a solid object)
* after: region at [0.32, 1.76, 0.18], 114 points: small and evidence not strong enough
