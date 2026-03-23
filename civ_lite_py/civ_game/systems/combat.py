import math
from civ_game.data.units import UNIT_DEFS
from civ_game.data.buildings import BUILDING_DEFS
from civ_game.data.civs import CIV_TRAITS
from civ_game.map.terrain import TERRAIN_DEFENSE_BONUS


def calc_damage(attacker_str, defender_str):
    """Returns integer damage dealt based on strength difference."""
    diff = attacker_str - defender_str
    damage = 30 * math.exp(0.04 * diff)
    return max(1, min(50, int(damage)))


def effective_strength(unit, tile, vs_unit_type=None, owner=None):
    """Adjust unit combat strength for terrain, fortification, HP, unit bonuses, and civ bonuses."""
    base = UNIT_DEFS[unit.unit_type]["strength"]

    # Civ bonuses (special unit + civ-wide)
    if owner is not None:
        traits = CIV_TRAITS.get(owner, {})
        su = traits.get("special_units", {}).get(unit.unit_type, {})
        base *= (1 + su.get("strength_bonus", 0.0))

    terrain_bonus = TERRAIN_DEFENSE_BONUS.get(tile.terrain, 0)
    fortify_bonus = unit.fortify_bonus
    hp_max = UNIT_DEFS[unit.unit_type]["hp_max"]
    hp_modifier = 0.5 + 0.5 * (unit.hp / hp_max)   # 1.0 at full HP, 0.5 at 0 HP
    unit_bonus = UNIT_DEFS[unit.unit_type].get("bonus_vs", {}).get(vs_unit_type, 0.0)
    result = base * (1 + terrain_bonus + fortify_bonus + unit_bonus) * hp_modifier

    # Civ-wide strength bonus (e.g. Rome +7%)
    if owner is not None:
        result *= (1 + traits.get("all_units_strength_bonus", 0.0))

    return result


def city_combat_strength(city) -> float:
    """Fixed city defensive strength: base + population bonus + building defense bonus."""
    base = 5
    pop_bonus = city.population * 2
    building_bonus = sum(BUILDING_DEFS[b].get("defense", 0) for b in city.buildings)
    return base + pop_bonus + building_bonus


def melee_attack(attacker, defender, attacker_tile, defender_tile):
    """Both units exchange damage. Returns (attacker_dmg, defender_dmg)."""
    a_str = effective_strength(attacker, attacker_tile, vs_unit_type=defender.unit_type, owner=attacker.owner)
    d_str = effective_strength(defender, defender_tile, vs_unit_type=attacker.unit_type, owner=defender.owner)
    # Apply attack-only bonus (e.g. Huns +10% attacking strength)
    a_traits = CIV_TRAITS.get(attacker.owner, {})
    a_str *= (1 + a_traits.get("attacking_strength_bonus", 0.0))
    attacker_dmg = calc_damage(d_str, a_str)   # defender hits back
    defender_dmg = calc_damage(a_str, d_str)   # attacker hits defender
    attacker.hp = max(0, attacker.hp - attacker_dmg)
    defender.hp = max(0, defender.hp - defender_dmg)
    return attacker_dmg, defender_dmg


def ranged_attack(attacker, defender, defender_tile):
    """Only defender takes damage (no retaliation)."""
    a_str = UNIT_DEFS[attacker.unit_type].get(
        "ranged_strength", UNIT_DEFS[attacker.unit_type]["strength"]
    )
    # Apply civ bonuses to ranged attacker
    a_traits = CIV_TRAITS.get(attacker.owner, {})
    su = a_traits.get("special_units", {}).get(attacker.unit_type, {})
    a_str *= (1 + su.get("strength_bonus", 0.0))
    a_str *= (1 + a_traits.get("all_units_strength_bonus", 0.0))
    a_str *= (1 + a_traits.get("attacking_strength_bonus", 0.0))
    d_str = effective_strength(defender, defender_tile, owner=defender.owner)
    defender_dmg = calc_damage(a_str, d_str)
    defender.hp = max(0, defender.hp - defender_dmg)
    return defender_dmg


def bombard_city(attacker, city):
    """Attack city HP directly. Returns (city_dmg, attacker_dmg).
    Melee attackers take retaliation damage from the city; ranged do not."""
    defn = UNIT_DEFS[attacker.unit_type]
    a_str = defn.get("ranged_strength", defn["strength"])

    # Apply civ bonuses
    a_traits = CIV_TRAITS.get(attacker.owner, {})
    su = a_traits.get("special_units", {}).get(attacker.unit_type, {})
    a_str *= (1 + su.get("strength_bonus", 0.0))
    a_str *= (1 + a_traits.get("all_units_strength_bonus", 0.0))
    a_str *= (1 + a_traits.get("attacking_strength_bonus", 0.0))

    city_bonus = defn.get("bonus_vs_city", 0.0)
    city_bonus += su.get("bonus_vs_city_add", 0.0)  # e.g. Huns spearman +300%
    a_str = a_str * (1 + city_bonus)
    city_dmg = max(1, min(20, int(a_str * 0.4)))
    city.hp = max(0, city.hp - city_dmg)

    attacker_dmg = 0
    if defn["type"] == "melee":
        c_str = city_combat_strength(city)
        hp_max = defn["hp_max"]
        hp_modifier = 0.5 + 0.5 * (attacker.hp / hp_max)
        a_eff_str = defn["strength"]
        a_eff_str *= (1 + su.get("strength_bonus", 0.0))
        a_eff_str *= (1 + a_traits.get("all_units_strength_bonus", 0.0))
        a_eff_str *= hp_modifier
        attacker_dmg = calc_damage(c_str, a_eff_str)
        attacker.hp = max(0, attacker.hp - attacker_dmg)

    return city_dmg, attacker_dmg
