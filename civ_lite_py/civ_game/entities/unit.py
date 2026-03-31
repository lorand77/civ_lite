from __future__ import annotations
from dataclasses import dataclass
from collections import deque

from civ_game.map.hex_grid import hex_neighbors, hex_distance
from civ_game.map.terrain import TERRAIN_PASSABLE, TERRAIN_MOVE_COST
from civ_game.data.units import UNIT_DEFS


@dataclass
class Unit:
    unit_type: str          # key into UNIT_DEFS
    owner: int              # player index 0-3
    q: int
    r: int
    hp: int                 # current HP
    moves_left: int
    fortified: bool = False
    fortify_bonus: float = 0.0
    healing: bool = False
    xp: int = 0
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


def get_reachable_tiles(unit: Unit, tiles: dict, turn: int = 99) -> dict:
    """
    BFS — returns dict of {(q,r): move_cost} for all tiles the unit can
    move to this turn.  Using a dict means callers can still use `in` and
    iterate over keys exactly like a set, but also look up the actual cost.
    """
    start = (unit.q, unit.r)
    max_moves = unit.moves_left
    visited = {start: 0}
    queue = deque([(start, 0)])
    reachable = {}          # (q,r) -> cost to reach

    while queue:
        (q, r), used = queue.popleft()
        for nq, nr in hex_neighbors(q, r):
            tile = tiles.get((nq, nr))
            if not tile:
                continue
            if not TERRAIN_PASSABLE[tile.terrain]:
                continue
            cost = used + TERRAIN_MOVE_COST[tile.terrain]
            if cost > max_moves:
                continue
            if (nq, nr) in visited and visited[(nq, nr)] <= cost:
                continue
            visited[(nq, nr)] = cost

            if unit.is_civilian:
                # Any civilian blocks (friendly or enemy)
                if tile.civilian:
                    continue
                # Enemy military blocks civilian movement
                if tile.unit and tile.unit.owner != unit.owner:
                    continue
                reachable[(nq, nr)] = cost
                queue.append(((nq, nr), cost))
            else:
                # Military: friendly blocks
                if tile.unit and tile.unit.owner == unit.owner:
                    continue
                # Enemy military: attack target only, blocks movement
                if tile.unit and tile.unit.owner != unit.owner:
                    continue
                # Enemy city: blocks movement entirely
                if tile.city and tile.city.owner != unit.owner:
                    continue
                # Enemy civilian: can capture (move there) but can't pass through
                # Exception: settlers are untouchable on turn 1
                if tile.civilian and tile.civilian.owner != unit.owner:
                    if turn <= 1 and tile.civilian.unit_type == "settler":
                        continue
                    reachable[(nq, nr)] = cost
                    continue
                reachable[(nq, nr)] = cost
                queue.append(((nq, nr), cost))

    return reachable


def get_attackable_tiles(unit: Unit, tiles: dict) -> set:
    """Returns set of (q,r) the unit can attack from its current position."""
    if unit.is_civilian or unit.moves_left == 0:
        return set()

    defn = UNIT_DEFS[unit.unit_type]
    attack_range = defn.get("range", 1)  # 1 = melee, 2 = ranged

    targets = set()

    if attack_range == 1:
        # Melee: only adjacent tiles
        for nq, nr in hex_neighbors(unit.q, unit.r):
            tile = tiles.get((nq, nr))
            if not tile:
                continue
            if tile.unit and tile.unit.owner != unit.owner:
                targets.add((nq, nr))
            elif tile.city and tile.city.owner != unit.owner:
                targets.add((nq, nr))
    else:
        # Ranged: all tiles within attack_range
        for (tq, tr), tile in tiles.items():
            dist = hex_distance(unit.q, unit.r, tq, tr)
            if dist == 0 or dist > attack_range:
                continue
            if tile.unit and tile.unit.owner != unit.owner:
                targets.add((tq, tr))
            elif tile.city and tile.city.owner != unit.owner:
                targets.add((tq, tr))

    return targets
