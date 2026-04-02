import math
from civ_game.data.units import UNIT_DEFS
from civ_game.data.buildings import BUILDING_DEFS
from civ_game.map.terrain import TERRAIN_DEFENSE_BONUS


def calc_damage(attacker_str, defender_str):
    """Returns integer damage dealt based on strength difference."""
    diff = attacker_str - defender_str
    damage = 30 * math.exp(0.04 * diff)
    return max(1, min(50, int(damage)))


def effective_strength(unit, tile, vs_unit_type=None):
    """Adjust unit combat strength for terrain, fortification, HP, and unit bonuses."""
    base = UNIT_DEFS[unit.unit_type]["strength"]
    terrain_bonus = TERRAIN_DEFENSE_BONUS.get(tile.terrain, 0)
    fortify_bonus = unit.fortify_bonus
    hp_max = UNIT_DEFS[unit.unit_type]["hp_max"]
    hp_modifier = 0.5 + 0.5 * (unit.hp / hp_max)   # 1.0 at full HP, 0.5 at 0 HP
    unit_bonus = UNIT_DEFS[unit.unit_type].get("bonus_vs", {}).get(vs_unit_type, 0.0)
    xp_bonus = getattr(unit, "xp", 0) / 100         # +1% strength per XP point
    return base * (1 + terrain_bonus + fortify_bonus + unit_bonus + xp_bonus) * hp_modifier


def city_combat_strength(city) -> float:
    """Fixed city defensive strength: base + population bonus + building defense bonus."""
    base = 5
    pop_bonus = city.population * 2
    building_bonus = sum(BUILDING_DEFS[b].get("defense", 0) for b in city.buildings)
    return base + pop_bonus + building_bonus


def melee_attack(attacker, defender, attacker_tile, defender_tile):
    """Both units exchange damage. Returns (attacker_dmg, defender_dmg)."""
    a_str = effective_strength(attacker, attacker_tile, vs_unit_type=defender.unit_type)
    d_str = effective_strength(defender, defender_tile, vs_unit_type=attacker.unit_type)
    attacker_dmg = calc_damage(d_str, a_str)   # defender hits back
    defender_dmg = calc_damage(a_str, d_str)   # attacker hits defender
    attacker.hp = max(0, attacker.hp - attacker_dmg)
    defender.hp = max(0, defender.hp - defender_dmg)
    return attacker_dmg, defender_dmg


def ranged_attack(attacker, defender, defender_tile, attacker_tile=None):
    """Only defender takes damage (no retaliation)."""
    defn = UNIT_DEFS[attacker.unit_type]
    if attacker_tile is not None:
        # Use effective_strength for the base bonuses, then swap in ranged_strength
        base_multiplier = effective_strength(attacker, attacker_tile) / defn["strength"]
        a_str = defn.get("ranged_strength", defn["strength"]) * base_multiplier
    else:
        a_str = defn.get("ranged_strength", defn["strength"])
    d_str = effective_strength(defender, defender_tile)
    defender_dmg = calc_damage(a_str, d_str)
    defender.hp = max(0, defender.hp - defender_dmg)
    return defender_dmg


def bombard_city(attacker, city, attacker_tile=None):
    """Attack city HP directly. Returns (city_dmg, attacker_dmg).
    Melee attackers take retaliation damage from the city; ranged do not."""
    defn = UNIT_DEFS[attacker.unit_type]
    city_bonus = defn.get("bonus_vs_city", 0.0)

    if attacker_tile is not None:
        base_multiplier = effective_strength(attacker, attacker_tile) / defn["strength"]
        a_str = defn.get("ranged_strength", defn["strength"]) * base_multiplier
    else:
        a_str = defn.get("ranged_strength", defn["strength"])

    a_str = a_str * (1 + city_bonus)
    city_dmg = max(1, min(20, int(a_str * 0.4)))
    city.hp = max(0, city.hp - city_dmg)

    attacker_dmg = 0
    if defn["type"] == "melee":
        c_str = city_combat_strength(city)
        a_eff_str = effective_strength(attacker, attacker_tile) if attacker_tile is not None \
                    else defn["strength"] * (0.5 + 0.5 * (attacker.hp / defn["hp_max"]))
        attacker_dmg = calc_damage(c_str, a_eff_str)
        attacker.hp = max(0, attacker.hp - attacker_dmg)

    return city_dmg, attacker_dmg
