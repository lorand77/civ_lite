IMPROVEMENT_DEFS = {
    "farm": {
        "name": "Farm", "build_turns": 3,
        "valid_terrain": ["grassland", "plains"],
        "requires_tech": None,
        "yield_bonus": {"food": 1}, "label": "f",
    },
    "mine": {
        "name": "Mine", "build_turns": 3,
        "valid_terrain": ["hills", "forest"],
        "requires_tech": "mining",
        "yield_bonus": {"prod": 1}, "label": "m",
    },
    "pasture": {
        "name": "Pasture", "build_turns": 3,
        "valid_terrain": ["grassland", "plains"],
        "requires_tech": "animal_husbandry",
        "yield_bonus": {"prod": 1}, "label": "p",
    },
}
