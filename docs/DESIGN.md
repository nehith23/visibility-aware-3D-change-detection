# Design notes and trade-offs

This page explains each design choice and its trade-off. Measured results are in [RESULTS.md](RESULTS.md).

## The core problem

Two recordings of a space never see the same surfaces. A plain point cloud diff ("is there a point near p in the other scan?") reports every surface the second camera did not look at as *removed*. A robot using that would plan around obstacles that are not there.

So the question asked of every 3D point is: **did a camera in the other recording see through the place where this point was?** Only evidence of empty space counts as a change. No evidence means *unverified*.

The second problem showed up on real footage: learned depth is not perfectly rigid, and two recordings never line up perfectly. Most of the later work went into telling a real change from a few centimetres of misalignment (sections 5 to 9).

## Pipeline

```
before.mov ─┐                      ┌─ room frame (gravity, floor, metric scale) + ICP refinement
            ├─ keyframes ─ VGGT ───┤
after.mov ──┘  (stitched passes)   └─ per-frame depth + cameras, one shared frame
                                                    │
                     visibility votes: every point vs every camera of the other scan
                                                    │
                       present / gone / unobserved per point
                                                    │
               cluster "gone" points ─ shape filters ─ regions
                                                    │
            local re-registration ─ appearance check ─ depth-edge check ─ confidence
                                                    │
               CLIP label + size prior ─ match removed↔added ─ moved / added / removed
                                                    │
            sentences, 3D page, top-down map, before/after evidence, PLY, JSON
```

## Choices

### 1. One shared VGGT reconstruction instead of two reconstructions plus registration

Keyframes from both videos go through VGGT together. Every camera and depth map comes out in one coordinate frame, so there is no separate global registration step to fail. Classic SfM (COLMAP) is the alternative: more accurate on textured scenes, but slow, brittle on blank walls (a corridor is mostly blank walls), and it would still need dense depth from somewhere. MASt3R or other point-map models would fit behind the same interface (`roomdiff/backends/`).

**Memory.** VGGT's memory grows linearly with image tokens (frames x patches). The run measures the GPU and plans for it. The aggregator runs under bf16 autocast anyway, so below 16 GB its weights are stored in bf16 (frees about 1.8 GB); the heads stay in fp32 as in the reference code. An 8 GB laptop GPU then holds about 25 square frames at 518 px.

**Stitching passes.** 25 frames for two recordings is too few to see every part of a 10 m corridor twice. So keyframes are split into several passes (`backends/stitch.py`). Every pass also contains the same 8 anchor frames, 4 spread over each recording, and the other frames are interleaved so each pass covers the whole space rather than one end. Each pass comes back in its own arbitrary similarity frame. An anchor's depth map in pass *j* and in pass 0 gives 3D points at *identical pixels*, so the transform between passes is a closed-form Umeyama fit on exact correspondences, with a trimmed refit to ignore the worst 20%. No feature matching is needed. On the corridor, 80 frames ran as 5 passes and the anchor residual was 0.7 to 1.6% of the scene size. An out-of-memory error retries with 20% fewer frames per pass.

*Trade-off:* frames in different passes never attend to each other, so cross-pass consistency is only as good as the anchors. One joint pass on a bigger GPU is better; stitching is what makes 8 GB usable.

**Portrait footage.** Narrow portrait frames, resized to VGGT's input width, gave strongly anisotropic intrinsics (fx 195 against fy 466 on the bedroom clips) and depth that did not agree between frames. Padding every frame to a square canvas, which is VGGT's own "pad" preprocessing, fixed it. Intrinsics are mapped back to the full-resolution frame afterwards, so crops for CLIP and the evidence sheet use the original pixels.

**HDR.** iPhone footage is HLG HDR by default. Decoded naively it looks washed out, which hurts both depth and CLIP. The pipeline detects it and tone-maps to SDR with ffmpeg (downscaling to 1080p first, because tone mapping 4K is slow).

The VGGT-1B weights are licensed for non-commercial use.

### 2. Free-space evidence, not proximity

For point `p` from one recording and each camera of the other, with measured depth `d` at `p`'s pixel and `p`'s own depth `z`:

| condition | meaning | vote |
|---|---|---|
| `|d - z| < tol` | surface still there | present |
| `d > z + tol` in the whole neighbourhood | camera saw the space behind `p` | gone |
| `d < z - tol` | something in front | none (occluded) |
| outside the image | | none |

A point is **gone** with at least 2 "gone" votes and at least 70% of its evidence saying so, **present** with any agreement, and **unobserved** with no evidence at all. Tolerance is `max(6 cm, 4% of depth)`, because learned depth error grows with distance.

Details that matter a lot on real data:

* The "gone" test uses the *minimum* depth in a 5x5 window. A pixel next to a depth edge cannot vote "see-through".
* Low-confidence pixels (the bottom 25% per frame) count as invalid and can never vote "gone".
* **Incidence.** A surface seen at a grazing angle changes depth fast along the ray, so a small pose error reads as "seen through". The tolerance is divided by the cosine between the viewing ray and the surface normal, capped at 2x for walls and object sides and 5x for horizontal surfaces, where grazing views are the norm (a floor 4 m ahead).
* **Floor band.** Points within 6 cm of the fitted floor are never "gone". A carpet re-measured a few centimetres differently is not an object, and a real object always sticks out above the band anyway.

### 3. Range and self-consistency filters

Points further than 4.5 m from the camera that saw them are dropped: in a room that is only ever the view through a window, where learned depth is unreliable. In the corridor it limits each point to the views where it was reasonably close.

Each point must also be confirmed by at least two frames of its own recording. This removes flying pixels at depth discontinuities and anything that moved during a recording.

### 4. Metric scale and gravity without extra sensors

People hold phones upright, so the average image "down" axis is a good gravity estimate. A RANSAC plane roughly perpendicular to it, at the low end of the height distribution, is the floor. Scale comes from the median camera height above the floor, which you pass with `--camera-height` (1.20 m for the corridor). On the synthetic room the scale error is under 1%.

*Trade-off:* this breaks if the floor is never visible (the log warns, and `--scale` overrides), and a wrong height scales every size and distance by the same factor.

### 5. Refining the registration

VGGT's joint frame is good but not exact. After the room frame is set, the after cloud is refined onto the before cloud with trimmed point-to-plane ICP. It is accepted only if the share of points within 3 cm of the other cloud improves by at least 1%, and the correction is under 10 degrees and 0.5 m. An earlier version accepted on median distance, which can improve while the alignment gets worse (it rewards sliding onto the floor).

Same-direction pairs needed 0.1 to 0.2 degrees of correction. Opposite-direction pairs needed 1.75 to 3.1 degrees, and that is where most remaining false positives come from (see Known limitations).

### 6. Shape filters: what a real object does not look like

Gone points are clustered with DBSCAN (6 cm). Small fragments are then attached to a much larger cluster close by (a host of at least 150 points, at least 4x the fragment, within 20 cm), because depth noise splits one chair into pieces. Merging is one way on purpose: the first version merged chains of neighbours and turned a backpack next to a bike into one 2 m blob.

Then regions are dropped when their shape says "artefact", not "object":

* **Sheets.** A slice of wall or floor: very flat (third principal spread under 3 cm, or under a fifth of the second for a thicker slab) and large. This is the signature of a misregistered surface.
* **Poles and cables.** Narrower than 6 cm and much longer than wide, or with a second principal spread under 1.8 cm. Bike tubes, chair legs and cables are near the depth resolution of the pipeline, and they produced most false positives in the bedroom.
* **Floor noise.** Anything lower than 8 cm in total.

### 7. Local re-registration

Learned depth is not perfectly rigid: one wall can be a few centimetres off while the rest of the scene is aligned. So each candidate's neighbourhood (everything within 60 cm) is re-registered on its own with ICP, and the visibility test is repeated. A real object stays gone, because the space it occupied is empty whatever the local alignment. A local misregistration disappears. The share of points still gone after this becomes part of the confidence. If the local fit wants to move more than 8 cm or 4 degrees, it is treated as unreliable and abstains instead of deciding.

### 8. Appearance and depth-edge corroboration

**Appearance.** For every view of the other recording that "sees through" a region, the colour at those pixels is compared (Lab distance, threshold 18) with the region's own colour. When a real object is removed, the camera now sees the wall or floor behind it, which looks different. When depth is just wrong, the pixels look the same. Regions where under 45% of the evidence looks different are dropped.

**Depth edges.** A slatted footboard, bicycle spokes or a stair railing produce clusters full of depth discontinuities, because the camera sees through gaps between thin parts. A pixel is on a depth edge when depth varies by more than 10% within 7 px of it. For each region the share of its observations on a depth edge is compared with what a solid object of that image size would have from its own outline (roughly `1 - ((s - 6) / s)^2` for an object `s` pixels across). Regions more than 25 percentage points above that are dropped. Normalising by size matters: an earlier fixed threshold removed the small bottle on the synthetic desk.

### 9. Confidence instead of a hard threshold

A single cut-off either drops real small objects or keeps noise. Each region gets a score from its own evidence:

```
confidence = sqrt(size) x appearance x (0.5 + 0.5 x compact) x local x views x slab
```

* `size`: log-scaled from 120 to 2000 points.
* `appearance`: share of see-through views that look different.
* `compact`: 1 minus the scaled depth-edge excess.
* `local`: share still gone after local re-registration.
* `views`: how many frames of the other recording saw through the region, full weight from 4. On the corridor, every confident false positive with weak support was seen through by exactly 2 frames, typically a camera 1.2 m away glancing past a surface the other video only saw from 4.5 to 6 m. Learned depth at 5 m is uncertain by about 20 cm, so that is not evidence. No real change had fewer than 3.
* `slab`: `sqrt(min(1, width / 10 cm))`. Door leaves and wall slices that come loose under misregistration are 3 to 9 cm thick; the thinnest real object in the data, a backpack seen side-on, is 12 cm.

A move combines its two halves with a noisy-OR and multiplies by `0.6 + 0.4 x match quality`. Changes at 0.5 or above are reported; below that they are listed as "possible change (low confidence)" in every output, dotted on the map and grouped separately in the 3D view. Small regions under 120 points are only listed if their evidence is very strong.

Every filter records what it rejected and why (`rejected_by_filters` in `report.json`, counts by reason in `report.md`), next to the candidates CLIP suppressed as bare wall or floor. Each reported change also carries the evidence behind its score.

These are heuristic evidence scores, not calibrated probabilities. The factors and the 0.5 tier were tuned on the corridor and the failed first bedroom recordings, with the no-change pairs as the main check. The room recordings were then analysed with these settings frozen ([RESULTS.md](RESULTS.md)).

### 10. Objects, moves and semantics

Each region gets a gravity-aligned box from a minimum-area rectangle of its footprint. Its bottom is snapped to the surface found under it **in the other recording**, because the lowest centimetres of an object always fall within depth tolerance of the floor.

A region that vanished from "before" and one that appeared in "after" are paired as a **move** with the Hungarian algorithm on a cost combining size (log ratio of sorted dimensions), colour (Lab distance), CLIP embedding similarity and support height, with hard gates: sizes within 2x, colour within 30, at least 60 points each. Rotation comes from a yaw search minimising a symmetric chamfer distance between the two clusters. Symmetric because each cluster is a partial view, and a one-way distance rewards rotating the small one into the big one.

Each region is cropped from the full-resolution frame that sees it best and labelled by CLIP (ViT-B-32, LAION-2B) over about 70 household classes plus a few structure classes (wall, floor, shadow, blurry photo). CLIP alone will call a 40 cm box a "wardrobe", so its probabilities are weighted by a loose size prior per class. If the winning label still contradicts the measured height by a wide margin (a 60 cm tall "door"), the name falls back to "object" and CLIP's guess is kept in the report. Crops that CLIP thinks are structure are suppressed and listed. Labels are local only, no API calls.

## Footage quality check

`roomdiff check` scores a recording before any GPU time is spent:

* **Blur** relative to the clip's own sharpest frames (absolute Laplacian variance confuses a blank wall with blur), plus a separate low-texture score so blank walls are reported as such.
* **Gaps:** the longest stretch with no sharp frame, i.e. a part of the space with no usable view.
* **Rotation-only score:** the ratio of homography inliers to fundamental-matrix inliers on frame pairs 0.5 s apart. Pure rotation is fully explained by a homography, so values near 1 mean the camera turned on the spot and depth has little parallax.

It only says "re-record" when something is severe, otherwise it lists what to improve.

## What I learned from the results

* **Localisation transferred to the new room recordings; association did not.** The matcher links a removal and an addition when size, colour, CLIP embedding and height agree. It has no outcome for "a different object replaced this one", which is where both wrong links in the room came from.
* **The no-change pairs were the most informative test.** They exposed the opposite-direction misalignment that the change pairs alone did not show.
* **Recording mattered more than any threshold.** The first, cluttered bedroom recordings failed; most of sections 6 to 8 came from studying why. The same room, cleared and filmed on the 0.5x lens in landscape, reconstructed with a stitch residual of 0.3%, against 0.7 to 1.6% in the corridor.

The synthetic room (`python -m roomdiff demo`) checks the geometry and visibility logic against exact ground truth, but not VGGT's depth quality, which is the main error source on real footage.

## Known limitations

* Opposite-direction recordings register a few degrees off. The view-count and slab factors catch most of the resulting false changes, not all.
* Move pairing has no notion of replacement, and confuses similar objects that change close together.
* Labels come from one crop per object and can name the surroundings.
* An object moved by less than its own size overlaps itself, so only the non-overlapping parts register.
* Objects thinner than the depth tolerance (a book flat on a desk, a doormat) are below the noise floor.
* Thin structures (poles, cables, slats) are filtered out, so a real change to one is not reported either.
* Two identical objects swapped would not be detected.
* Reflective and transparent surfaces give inconsistent depth.

## What I would do next

1. **Use the iPhone LiDAR.** Record3D or ARKit exports give metric depth and VIO poses: no scale assumption, far less depth noise at short range, and a pose prior that would fix the opposite-direction registration.
2. **Non-rigid or piecewise registration.** Section 7 already shows that local alignment matters. Doing it everywhere, as a smooth deformation field, would remove most remaining false positives at the source.
3. **Instance masks.** SAM 2 masks lifted to 3D would split touching objects, give cleaner boxes than DBSCAN, and let CLIP see the object instead of the bed it lies on.
4. **Replacement-aware matching.** Compare the appearance of the removed and the added object directly (DINOv2 features from both crops) and allow a third outcome besides "moved": "replaced", when a different object now occupies the same spot. Both held-out pairing errors are this case.
5. **Calibrated confidence.** Record a dozen pairs with known changes and fit the confidence on them, instead of hand-tuning on the same recordings it is evaluated on.
6. **Persistent map.** Treat each new recording as an update to a long-lived object map, which is closer to what a robot actually needs.
