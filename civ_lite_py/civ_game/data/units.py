UNIT_DEFS = {
    "warrior": {
        "name": "Warrior", "type": "melee",
        "strength": 8, "moves": 2, "hp_max": 100, "prod_cost": 40,
        "requires_tech": None, "requires_resource": None, "label": "W",
    },
    "archer": {
        "name": "Archer", "type": "ranged",
        "strength": 5, "ranged_strength": 7, "range": 2,
        "moves": 2, "hp_max": 100, "prod_cost": 40,
        "requires_tech": "archery", "requires_resource": None, "label": "A",
    },
    "settler": {
        "name": "Settler", "type": "civilian",
        "strength": 0, "moves": 2, "hp_max": 100, "prod_cost": 100,
        "requires_tech": None, "requires_resource": None, "label": "Se",
    },
    "worker": {
        "name": "Worker", "type": "civilian",
        "strength": 0, "moves": 2, "hp_max": 100, "prod_cost": 60,
        "requires_tech": None, "requires_resource": None, "label": "Wo",
    },
    "spearman": {
        "name": "Spearman", "type": "melee",
        "strength": 11, "moves": 2, "hp_max": 100, "prod_cost": 60,
        "requires_tech": "bronze_working", "requires_resource": None, "label": "Sp",
        "bonus_vs": {"horseman": 1.0},  # +100% attack and defense vs Horseman
    },
    "swordsman": {
        "name": "Swordsman", "type": "melee",
        "strength": 14, "moves": 2, "hp_max": 100, "prod_cost": 80,
        "requires_tech": "iron_working", "requires_resource": "iron", "label": "Sw",
    },
    "horseman": {
        "name": "Horseman", "type": "melee",
        "strength": 12, "moves": 4, "hp_max": 100, "prod_cost": 80,
        "requires_tech": "horseback_riding", "requires_resource": "horses", "label": "H",
    },
    "catapult": {
        "name": "Catapult", "type": "ranged",
        "strength": 5, "ranged_strength": 8, "range": 2,
        "moves": 2, "hp_max": 100, "prod_cost": 100,
        "requires_tech": "mathematics", "requires_resource": None, "label": "Ca",
        "bonus_vs_city": 2.0,  # +200% attack vs cities
    },
    # Medieval Era
    "pikeman": {
        "name": "Pikeman", "type": "melee",
        "strength": 16, "moves": 2, "hp_max": 100, "prod_cost": 90,
        "requires_tech": "feudalism", "requires_resource": None, "label": "Pi",
        "bonus_vs": {"horseman": 1.5, "knight": 1.5},
    },
    "longswordsman": {
        "name": "Longswordsman", "type": "melee",
        "strength": 21, "moves": 2, "hp_max": 100, "prod_cost": 100,
        "requires_tech": "steel", "requires_resource": "iron", "label": "Ls",
    },
    "knight": {
        "name": "Knight", "type": "melee",
        "strength": 20, "moves": 4, "hp_max": 100, "prod_cost": 120,
        "requires_tech": "steel", "requires_resource": "horses", "label": "Kn",
    },
    "crossbowman": {
        "name": "Crossbowman", "type": "ranged",
        "strength": 12, "ranged_strength": 18, "range": 2,
        "moves": 2, "hp_max": 100, "prod_cost": 90,
        "requires_tech": "machinery", "requires_resource": None, "label": "Xb",
    },
    "trebuchet": {
        "name": "Trebuchet", "type": "ranged",
        "strength": 13, "ranged_strength": 14, "range": 2,
        "moves": 2, "hp_max": 100, "prod_cost": 120,
        "requires_tech": "machinery", "requires_resource": None, "label": "Tr",
        "bonus_vs_city": 2.5,
    },
}

# Each entry: from_unit -> (to_unit, gold_cost)
UNIT_UPGRADES = {
    "warrior":   ("swordsman",     60),
    "spearman":  ("pikeman",       60),
    "swordsman": ("longswordsman", 50),
    "archer":    ("crossbowman",   70),
    "horseman":  ("knight",        60),
    "catapult":  ("trebuchet",     40),
}
