# Recording the videos

What worked in my recordings, and what didn't. Run `python -m roomdiff check before.mov after.mov` on each take before using the GPU: it reports blur, gaps, blank-wall footage and whether the camera mostly turned on the spot.

## Phone settings (iPhone 15 Pro)

* 1080p at 30 fps, HDR video off. HDR footage also works; it is tone-mapped automatically.
* Same lens and orientation for every video. In a small room, use the 0.5x lens in landscape: it keeps most of the room and the floor in view. The corridor was filmed on 1x in portrait. Portrait costs more GPU memory, because frames are padded to a square.
* Lock exposure and focus on a mid-distance wall before recording.

## The room

* Same lighting in every video, curtains closed if daylight is changing.
* Clear thin, see-through clutter (bikes, cables, open shelving): it produces false changes.
* Cover mirrors, switch screens off or leave them static, and keep fans and people out of the shot.

## Moving the phone

* Hold the phone at the same height every time, and measure that height: it sets the real-world scale (`--camera-height`).
* Move slowly, about 45 to 60 s for a small room. Turn slowly; that is where blur happens.
* Step sideways rather than just turning on the spot. Depth needs the camera to move.
* Keep at least 1 m from surfaces, and tilt slightly down so the floor is in view.

## The changes

* Use objects about shoebox size or bigger. Flat things (paper, a doormat) are below what the system can detect.
* In the "after" video, film every changed spot, including both the old and new place of anything you moved. One of my corridor clips never filmed where the backpack went, so it could only report it as removed.
* Walking in opposite directions in "before" and "after" works, but the two line up less precisely; door frames then sometimes show up as false changes.

## Recording plan

1. `before_A`: the room, one path.
2. `before_B`: the room again, unchanged, a different path. Comparing it with `before_A` is a no-change test: anything reported there is a false alarm.
3. Make the changes and write them down. Measure one distance with a tape to check the scale.
4. `after_A` (and optionally `after_B`): the changed room.

Copy the files by cable, AirDrop or iCloud. Some messaging apps re-compress video, which loses detail.
