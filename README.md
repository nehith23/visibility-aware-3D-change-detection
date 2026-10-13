# What changed in the room?

Give it two phone videos of the same room, taken before and after you move some things. It builds one 3D model from both and reports what was moved, added or removed, with a position, a size and a confidence score.

## Example

I recorded my room, then moved a box, moved a backpack, added a duffel bag and removed a water jug.

![Keyframes from the before and after videos](examples/room_A/inputs.jpg)

| change I made | what it reported | correct? |
|---|---|---|
| box moved from the chair seat to the floor | moved 0.4 m (confidence 0.76) | yes, but named "laundry basket" |
| duffel bag added on the bed | added (0.71) | right place, named "bed" |
| backpack moved 1.7 m, bed to chair | removed from the bed (0.55); added on the chair (0.45, low) | both ends found, but not linked as one move |
| water jug removed | found, but linked to an empty spot as a move (0.44, low) | partly |

![Top-down map: blue = moved, orange = removed, green = added, dotted = low confidence](examples/room_A/topdown.png)

The backpack ended up where the box had been, so most of it filled space that was already occupied in the first video. Only a thin slice of it registered as new, which is why the two ends weren't linked. Names come from CLIP looking at one image crop, and the crop of the duffel bag is mostly bed.

The shared 3D model of both videos, with the changes marked:

![3D view of the room](examples/room_A/scene.png)

Interactive version: [room](https://nehith23.github.io/visibility-aware-3D-change-detection/examples/room_A/scene.html), [corridor](https://nehith23.github.io/visibility-aware-3D-change-detection/examples/corridor_right/scene.html).

## Run it

Try the shipped example (no GPU needed; about a minute, plus a one-time CLIP download):

```
pip install -r requirements.txt
python scripts/try_example.py
```

This recomputes the room example above into `results/room_A/`.

On your own videos (tested on Windows 11, RTX 4070 laptop GPU with 8 GB, Python 3.12):

```
powershell -ExecutionPolicy Bypass -File scripts\run_all_windows.ps1 -Height 1.20 -Pairs "mine=data\before.mov,data\after.mov"
```

The first run sets up a virtual environment, PyTorch and VGGT. `-Height` is how high you held the phone, in metres. Results go to `results\mine\`. Linux, all commands, and how to rerun everything from the original videos: [docs/SETUP.md](docs/SETUP.md). How to film: [docs/RECORDING.md](docs/RECORDING.md).

## How it works

[VGGT](https://github.com/facebookresearch/vggt) reconstructs keyframes from both videos together, so they share one 3D frame. The floor and the phone height give real-world scale. For each 3D point from one video, I check whether any camera in the other video saw through that spot. If it did, the point is gone. If the spot was hidden or off screen, it is marked "not verified" rather than changed. Gone points are grouped into objects, likely alignment errors are filtered out, and each object gets a confidence score from its evidence. CLIP names the objects, and a removal and an addition that look alike are linked as a move.

## Design choices

* **One joint reconstruction instead of two plus registration.** Both videos go through VGGT together, so there is no separate alignment step to fail, and it does not depend on feature matching, which struggles on blank walls. Trade-off: GPU memory. An 8 GB card fits only 25 to 45 frames at once, depending on orientation, so I split the frames into passes linked by shared anchor frames.
* **Evidence of empty space, not distance between point clouds.** A spot only counts as changed if the other video saw through it. This is what separates real changes from viewpoint, occlusion and missing coverage. Trade-off: it depends on good alignment, so I added local re-alignment and filters for typical misalignment shapes.
* **Scale from the phone height.** No extra sensor or marker is needed. Trade-off: a wrong height scales every size and distance.
* **A confidence score instead of a hard cut.** Weak candidates are listed as low confidence rather than dropped. Trade-off: the score is hand-tuned, so I froze it before analysing the room recordings.
* **CLIP for names.** It works on any object with no training. Trade-off: it names whatever fills the crop, often the surroundings.

More detail, including what failed: [docs/DESIGN.md](docs/DESIGN.md).

## Results

| scene | comparisons | result |
|---|---|---|
| room (analysed only after the code was frozen) | 3 with changes, 1 with none | 9 confident detections, all at real changes; 2 link the wrong objects; nothing confident when nothing changed |
| corridor (used to develop the method) | 3 with changes, 1 with none | 8 of 9 changes found; 2 false alarms |
| synthetic room | 1 | 4 of 4 changes found, positions within 1 cm |

Compared with a plain nearest-point diff on the same data, the see-through check cuts false detections by about 90% ([examples/ablation.md](examples/ablation.md)). Every comparison: [docs/RESULTS.md](docs/RESULTS.md).

Limitations:

* When two objects change in the same spot, it can link the wrong ones.
* Object names are often wrong; positions and sizes are more reliable.
* Walking in opposite directions in the two videos aligns them less precisely, and door frames can show up as false changes.
* The confidence score is hand-tuned, and only one room was held out for testing.
* VGGT weights are non-commercial.

## Data

All eight videos (room and corridor) and the remaining reconstructions are in the [latest release](../../releases/latest). Recording details are in [docs/RESULTS.md](docs/RESULTS.md).

## License

Code: [MIT](LICENSE). Videos and outputs: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
