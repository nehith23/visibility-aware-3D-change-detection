# How to record the videos

The reconstruction is only as good as the footage. Run `python -m roomdiff check before.mov after.mov` on every take before spending GPU time; it scores blur, gaps and camera motion and tells you what to fix.

## What the test clips taught us

Two test clips of this room (no changes, one landscape, one portrait) scored:

| | landscape | portrait | target |
|---|---|---|---|
| resolution | 1024x576 | 576x1024 | 1920x1080 |
| blurry frames | 29% | 38% | under 15% |
| longest gap with no sharp frame | 4.7 s | 6.0 s | under 1.5 s |
| rotation-only score (1.0 = turned on the spot) | 0.84 | 0.91 | under 0.75 |

Coverage was good: both clips see the whole room, with the floor in view most of the time. The fixes are all about *how* the phone moves.

## What the real recordings taught us

* **The cluttered bedroom on the 1x lens did not work.** There was no room to step back, so the camera mostly turned on the spot, and thin clutter (a bike, bed slats, cables) produced false changes.
* **The same bedroom, cleared, on the 0.5x lens in landscape, worked.** The wide lens keeps most of a small room in every frame, so frames overlap and still have parallax. That gave the best reconstruction in the project and the held-out result in docs/RESULTS.md. Clear thin, see-through clutter, cover mirrors, switch screens off or leave them static, and keep fans still.
* **A corridor worked.** Walking its length gives the camera real sideways and forward motion, and the floor stays in view.
* **Walk the same direction in "before" and "after".** Same-direction pairs registered within 0.2 degrees and found every change. Opposite-direction pairs were 2 to 3 degrees off and reported door frames as changes. If you want a second direction, record it as an extra pass, not instead.
* **Film every spot that changed in the "after" video**, including the new position of anything moved. One "after" clip never saw where the backpack went, so it could only report it as removed.

## 1. Prepare the room

* Same lighting for every video: same lamps on, curtains in the same position.
* Lower the blinds part way so the window is not blown out. Bright windows turn everything near them into silhouettes.
* Nothing moving in frame: no people, pets, or fans running.
* Avoid pointing the camera straight at the full-length mirror. It shows you, moving, and its reflection looks like a second room.

## 2. Phone settings (iPhone 15 Pro)

* Settings > Camera > Formats: **Most Compatible** (H.264).
* Settings > Camera > Record Video: **1080p at 30 fps**, **HDR Video off**, Action Mode off.
* Settings > Camera: **Macro Control on**, then keep macro off in the camera app.
* Settings > Camera: **Grid on**.
* Plain Video mode and the **same lens and orientation for every video**. In a small room use the **0.5x lens in landscape**: it keeps the floor and most of the room in view. In a larger space or a corridor, 1x works too. Landscape is also cheaper: portrait frames are padded to a square, which costs about 75% more GPU memory per frame. Keep Lens Correction on.
* Long press a mid-distance wall until "AE/AF LOCK" shows, then record.

## 3. Moving the phone (the part that matters)

* **Same height for every video.** Pick chest height, measure it once with a tape (floor to phone) and use that number as `--camera-height`. The test clips were held at different heights, which corrupts the scale estimate.
* **Slow.** A full loop of the room should take 45 to 60 s, not 30. Turns are where blur happens: turn at about half the speed that feels natural.
* **Step sideways, don't just pivot.** For each area of the room, take two or three small steps sideways while looking at it, then turn to the next area. Depth comes from the camera moving. Your room is small, so short steps along the free strip of floor between the bed and the desk are enough.
* **Stay at least 1 m from surfaces** and keep some context in frame. A wardrobe door filling the whole frame (test clip at 33 s) has nothing to match.
* Tilt slightly down so the **floor is visible** in most frames.

## 4. Choose the changes

Good objects are shoebox size or bigger with a clear shape, standing on the floor or a desk. In this room:

* **Move:** the desk chair about 1 m, and turn it. Or the tower fan.
* **Remove:** the boots by the desk, or the helmet from the windowsill.
* **Add on the floor:** the backpack, in the open floor space. A new obstacle in a robot's path is the most relevant case.
* **Add on the desk:** a bottle or a box.

Avoid: things on the bright windowsill, flat things (paper, cables), anything glass or glossy black. Touch nothing else.

## 5. The recording plan: three videos

1. **before.mov**: a slow loop of the room, path A (along the bed side).
2. **before2.mov**: another loop with **no changes**, path B (along the desk side, or a diagonal).
3. Make the changes. Write them down.
4. **after.mov**: path B again, in the same walking direction, making sure to see every changed spot, including the old and new position of anything moved.

Also leave one corner that `before` sees and `after` does not. The system should mark it *not verified* instead of reporting it as removed.

**Why the extra video?** `before` vs `before2` is a null test: nothing changed, only the viewpoint. The system should report nothing. It is the most convincing evidence that detections come from real changes, not viewpoint differences, which is exactly what the brief asks for.

## 6. Ground truth

Write down each change (what, moved / added / removed, roughly where), measure one object (the desk length) to check the scale estimate, and note the phone height.

## 7. Transfer

Use **AirDrop, a USB cable or iCloud Drive** and keep the original files. The test clips arrived as 1024x576 at about 1.7 Mbit/s, which means something re-compressed them on the way. Record two takes of each video in case one is blurry.
