BUILDING_DEFS = {
    "palace": {
        "name": "Palace", "prod_cost": 0, "requires_tech": None,
        "effects": {"prod_per_turn": 3, "gold_per_turn": 3, "culture_per_turn": 2},
        "maintenance": 0,
    },
    "monument": {
        "name": "Monument", "prod_cost": 60, "requires_tech": None,
        "effects": {"culture_per_turn": 2}, "maintenance": 0,
    },
    "granary": {
        "name": "Granary", "prod_cost": 80, "requires_tech": "pottery",
        "effects": {"food_per_turn": 2}, "maintenance": 1,
    },
    "barracks": {
        "name": "Barracks", "prod_cost": 80, "requires_tech": "bronze_working",
        "effects": {"new_unit_xp": 15}, "maintenance": 1,
    },
    "library": {
        "name": "Library", "prod_cost": 100, "requires_tech": "writing",
        "effects": {"science_per_turn": 2}, "maintenance": 1,
    },
    "market": {
        "name": "Market", "prod_cost": 100, "requires_tech": "currency",
        "effects": {"gold_per_turn": 2}, "maintenance": 0,
    },
    "forge": {
        "name": "Forge", "prod_cost": 120, "requires_tech": "iron_working",
        "effects": {"prod_bonus_hills": 1}, "maintenance": 1,
    },
}
