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
    # Medieval Era
    "castle": {
        "name": "Castle", "prod_cost": 130, "requires_tech": "feudalism",
        "effects": {"gold_per_turn": 1, "culture_per_turn": 3},
        "maintenance": 2,
    },
    "cathedral": {
        "name": "Cathedral", "prod_cost": 120, "requires_tech": "theology",
        "effects": {"culture_per_turn": 4, "food_per_turn": 1},
        "maintenance": 2,
    },
    "university": {
        "name": "University", "prod_cost": 160, "requires_tech": "education",
        "effects": {"science_per_turn": 4},
        "maintenance": 2,
    },
    "bank": {
        "name": "Bank", "prod_cost": 140, "requires_tech": "civil_service",
        "effects": {"gold_per_turn": 3},
        "maintenance": 0,
    },
}
