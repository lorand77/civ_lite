from __future__ import annotations
from dataclasses import dataclass, field

from civ_game.map.hex_grid import hex_neighbors
from civ_game.map.terrain import TERRAIN_YIELDS, RESOURCES
from civ_game.entities.improvement import IMPROVEMENT_DEFS


@dataclass
class City:
    name: str
    q: int
    r: int
    owner: int
    population: int = 1
    food_stored: int = 0
    hp: int = 50
    buildings: list = field(default_factory=list)
    production_queue: list = field(default_factory=list)
    production_progress: int = 0
    worked_tiles: list = field(default_factory=list)
    is_original_capital: bool = False
    culture_stored: int = 0

    @property
    def food_growth_threshold(self):
        return 15 + 6 * self.population


def auto_assign_worked_tiles(city: City, tiles: dict):
    """Assign worked tiles based on population (best-yield neighbours first)."""
    city_pos = (city.q, city.r)
    city.worked_tiles = [city_pos]

    candidates = []
    for nq, nr in hex_neighbors(city.q, city.r):
        tile = tiles.get((nq, nr))
        if not tile or tile.terrain == "ocean":
            continue
        y = TERRAIN_YIELDS[tile.terrain]
        score = y["food"] * 1.1 + y["prod"] + y["gold"]

        if tile.resource and tile.resource in RESOURCES:
            b = RESOURCES[tile.resource]["yield_bonus"]
            score += b.get("food", 0) * 1.1 + b.get("prod", 0) + b.get("gold", 0)

        if tile.improvement and tile.improvement in IMPROVEMENT_DEFS:
            b = IMPROVEMENT_DEFS[tile.improvement]["yield_bonus"]
            score += b.get("food", 0) * 1.1 + b.get("prod", 0) + b.get("gold", 0)

        candidates.append(((nq, nr), score))

    candidates.sort(key=lambda x: -x[1])
    for i in range(min(city.population, len(candidates))):
        city.worked_tiles.append(candidates[i][0])
