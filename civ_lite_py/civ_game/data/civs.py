from civ_game.data.units import UNIT_DEFS

CIV_TRAITS = {
    0: {  # Rome
        "name": "Rome",
        "all_units_strength_bonus": 0.07,
        "attacking_strength_bonus": 0.0,
        "city_culture_bonus": 0,
        "science_bonus": 0.0,
        "special_units": {
            "swordsman": {"strength_bonus": 0.30},
            "catapult":  {"strength_bonus": 0.20},
        },
        "special_buildings": {},
    },
    1: {  # Greece
        "name": "Greece",
        "all_units_strength_bonus": 0.0,
        "attacking_strength_bonus": 0.0,
        "city_culture_bonus": 1,
        "science_bonus": 0.0,
        "special_units": {
            "spearman": {"strength_bonus": 0.20},
            "horseman": {"strength_bonus": 0.20},
        },
        "special_buildings": {},
    },
    2: {  # The Huns
        "name": "The Huns",
        "all_units_strength_bonus": 0.0,
        "attacking_strength_bonus": 0.10,
        "city_culture_bonus": 0,
        "science_bonus": 0.0,
        "special_units": {
            "spearman": {"bonus_vs_city_add": 3.0},
            "horseman": {"movement_bonus": 1},
        },
        "special_buildings": {},
    },
    3: {  # Babylon
        "name": "Babylon",
        "all_units_strength_bonus": 0.0,
        "attacking_strength_bonus": 0.0,
        "city_culture_bonus": 0,
        "science_bonus": 0.10,
        "special_units": {
            "archer": {"strength_bonus": 0.30},
        },
        "special_buildings": {
            "library": {"science_per_turn_add": 6},
        },
    },
}


def is_special_unit(player_index, unit_type):
    """Return True if unit_type is a special unit for the given civ."""
    traits = CIV_TRAITS.get(player_index, {})
    return unit_type in traits.get("special_units", {})


def is_special_building(player_index, building_key):
    """Return True if building_key is a special building for the given civ."""
    traits = CIV_TRAITS.get(player_index, {})
    return building_key in traits.get("special_buildings", {})


def get_effective_base_strength(player_index, unit_type):
    """Return the unit's base strength including civ bonuses (no terrain/HP/etc)."""
    base = UNIT_DEFS[unit_type]["strength"]
    traits = CIV_TRAITS.get(player_index, {})
    su = traits.get("special_units", {}).get(unit_type, {})
    base *= (1 + su.get("strength_bonus", 0.0))
    base *= (1 + traits.get("all_units_strength_bonus", 0.0))
    return base


def get_unit_move_bonus(player_index, unit_type):
    """Return extra movement points for this civ/unit combo (0 for most)."""
    traits = CIV_TRAITS.get(player_index, {})
    su = traits.get("special_units", {}).get(unit_type, {})
    return su.get("movement_bonus", 0)
