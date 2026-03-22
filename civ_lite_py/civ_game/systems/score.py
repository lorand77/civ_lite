from civ_game.data.buildings import BUILDING_DEFS
from civ_game.data.units import UNIT_DEFS


def compute_score(civ, game) -> int:
    if civ.is_eliminated:
        return 0

    score = 0
    score += len(civ.cities) * 50
    score += sum(c.population for c in civ.cities) * 20
    score += sum(UNIT_DEFS[u.unit_type]["strength"] for u in civ.units if not u.is_civilian) * 3
    score += len(civ.techs_researched) * 20
    score += sum(1 for t in game.tiles.values() if t.owner == civ.player_index)
    score += civ.gold // 10

    for city in civ.cities:
        for b_key in city.buildings:
            defn = BUILDING_DEFS[b_key]
            effects = defn.get("effects", {})
            score += effects.get("food_per_turn",    0) * 4
            score += effects.get("prod_per_turn",    0) * 5
            score += effects.get("gold_per_turn",    0) * 3
            score += effects.get("science_per_turn", 0) * 6
            score += effects.get("culture_per_turn", 0) * 2
            score += defn.get("defense", 0) * 8

    return score
