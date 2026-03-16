# Terrain constants and yield definitions

TERRAIN_YIELDS = {
    "grassland": {"food": 2, "prod": 0, "gold": 0},
    "plains":    {"food": 1, "prod": 1, "gold": 0},
    "hills":     {"food": 0, "prod": 2, "gold": 0},
    "forest":    {"food": 1, "prod": 1, "gold": 0},
    "ocean":     {"food": 0, "prod": 0, "gold": 0},
}

TERRAIN_DEFENSE_BONUS = {
    "grassland": 0,
    "plains":    0,
    "hills":     0.25,
    "forest":    0.25,
    "ocean":     0,
}

TERRAIN_PASSABLE = {
    "grassland": True,
    "plains":    True,
    "hills":     True,
    "forest":    True,
    "ocean":     False,
}

TERRAIN_MOVE_COST = {
    "grassland": 1,
    "plains":    1,
    "hills":     2,
    "forest":    2,
    "ocean":     99,  # impassable
}

# Colors (R, G, B)
TERRAIN_COLORS = {
    "grassland": (106, 168, 79),
    "plains":    (182, 215, 168),
    "hills":     (153, 102, 51),
    "forest":    (39, 78, 19),
    "ocean":     (30, 90, 180),
}

# Resources
RESOURCES = {
    "iron": {
        "type": "strategic",
        "valid_terrain": ["hills"],
        "yield_bonus": {"prod": 1},
        "requires_tech": "mining",
        "enables_unit": "swordsman",
    },
    "horses": {
        "type": "strategic",
        "valid_terrain": ["plains", "grassland"],
        "yield_bonus": {"food": 1},
        "requires_tech": "animal_husbandry",
        "enables_unit": "horseman",
    },
    "gold": {
        "type": "luxury",
        "valid_terrain": ["plains", "grassland"],
        "yield_bonus": {"gold": 3},
        "requires_tech": None,
    },
    "silver": {
        "type": "luxury",
        "valid_terrain": ["hills"],
        "yield_bonus": {"gold": 2},
        "requires_tech": "mining",
    },
    "diamonds": {
        "type": "luxury",
        "valid_terrain": ["forest", "hills"],
        "yield_bonus": {"gold": 4},
        "requires_tech": None,
    },
}

RESOURCE_COLORS = {
    "iron":     (160, 160, 160),
    "horses":   (200, 160, 100),
    "gold":     (255, 215, 0),
    "silver":   (192, 192, 192),
    "diamonds": (180, 230, 255),
}

# Resources always visible (requires_tech is None)
ALWAYS_VISIBLE_RESOURCES = {k for k, v in RESOURCES.items() if v["requires_tech"] is None}
