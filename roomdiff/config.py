"""All tunable numbers in one place. Distances are metres in the room frame."""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Config:
    # --- frame sampling / reconstruction ---------------------------------
    frames_per_video: int = 0          # 0 = pick automatically from GPU memory
    max_side: int = 0                  # 0 = 518 (VGGT native), or 392 on small GPUs
    conf_drop_percentile: float = 25.0  # drop the least confident pixels

    # --- room frame ------------------------------------------------------
    camera_height: float = 1.35        # typical handheld phone height above floor
    scale: float = 0.0                 # 0 = estimate from camera height

    # --- point clouds ----------------------------------------------------
    pixel_stride: int = 2              # back-project every n-th pixel
    voxel: float = 0.02                # point cloud resolution
    flying_pixel_ratio: float = 0.04   # drop pixels on depth discontinuities
    min_self_support: int = 2          # frames of its own scan that must agree
    max_depth: float = 4.5             # ignore anything further away (e.g. outside a window)

    # --- visibility test -------------------------------------------------
    depth_tol_abs: float = 0.06
    depth_tol_rel: float = 0.04        # tolerance = max(abs, rel * depth)
    window: int = 5                    # neighbourhood for robust depth lookup
    grazing_min_cos: float = 0.5       # tolerance grows as 1/cos(incidence), at most 2x
    grazing_min_cos_floor: float = 0.2 # ... at most 5x on horizontal surfaces
    floor_band: float = 0.06           # points this close to the floor are never 'gone'
    min_height: float = 0.08           # changes lower than this (mats, paper) are floor noise
    min_votes: int = 2                 # frames that must see "through" a point
    vanish_ratio: float = 0.7          # share of evidence that must say "gone"

    # --- clustering / objects -------------------------------------------
    cluster_eps: float = 0.06
    cluster_min_samples: int = 6
    min_cluster_points: int = 25
    min_cluster_extent: float = 0.07
    max_sheet_area: float = 1.0        # large flat clusters = alignment artefacts
    sheet_max_thickness: float = 0.03  # 3rd principal spread of a wall/floor slice
    sheet_max_flatness: float = 0.2    # ... or 3rd/2nd spread ratio for a thicker slab
    sheet_min_extent: float = 0.12     # product of the first two spreads (~1.4 m2 of surface)
    match_cost: float = 0.85           # max cost to pair a removal with an addition
    merge_gap: float = 0.10            # merge clusters closer than this (one object split by noise)
    move_max_size_ratio: float = 2.0   # a moved object keeps its size within this factor
    move_max_color: float = 30.0       # ... and its mean Lab colour within this distance
    move_min_points: int = 60          # tiny fragments are never paired as moves
    pole_max_width: float = 0.06       # thinner than this and much taller than long = pole,
    pole_aspect: float = 3.0           # below depth resolution (seat posts, chair legs)
    line_max_spread: float = 0.018     # 2nd principal spread under this = tube or cable
    local_radius: float = 0.6          # neighbourhood re-registered around each candidate
    local_keep_gone: float = 0.6       # share of points still "gone" after local re-registration
    edge_max_excess: float = 0.25      # depth-edge share above what a solid object that size has
    min_report_points: int = 120       # smaller than ~0.05 m2 of visible surface is not "meaningful"
    confident_score: float = 0.5       # below this a change is listed as "possible"
    appearance_delta_e: float = 18.0   # Lab distance that counts as "looks different"
    appearance_min_changed: float = 0.45  # share of see-through views that must look different

    # --- semantics -------------------------------------------------------
    use_clip: bool = True
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"

    def to_dict(self) -> dict:
        return asdict(self)
