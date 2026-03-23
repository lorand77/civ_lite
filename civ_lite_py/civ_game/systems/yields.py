from civ_game.map.terrain import TERRAIN_YIELDS, RESOURCES
from civ_game.entities.improvement import IMPROVEMENT_DEFS
from civ_game.data.buildings import BUILDING_DEFS
from civ_game.data.civs import CIV_TRAITS


def compute_city_yields(city, tiles, civ):
    """Return dict with food/prod/gold/science/culture totals for a city."""
    totals = {"food": 0, "prod": 0, "gold": 0, "science": 0, "culture": 0}

    for (q, r) in city.worked_tiles:
        tile = tiles.get((q, r))
        if not tile:
            continue

        t = TERRAIN_YIELDS[tile.terrain]
        totals["food"] += t["food"]
        totals["prod"] += t["prod"]
        totals["gold"] += t["gold"]

        # Resource bonus (visible if no tech required, or civ has the tech)
        if tile.resource:
            res = RESOURCES[tile.resource]
            req = res.get("requires_tech")
            if req is None or req in civ.techs_researched:
                for k, v in res["yield_bonus"].items():
                    totals[k] = totals.get(k, 0) + v

        # Improvement bonus
        if tile.improvement:
            imp = IMPROVEMENT_DEFS[tile.improvement]
            for k, v in imp["yield_bonus"].items():
                totals[k] = totals.get(k, 0) + v

        # Forge: +1 prod on hills tiles
        if tile.terrain == "hills" and "forge" in city.buildings:
            totals["prod"] += 1

    # Building bonuses and maintenance
    for b_key in city.buildings:
        b = BUILDING_DEFS[b_key]
        eff = b["effects"]
        totals["food"]    += eff.get("food_per_turn", 0)
        totals["prod"]    += eff.get("prod_per_turn", 0)
        totals["gold"]    += eff.get("gold_per_turn", 0)
        totals["science"] += eff.get("science_per_turn", 0)
        totals["culture"] += eff.get("culture_per_turn", 0)
        totals["gold"]    -= b.get("maintenance", 0)

    # Base science: 1 per city + 1 per citizen
    totals["science"] += 1 + city.population

    # Civ-specific yield bonuses
    traits = CIV_TRAITS.get(civ.player_index, {})

    # Greece: +1 culture per city per turn
    totals["culture"] += traits.get("city_culture_bonus", 0)

    # Special buildings (e.g. Babylon library +6 science)
    for b_key in city.buildings:
        sb = traits.get("special_buildings", {}).get(b_key, {})
        totals["science"] += sb.get("science_per_turn_add", 0)

    # Science multiplier (e.g. Babylon +10%)
    science_bonus = traits.get("science_bonus", 0.0)
    if science_bonus:
        totals["science"] = int(totals["science"] * (1 + science_bonus))

    return totals
