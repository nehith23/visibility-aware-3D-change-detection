# Design notes

Why the system is built this way, what each choice costs, and what failed. Exact thresholds are in `roomdiff/config.py`; measured results are in [RESULTS.md](RESULTS.md).

## The core problem

Two recordings never see the same surfaces. A plain point cloud diff ("is there a point near here in the other scan?") reports every surface the second video did not look at as removed.

So for every 3D point I ask: did a camera in the other recording see through the place where this point was? Only evidence of empty space counts as a change. No evidence means "not verified".

The second problem showed up on real footage: learned depth is not perfectly rigid, and two recordings never line up exactly. Most of the later work went into telling a real change from a few centimetres of misalignment.

## Choices

### One joint reconstruction

Keyframes from both videos go through VGGT together, so every camera and depth map lands in one coordinate frame and there is no separate registration step to fail. COLMAP was the alternative, but it relies on feature matching, which struggles on blank walls, and it would still need dense depth from somewhere else.

The cost is GPU memory. An 8 GB laptop GPU fits only 25 to 45 frames at once, too few to cover two videos. So the frames are split into passes that share the same 8 anchor frames. An anchor's depth in two passes gives 3D points at identical pixels, so the transform between passes is a closed-form fit on exact correspondences, with no feature matching. The passes lined up to within 0.3 to 1.6% of the scene size.

Portrait frames resized to VGGT's input width gave distorted camera intrinsics and inconsistent depth. Padding them to a square fixed it.

### Evidence of empty space

For a point at depth `z` in a camera of the other recording, which measured depth `d` at that pixel:

| condition | meaning | vote |
|---|---|---|
| `d` close to `z` | surface still there | present |
| `d` behind `z` everywhere around the pixel | camera saw through the spot | gone |
| `d` in front of `z` | something in the way | no vote |
| outside the image | | no vote |

A point is gone only with at least two "gone" votes and 70% of its votes agreeing. The tolerance grows with distance and at grazing angles, because learned depth is less precise there. Pixels on depth edges or with low confidence never vote "gone", and the floor itself is never "gone".

The cost is that everything depends on alignment, which is what the next choice deals with.

### Separating misalignment from real change

Misalignment produces recognisable shapes, so each candidate goes through a few checks:

* **Global refinement.** After VGGT, ICP aligns the second recording onto the first. A correction is kept only if it improves the overlap.
* **Shape.** Large flat slices of wall or floor, thin poles and cables, and clusters full of depth edges (bed slats, railings) are dropped. They are what misalignment and see-through structures look like.
* **Local re-alignment.** The area within 60 cm of each candidate is aligned again on its own. A real object stays gone; a local misalignment disappears.
* **Appearance.** Where the other video saw through a region, the pixels must also look different. A removed object reveals the wall behind it; wrong depth leaves the same pixels.

Every rejected candidate is listed in `report.json` with the reason.

### A confidence score instead of a hard cut

A single threshold either drops small real objects or keeps noise. Each candidate gets a score from 0 to 1 from its size, its appearance change, how compact it is, how much survives local re-alignment, how many camera views saw through it, and whether it is a thin slab like a door leaf. Changes at 0.5 or above are reported; the rest are listed as low confidence.

The weights are hand-tuned on the corridor and my first, failed room recordings. That is why I froze the code before analysing the new room recordings.

### Scale and gravity without extra sensors

People hold phones upright, so the average image "down" direction gives gravity. The floor is the lowest large plane, and the phone's height above it gives metres. On the synthetic room the scale error is under 1%; in the room, the backpack's 1.7 m move was measured as 1.58 m. The cost is that a wrong height scales every size and distance.

### Moves and names

A removal and an addition become a move when their size, colour, CLIP appearance and height agree. CLIP names each object from the best image crop, weighted by how plausible the name is for the measured size. If the name still contradicts the size, it falls back to "object".

## What failed, and what I learned

* **The first room recordings.** Cluttered, filmed in portrait on 1x, mostly turning on the spot. The 3D model did not look like the room, and bikes, slats and cables showed up as changes. The shape filters and appearance check came from this. Clearing the room and using the 0.5x lens in landscape fixed the recording itself.
* **Opposite walking directions.** Walking the corridor one way, then back, left the recordings 2 to 3 degrees apart, and door frames looked changed. Only the no-change comparisons revealed this. Counting how many camera views support a change, and down-weighting thin slabs, removed most of these false alarms.
* **Linking objects.** In the room, the matcher linked the wrong objects twice. Both times, two things changed in the same place. It has no way to say "a different object replaced this one".
* **Names.** CLIP names whatever fills the crop. The duffel bag lying on the bed was called "bed".

## What I would do next

1. Use the iPhone's LiDAR depth and tracked poses: metric scale, less depth noise, and no misalignment between walking directions.
2. Add a "replaced" outcome next to "moved", by comparing the removed and added objects' appearance directly.
3. Segment objects (for example with SAM 2) so the boxes are cleaner and CLIP sees the object, not its surroundings.
4. Record more scenes with known changes and fit the confidence score on them, instead of tuning by hand.
