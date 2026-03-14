from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque

from civ_game.map.hex_grid import hex_neighbors
from civ_game.map.terrain import TERRAIN_PASSABLE
from civ_game.data.units import UNIT_DEFS


@dataclass
class Unit:
    unit_type: str          # key into UNIT_DEFS
    owner: int              # player index 0-3
    q: int
    r: int
    hp: int                 # current HP
    moves_left: int
    xp: int = 0
    fortified: bool = False
    fortify_bonus: float = 0.0
    building_improvement: str | None = None  # worker: improvement being built
    build_turns_left: int = 0

    @property
    def is_civilian(self):
        return UNIT_DEFS[self.unit_type]["type"] == "civilian"

    @property
    def label(self):
        return UNIT_DEFS[self.unit_type]["label"]

    @property
    def name(self):
        return UNIT_DEFS[self.unit_type]["name"]


def get_reachable_tiles(unit: Unit, tiles: dict) -> set:
    """BFS — returns set of (q,r) the unit can move to this turn."""
    start = (unit.q, unit.r)
    max_moves = unit.moves_left
    visited = {start: 0}
    queue = deque([(start, 0)])
    reachable = set()

    while queue:
        (q, r), used = queue.popleft()
        for nq, nr in hex_neighbors(q, r):
            tile = tiles.get((nq, nr))
            if not tile:
                continue
            if not TERRAIN_PASSABLE[tile.terrain]:
                continue
            cost = used + 1
            if cost > max_moves:
                continue
            if (nq, nr) in visited and visited[(nq, nr)] <= cost:
                continue
            visited[(nq, nr)] = cost

            # Can't end on a tile occupied by same-class friendly unit
            if unit.is_civilian:
                if tile.civilian and tile.civilian.owner == unit.owner:
                    continue  # blocked but keep BFS-ing through
            else:
                if tile.unit and tile.unit.owner == unit.owner:
                    continue

            reachable.add((nq, nr))
            queue.append(((nq, nr), cost))

    return reachable
