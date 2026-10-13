# What changed in the room

Directions are relative to where the 'before' recording starts, looking forward from the first frame.

* Changes found: **1** (plus 5 low-confidence candidates)
* Share of 'before' surfaces re-observed in 'after': 70%
* Share of 'after' surfaces observed in 'before': 84%
* Metric scale factor: 5.465 (from a 1.2 m camera height assumption)

1. **Removed** (confidence 0.50): A black suitcase (about 35 x 25 x 60 cm) was removed from the floor, 5.6 m ahead of and 2.6 m to the right of the starting point.

## Possible changes (low confidence)

Small or weakly supported; most often reconstruction noise. Listed so nothing is hidden.

2. Added (confidence 0.37): A black suitcase (about 35 x 5 x 50 cm) appeared on the floor, 5.3 m ahead of and 2.5 m to the right of the starting point.
3. Removed (confidence 0.33): A grey door (about 65 x 5 x 145 cm) was removed from a surface about 0.27 m high, 5.0 m ahead of and 0.4 m to the right of the starting point.
4. Added (confidence 0.23): A white door (about 30 x 10 x 110 cm) appeared on a surface about 0.15 m high, 7.7 m ahead of and 3.6 m to the right of the starting point.
5. Removed (confidence 0.12): A grey object (about 25 x 10 x 65 cm) was removed from the floor, 9.4 m ahead of and 2.2 m to the right of the starting point.
6. Added (confidence 0.00): A grey cardboard box (about 40 x 5 x 70 cm) appeared on the floor, 4.4 m ahead of the starting point.

## Suppressed candidates

Regions that changed geometrically but look like bare wall, floor or shadow, usually small alignment or lighting errors:

* before: region at [-0.12, 2.24, 1.72] looked like 'plain wall' (71%)
* after: region at [1.72, 3.07, 0.99] looked like 'bare floor' (56%)

## Rejected by geometric filters

4 candidate regions were dropped before labelling. Every one is listed with its reason in `report.json` (`rejected_by_filters`). Counts by reason:

* 2 x vanishes after local re-registration
* 1 x planar slice of wall or floor (misregistration)
* 1 x looks the same in the other recording

The larger ones (100 points or more):

* after: region at [2.56, 5.04, 0.92], 9205 points: planar slice of wall or floor (misregistration)
* after: region at [0.09, 3.06, 0.71], 663 points: vanishes after local re-registration (only 55% still changed, shift 4.3 cm)
* after: region at [1.23, 1.71, 1.32], 662 points: vanishes after local re-registration (only 46% still changed, shift 1.7 cm)
* after: region at [0.53, 3.69, 0.3], 112 points: looks the same in the other recording (only 31% of the see-through views look different)
