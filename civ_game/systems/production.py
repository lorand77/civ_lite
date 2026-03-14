from civ_game.data.units import UNIT_DEFS
from civ_game.data.buildings import BUILDING_DEFS


def get_item_cost(item_key):
    if item_key in UNIT_DEFS:
        return UNIT_DEFS[item_key]["prod_cost"]
    if item_key in BUILDING_DEFS:
        return BUILDING_DEFS[item_key]["prod_cost"]
    return 9999


def process_production(city, civ, game):
    """Advance production queue by city's prod yield. Complete items if ready."""
    if not city.production_queue:
        return

    from civ_game.systems.yields import compute_city_yields
    yields = compute_city_yields(city, game.tiles, civ)
    city.production_progress += yields["prod"]

    item_key = city.production_queue[0]
    cost = get_item_cost(item_key)

    if city.production_progress >= cost:
        city.production_progress -= cost
        _complete_item(city, civ, game, item_key)
        city.production_queue.pop(0)


def _complete_item(city, civ, game, item_key):
    if item_key in BUILDING_DEFS:
        if item_key not in city.buildings:
            city.buildings.append(item_key)
        return

    if item_key in UNIT_DEFS:
        from civ_game.entities.unit import Unit
        defn = UNIT_DEFS[item_key]
        unit = Unit(
            unit_type=item_key,
            owner=civ.player_index,
            q=city.q, r=city.r,
            hp=defn["hp_max"],
            moves_left=defn["moves"],
        )
        # Place on city tile (or nearest free tile)
        tile = game.tiles.get((city.q, city.r))
        placed = False
        if tile:
            if defn["type"] == "civilian" and tile.civilian is None:
                tile.civilian = unit
                placed = True
            elif defn["type"] != "civilian" and tile.unit is None:
                tile.unit = unit
                placed = True

        if not placed:
            # Try adjacent tiles
            from civ_game.map.hex_grid import hex_neighbors
            from civ_game.map.terrain import TERRAIN_PASSABLE
            for nq, nr in hex_neighbors(city.q, city.r):
                t = game.tiles.get((nq, nr))
                if not t or not TERRAIN_PASSABLE[t.terrain]:
                    continue
                if defn["type"] == "civilian" and t.civilian is None:
                    unit.q, unit.r = nq, nr
                    t.civilian = unit
                    placed = True
                    break
                elif defn["type"] != "civilian" and t.unit is None:
                    unit.q, unit.r = nq, nr
                    t.unit = unit
                    placed = True
                    break

        if placed:
            civ.units.append(unit)
