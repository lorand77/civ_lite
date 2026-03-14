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
    },
}
