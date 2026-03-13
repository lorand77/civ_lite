import numpy as np
from dataclasses import dataclass, field
from civ_game.map.hex_grid import offset_to_axial
from civ_game.map.terrain import RESOURCES


@dataclass
class Tile:
    q: int
    r: int
    terrain: str           # "grassland"|"plains"|"hills"|"forest"|"ocean"
    resource: str | None = None
    improvement: str | None = None
    improvement_turns_left: int = 0
    city: object = None
    unit: object = None
    civilian: object = None
    owner: int | None = None


def _box_blur(arr, passes=4):
    """Smooth a 2D numpy array with repeated 3×3 mean blur."""
    result = arr.copy()
    for _ in range(passes):
        pad = np.pad(result, 1, mode="edge")
        result = (
            pad[:-2, :-2] + pad[:-2, 1:-1] + pad[:-2, 2:] +
            pad[1:-1, :-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:] +
            pad[2:, :-2] + pad[2:, 1:-1] + pad[2:, 2:]
        ) / 9.0
    return result


def generate_map(cols, rows, seed=None):
    """Return dict {(q, r): Tile} for the full map."""
    rng = np.random.default_rng(seed)

    # --- Elevation noise ---
    noise = rng.random((rows, cols)).astype(float)
    noise = _box_blur(noise, passes=2)  # light smoothing keeps local variation

    # Edge penalty: 0 in interior → 1 at corners; subtracted from noise
    row_idx = np.arange(rows)
    col_idx = np.arange(cols)
    edge_r = 1.0 - np.clip(np.minimum(row_idx, rows - 1 - row_idx) / (rows * 0.18), 0.0, 1.0)
    edge_c = 1.0 - np.clip(np.minimum(col_idx, cols - 1 - col_idx) / (cols * 0.12), 0.0, 1.0)
    edge_penalty = np.maximum(np.outer(edge_r, np.ones(cols)),
                              np.outer(np.ones(rows), edge_c))

    elev = np.clip(noise - edge_penalty * 0.75, 0.0, 1.0)

    # --- Assign terrain ---
    tiles = {}
    terrain_grid = {}  # (col, row) → terrain, for resource placement

    for row in range(rows):
        for col in range(cols):
            q, r = offset_to_axial(col, row)
            e = elev[row, col]
            if e > 0.54:
                terrain = "hills"
            elif e > 0.46:
                terrain = "forest"
            elif e > 0.16:
                terrain = "plains" if rng.random() < 0.4 else "grassland"
            else:
                terrain = "ocean"

            # Hard-force edges to ocean
            if row == 0 or row == rows - 1 or col == 0 or col == cols - 1:
                terrain = "ocean"

            tiles[(q, r)] = Tile(q=q, r=r, terrain=terrain)
            terrain_grid[(col, row)] = terrain

    # --- Scatter resources ---
    _place_resources(tiles, terrain_grid, cols, rows, rng)

    return tiles


def _place_resources(tiles, terrain_grid, cols, rows, rng):
    """Randomly place resources on valid terrain tiles."""
    # Collect candidate positions per terrain type
    hills_pos    = [(col, row) for (col, row), t in terrain_grid.items() if t == "hills"]
    plains_pos   = [(col, row) for (col, row), t in terrain_grid.items() if t == "plains"]
    grass_pos    = [(col, row) for (col, row), t in terrain_grid.items() if t == "grassland"]
    forest_pos   = [(col, row) for (col, row), t in terrain_grid.items() if t == "forest"]
    plains_grass = plains_pos + grass_pos
    forest_hills = forest_pos + hills_pos

    def place(positions, resource, count):
        if not positions:
            return
        chosen = rng.choice(len(positions), size=min(count, len(positions)), replace=False)
        for idx in chosen:
            col, row = positions[int(idx)]
            q, r = offset_to_axial(col, row)
            if (q, r) in tiles and tiles[(q, r)].resource is None:
                tiles[(q, r)].resource = resource

    place(hills_pos,    "iron",     8)
    place(plains_grass, "horses",   6)
    place(plains_grass, "gold",     5)
    place(hills_pos,    "silver",   4)
    place(forest_hills, "diamonds", 3)
