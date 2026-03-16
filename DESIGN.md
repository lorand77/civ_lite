# Civ V-Style Game — Design Document

This document is the single source of truth for implementing a Civilization V-inspired turn-based strategy game in Python/pygame. Read this file at the start of a new session before writing any code.

---

## Overview

- **Genre**: Turn-based 4X strategy (Explore, Expand, Exploit, Exterminate)
- **Players**: 4 humans, hotseat (pass the keyboard)
- **Victory**: Domination only — capture all other civilizations' original capitals
- **AI**: None in v1
- **Map**: 32 × 20 pointy-top hex grid, procedurally generated
- **Art**: Colored shapes only — no external image assets
- **Libraries**: `pygame`, `numpy` (already installed in `.venv`)
- **Python**: 3.12 (`.venv` at `/workspace/.venv`)

---

## Project Structure

Create the following package at `/workspace/civ_game/`:

```
/workspace/
├── DESIGN.md                    ← this file
├── main.py                      ← entry point (run this)
└── civ_game/
    ├── __init__.py
    ├── game.py                  # Game state, turn manager, win detection
    ├── map/
    │   ├── __init__.py
    │   ├── hex_grid.py          # Axial hex math, pixel↔hex, neighbors, distance
    │   ├── terrain.py           # Terrain & resource type definitions + yields
    │   └── generator.py         # Procedural map generation using numpy
    ├── entities/
    │   ├── __init__.py
    │   ├── civilization.py      # Per-player state: gold, science, cities, units
    │   ├── city.py              # City: population, food, production queue, buildings
    │   ├── unit.py              # Unit instance: type, HP, moves_left, owner
    │   └── improvement.py       # Tile improvement instance + build progress
    ├── systems/
    │   ├── __init__.py
    │   ├── combat.py            # Melee/ranged damage calculation + city capture
    │   ├── production.py        # Per-turn production queue processing
    │   ├── tech_tree.py         # Tech prerequisites, research progress per civ
    │   └── yields.py            # Per-tile yield calc (terrain + resource + improvement)
    ├── ui/
    │   ├── __init__.py
    │   ├── renderer.py          # All pygame drawing: map, units, cities, overlays
    │   ├── hud.py               # Bottom info bar
    │   ├── city_screen.py       # City detail popup (production queue + buildings)
    │   └── tech_screen.py       # Tech tree overlay
    └── data/
        ├── __init__.py
        ├── units.py             # Unit type definitions (static data)
        ├── buildings.py         # Building definitions (static data)
        └── techs.py             # Tech tree definitions (static data)
```

---

## Constants

```python
# Map
MAP_COLS = 32
MAP_ROWS = 20
HEX_SIZE = 36          # pixels from center to corner (pointy-top)
NUM_PLAYERS = 4

# Window
SCREEN_W = 1280
SCREEN_H = 720
HUD_HEIGHT = 120       # bottom bar height in pixels

# Colors (R, G, B)
COLOR_GRASSLAND  = (106, 168, 79)
COLOR_PLAINS     = (182, 215, 168)
COLOR_HILLS      = (153, 102, 51)
COLOR_FOREST     = (39, 78, 19)
COLOR_OCEAN      = (30, 90, 180)
COLOR_HEX_BORDER = (0, 0, 0)
COLOR_HUD_BG     = (30, 30, 30)
COLOR_TEXT       = (255, 255, 255)

# Player colors
PLAYER_COLORS = [
    (220, 50, 50),    # Player 1: Red
    (50, 100, 220),   # Player 2: Blue
    (50, 180, 50),    # Player 3: Green
    (220, 180, 50),   # Player 4: Yellow
]

# Resource dot colors
RESOURCE_COLORS = {
    "iron":     (160, 160, 160),
    "horses":   (200, 160, 100),
    "gold":     (255, 215, 0),
    "silver":   (192, 192, 192),
    "diamonds": (180, 230, 255),
}
```

---

## Hex Grid Math (Pointy-Top Axial Coordinates)

Use **axial coordinates** `(q, r)`. Pointy-top hexes.

```python
import math

HEX_SIZE = 36  # center-to-corner

def hex_to_pixel(q, r, offset_x=0, offset_y=0):
    """Convert axial hex coords to pixel center (x, y)."""
    x = HEX_SIZE * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
    y = HEX_SIZE * (3 / 2 * r)
    return (int(x) + offset_x, int(y) + offset_y)

def pixel_to_hex(px, py, offset_x=0, offset_y=0):
    """Convert pixel position to nearest axial hex coords."""
    px -= offset_x
    py -= offset_y
    q = (math.sqrt(3) / 3 * px - 1 / 3 * py) / HEX_SIZE
    r = (2 / 3 * py) / HEX_SIZE
    return axial_round(q, r)

def axial_round(q, r):
    """Round fractional axial coords to nearest hex."""
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return (rq, rr)

# 6 neighbors in axial coords (pointy-top)
HEX_DIRECTIONS = [(1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1)]

def hex_neighbors(q, r):
    return [(q + dq, r + dr) for dq, dr in HEX_DIRECTIONS]

def hex_distance(q1, r1, q2, r2):
    return (abs(q1-q2) + abs(q1+r1-q2-r2) + abs(r1-r2)) // 2

def hex_ring(q, r, radius):
    """All hex coords exactly `radius` steps from (q,r)."""
    results = []
    dq, dr = HEX_DIRECTIONS[4]
    hq, hr = q + dq * radius, r + dr * radius
    for i in range(6):
        for _ in range(radius):
            results.append((hq, hr))
            ddq, ddr = HEX_DIRECTIONS[i]
            hq += ddq
            hr += ddr
    return results

def hexes_in_range(q, r, n):
    """All hex coords within distance n (including center)."""
    results = []
    for dq in range(-n, n+1):
        for dr in range(max(-n, -dq-n), min(n, -dq+n)+1):
            results.append((q+dq, r+dr))
    return results

def hex_corners(cx, cy):
    """6 corner pixel positions for a pointy-top hex centered at (cx,cy)."""
    corners = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        corners.append((cx + HEX_SIZE * math.cos(angle),
                         cy + HEX_SIZE * math.sin(angle)))
    return corners
```

---

## Map Storage

The map is a 2D dict: `tiles[(q, r)] = Tile`

```python
@dataclass
class Tile:
    q: int
    r: int
    terrain: str          # "grassland"|"plains"|"hills"|"forest"|"ocean"
    resource: str | None  # "iron"|"horses"|"gold"|"silver"|"diamonds"|None
    improvement: str | None  # "farm"|"mine"|"pasture"|None
    improvement_turns_left: int  # 0 = complete
    city: City | None     # city on this tile (if any)
    unit: Unit | None     # military unit on this tile (if any)
    civilian: Unit | None # civilian unit (Settler/Worker) on this tile
    owner: int | None     # player index who owns this tile (territory)
```

Valid `(q, r)` coords: all pairs where `0 <= r < MAP_ROWS` and offset column range fits. Use **offset-to-axial conversion** when iterating rows:

```python
def offset_to_axial(col, row):
    q = col - (row - (row & 1)) // 2
    r = row
    return q, r
```

Generate all map tiles by iterating `col` in `range(MAP_COLS)` and `row` in `range(MAP_ROWS)`.

---

## Terrain

```python
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
    "hills":     0.25,   # +25% defense strength
    "forest":    0.25,
    "ocean":     0,
}

TERRAIN_PASSABLE = {
    "grassland": True,
    "plains":    True,
    "hills":     True,
    "forest":    True,
    "ocean":     False,  # land units cannot enter
}
```

---

## Resources

```python
# Resource definitions
RESOURCES = {
    "iron": {
        "type": "strategic",
        "valid_terrain": ["hills"],
        "yield_bonus": {"prod": 1},
        "requires_tech": "mining",        # tile must be mined to reveal
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
        "requires_tech": None,            # always visible

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

# A resource is "visible" to a civ if requires_tech is None
# OR the civ has researched that tech.
# A strategic resource "connected" = visible + worked by one of civ's cities.
```

---

## Map Generation (numpy)

```python
import numpy as np

def generate_map(cols, rows, seed=None):
    """
    Returns dict: {(q,r): Tile}
    Algorithm:
    1. Generate elevation noise (numpy random + gaussian blur approximation)
    2. Threshold elevation to assign terrain:
       - elevation > 0.65  → hills
       - elevation > 0.45  → forest (if adjacent to other forest, cluster)
       - elevation > 0.0   → plains or grassland (random split 40/60)
       - border/low areas  → ocean (flood-fill from edges until ~30% of map)
    3. Ensure map edges are mostly ocean
    4. Scatter resources:
       - Iron:     place on ~8 hills tiles (random)
       - Horses:   place on ~6 plains/grassland tiles
       - Gold:     place on ~5 plains/grassland tiles
       - Silver:   place on ~4 hills tiles
       - Diamonds: place on ~3 forest/hills tiles
    5. Ensure each player's starting area (quadrant) has at least
       1 grassland tile within 3 hexes for Settler placement
    """
    rng = np.random.default_rng(seed)
    # ... implementation details in generator.py
```

**Starting positions**: divide map into 4 quadrants (top-left, top-right, bottom-left, bottom-right). Each player gets a Settler + Warrior placed on the best grassland/plains tile in their quadrant.

---

## Civilization (Player State)

```python
@dataclass
class Civilization:
    player_index: int       # 0–3
    name: str               # "Player 1" etc.
    color: tuple            # RGB
    cities: list[City]
    units: list[Unit]
    gold: int = 0
    gold_per_turn: int = 0  # recalculated each turn
    science: int = 0        # accumulated beakers
    science_per_turn: int = 0
    culture: int = 0        # accumulated (only for border growth)
    current_research: str | None = None   # tech key being researched
    techs_researched: set = field(default_factory=set)
    original_capital: City | None = None  # set when first city founded
    is_eliminated: bool = False
```

---

## City

```python
@dataclass
class City:
    name: str
    q: int
    r: int
    owner: int              # player index
    population: int = 1
    food_stored: int = 0
    hp: int = 50            # max 50; reduced when bombarded
    buildings: list[str] = field(default_factory=list)  # building keys
    production_queue: list[str] = field(default_factory=list)  # unit/building keys
    production_progress: int = 0  # hammers accumulated toward front of queue
    worked_tiles: list[tuple] = field(default_factory=list)  # (q,r) tiles worked
    is_original_capital: bool = False

# Territory: all tiles within hex_distance <= 3 of city center
# that are not ocean and not already owned by another civ.
# On founding, claim all tiles within distance 1 immediately.
# At culture thresholds, expand to distance 2, then 3.
# Culture thresholds: 10 culture → radius 2, 50 culture → radius 3

# Food growth formula:
#   food_yield = sum of food from worked tiles + buildings (Granary +2)
#   food_stored += food_yield - (population * 2)
#   growth_threshold = 15 + 6 * population
#   if food_stored >= growth_threshold: population += 1, food_stored = 0
#   if food_stored < 0: food_stored = 0  (no starvation in v1, just cap at 0)

# Production:
#   prod_yield = sum of prod from worked tiles + buildings
#   production_progress += prod_yield each turn
#   when progress >= item cost: item complete, progress -= cost (overflow kept)

# Gold income per city:
#   gold_yield = sum of gold from worked tiles + buildings (Market +2)
#   subtract building maintenance: 1 gold per non-free building per turn
#   add to civ's gold pool

# Science per city:
#   science_yield = 1 (base) + buildings (Library +2, etc.)
#   add to civ's science pool
```

---

## Units (Static Definitions)

```python
# data/units.py
UNIT_DEFS = {
    "warrior": {
        "name": "Warrior",
        "type": "melee",
        "strength": 8,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 40,
        "requires_tech": None,
        "requires_resource": None,
        "label": "W",   # single letter drawn on token
    },
    "archer": {
        "name": "Archer",
        "type": "ranged",
        "strength": 5,
        "ranged_strength": 7,
        "range": 2,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 40,
        "requires_tech": "archery",
        "requires_resource": None,
        "label": "A",
    },
    "settler": {
        "name": "Settler",
        "type": "civilian",
        "strength": 0,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 100,
        "requires_tech": None,
        "requires_resource": None,
        "label": "Se",
    },
    "worker": {
        "name": "Worker",
        "type": "civilian",
        "strength": 0,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 60,
        "requires_tech": None,
        "requires_resource": None,
        "label": "Wo",
    },
    "spearman": {
        "name": "Spearman",
        "type": "melee",
        "strength": 11,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 60,
        "requires_tech": "bronze_working",
        "requires_resource": None,
        "label": "Sp",
    },
    "swordsman": {
        "name": "Swordsman",
        "type": "melee",
        "strength": 14,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 80,
        "requires_tech": "iron_working",
        "requires_resource": "iron",
        "label": "Sw",
    },
    "horseman": {
        "name": "Horseman",
        "type": "melee",
        "strength": 12,
        "moves": 4,
        "hp_max": 100,
        "prod_cost": 80,
        "requires_tech": "horseback_riding",
        "requires_resource": "horses",
        "label": "H",
    },
    "catapult": {
        "name": "Catapult",
        "type": "ranged",
        "strength": 5,
        "ranged_strength": 8,
        "range": 2,
        "moves": 2,
        "hp_max": 100,
        "prod_cost": 100,
        "requires_tech": "mathematics",
        "requires_resource": None,
        "label": "Ca",
    },
}
```

---

## Buildings (Static Definitions)

```python
# data/buildings.py
BUILDING_DEFS = {
    "monument": {
        "name": "Monument",
        "prod_cost": 60,
        "requires_tech": None,
        "effects": {"culture_per_turn": 2},
        "maintenance": 0,
    },
    "granary": {
        "name": "Granary",
        "prod_cost": 80,
        "requires_tech": "pottery",
        "effects": {"food_per_turn": 2},
        "maintenance": 1,
    },
    "barracks": {
        "name": "Barracks",
        "prod_cost": 80,
        "requires_tech": "bronze_working",
        "effects": {"new_unit_xp": 15},
        "maintenance": 1,
    },
    "library": {
        "name": "Library",
        "prod_cost": 100,
        "requires_tech": "writing",
        "effects": {"science_per_turn": 2},
        "maintenance": 1,
    },
    "market": {
        "name": "Market",
        "prod_cost": 100,
        "requires_tech": "currency",
        "effects": {"gold_per_turn": 2},
        "maintenance": 1,
    },
    "forge": {
        "name": "Forge",
        "prod_cost": 120,
        "requires_tech": "iron_working",
        "effects": {"prod_bonus_hills": 1},  # +1 prod on hills tiles worked
        "maintenance": 1,
    },
}
```

---

## Tech Tree (Static Definitions)

```python
# data/techs.py
TECH_DEFS = {
    # Ancient Era
    "mining": {
        "name": "Mining",
        "era": "ancient",
        "science_cost": 35,
        "prerequisites": [],
        "unlocks_units": [],
        "unlocks_buildings": [],
        "unlocks_improvements": ["mine"],
        "reveals_resources": ["iron", "silver"],
    },
    "animal_husbandry": {
        "name": "Animal Husbandry",
        "era": "ancient",
        "science_cost": 35,
        "prerequisites": [],
        "unlocks_units": [],
        "unlocks_buildings": [],
        "unlocks_improvements": ["pasture"],
        "reveals_resources": ["horses"],
    },
    "archery": {
        "name": "Archery",
        "era": "ancient",
        "science_cost": 35,
        "prerequisites": [],
        "unlocks_units": ["archer"],
        "unlocks_buildings": [],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
    "pottery": {
        "name": "Pottery",
        "era": "ancient",
        "science_cost": 35,
        "prerequisites": [],
        "unlocks_units": [],
        "unlocks_buildings": ["granary"],
        "unlocks_improvements": ["farm"],
        "reveals_resources": [],
    },
    "bronze_working": {
        "name": "Bronze Working",
        "era": "ancient",
        "science_cost": 55,
        "prerequisites": ["mining"],
        "unlocks_units": ["spearman"],
        "unlocks_buildings": ["barracks"],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
    # Classical Era
    "iron_working": {
        "name": "Iron Working",
        "era": "classical",
        "science_cost": 80,
        "prerequisites": ["bronze_working"],
        "unlocks_units": ["swordsman"],
        "unlocks_buildings": ["forge"],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
    "horseback_riding": {
        "name": "Horseback Riding",
        "era": "classical",
        "science_cost": 80,
        "prerequisites": ["animal_husbandry"],
        "unlocks_units": ["horseman"],
        "unlocks_buildings": [],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
    "writing": {
        "name": "Writing",
        "era": "classical",
        "science_cost": 80,
        "prerequisites": ["pottery"],
        "unlocks_units": [],
        "unlocks_buildings": ["library"],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
    "mathematics": {
        "name": "Mathematics",
        "era": "classical",
        "science_cost": 100,
        "prerequisites": ["writing"],
        "unlocks_units": ["catapult"],
        "unlocks_buildings": [],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
    "currency": {
        "name": "Currency",
        "era": "classical",
        "science_cost": 100,
        "prerequisites": ["writing"],
        "unlocks_units": [],
        "unlocks_buildings": ["market"],
        "unlocks_improvements": [],
        "reveals_resources": [],
    },
}
```

---

## Worker Improvements

```python
# data improvements (inline in improvement.py is fine)
IMPROVEMENT_DEFS = {
    "farm": {
        "name": "Farm",
        "build_turns": 3,
        "valid_terrain": ["grassland", "plains"],
        "requires_tech": "pottery",
        "yield_bonus": {"food": 1},
        "label": "f",   # small letter drawn on tile
    },
    "mine": {
        "name": "Mine",
        "build_turns": 3,
        "valid_terrain": ["hills"],
        "requires_tech": "mining",
        "yield_bonus": {"prod": 1},
        "label": "m",
    },
    "pasture": {
        "name": "Pasture",
        "build_turns": 3,
        "valid_terrain": ["grassland", "plains"],
        "requires_tech": "animal_husbandry",
        "yield_bonus": {"food": 1},
        "label": "p",
    },
}
```

---

## Unit Instance

```python
@dataclass
class Unit:
    unit_type: str          # key into UNIT_DEFS
    owner: int              # player index
    q: int
    r: int
    hp: int                 # current HP (starts at hp_max)
    moves_left: int         # resets to UNIT_DEFS[type]["moves"] each turn
    xp: int = 0
    fortified: bool = False # +25% defense, cleared on move
    fortify_bonus: float = 0.0  # 0.0, 0.25, or 0.5 (max after 2 turns)
```

---

## Combat System

```python
import math

def calc_damage(attacker_str, defender_str):
    """Returns integer damage dealt."""
    diff = attacker_str - defender_str
    damage = 30 * math.exp(0.04 * diff)
    return max(1, min(50, int(damage)))

def effective_strength(unit, tile):
    """Adjust unit combat strength for terrain and fortify."""
    base = UNIT_DEFS[unit.unit_type]["strength"]
    terrain_bonus = TERRAIN_DEFENSE_BONUS[tile.terrain]
    fortify_bonus = unit.fortify_bonus
    return base * (1 + terrain_bonus + fortify_bonus)

def melee_attack(attacker: Unit, defender: Unit, attacker_tile, defender_tile):
    """Both units take damage. Returns (attacker_dmg, defender_dmg)."""
    a_str = effective_strength(attacker, attacker_tile)
    d_str = effective_strength(defender, defender_tile)
    attacker_dmg = calc_damage(d_str, a_str)   # defender hits attacker
    defender_dmg = calc_damage(a_str, d_str)   # attacker hits defender
    attacker.hp -= attacker_dmg
    defender.hp -= defender_dmg
    return attacker_dmg, defender_dmg

def ranged_attack(attacker: Unit, defender: Unit, attacker_tile, defender_tile):
    """Only defender takes damage."""
    a_str = UNIT_DEFS[attacker.unit_type].get("ranged_strength",
              UNIT_DEFS[attacker.unit_type]["strength"])
    d_str = effective_strength(defender, defender_tile)
    defender_dmg = calc_damage(a_str, d_str)
    defender.hp -= defender_dmg
    return defender_dmg

def bombard_city(attacker: Unit, city: City):
    """Ranged unit attacks city HP directly."""
    a_str = UNIT_DEFS[attacker.unit_type].get("ranged_strength",
              UNIT_DEFS[attacker.unit_type]["strength"])
    dmg = max(1, min(20, int(a_str * 0.4)))
    city.hp -= dmg
    return dmg

# City capture:
# When a melee unit attacks a tile containing a city with hp <= 0,
# the unit moves into the tile and the city changes owner.
# If it was the original capital of a player, check domination victory.

# Domination victory:
# After any capture, check: does any single player now own all
# original capitals (including their own)? If yes, that player wins.
# Also: if a player loses ALL cities, they are eliminated.
```

---

## Turn Processing (End of Turn)

Called when a player clicks End Turn:

```python
def end_turn(game):
    civ = game.current_civ()

    # 1. Process each city
    for city in civ.cities:
        yields = compute_city_yields(city, game.tiles, civ)

        # Food growth
        city.food_stored += yields["food"] - city.population * 2
        city.food_stored = max(0, city.food_stored)
        threshold = 15 + 6 * city.population
        if city.food_stored >= threshold:
            city.population += 1
            city.food_stored = 0
            auto_assign_citizen(city, game.tiles)

        # Production
        city.production_progress += yields["prod"]
        if city.production_queue:
            item = city.production_queue[0]
            cost = get_item_cost(item)
            if city.production_progress >= cost:
                city.production_progress -= cost
                complete_production(city, item, civ, game)
                city.production_queue.pop(0)

        # Gold
        civ.gold += yields["gold"] - city_maintenance(city)

        # Science
        civ.science += yields["science"]

        # Culture (border expansion)
        civ.culture += yields["culture"]
        check_border_expansion(city, civ, game.tiles)

    # 2. Unit maintenance
    for unit in civ.units:
        if UNIT_DEFS[unit.unit_type]["type"] != "civilian":
            civ.gold -= 1  # 1 gold/turn per military unit

    # 3. Research
    if civ.current_research:
        tech = TECH_DEFS[civ.current_research]
        if civ.science >= tech["science_cost"]:
            civ.science -= tech["science_cost"]
            civ.techs_researched.add(civ.current_research)
            civ.current_research = None
            # notify player

    # 4. Worker improvements
    for unit in civ.units:
        if unit.unit_type == "worker" and unit.building_improvement:
            unit.build_turns_left -= 1
            if unit.build_turns_left <= 0:
                tile = game.tiles[(unit.q, unit.r)]
                tile.improvement = unit.building_improvement
                unit.building_improvement = None

    # 5. Reset unit movement
    for unit in civ.units:
        unit.moves_left = UNIT_DEFS[unit.unit_type]["moves"]
        if unit.fortified:
            unit.fortify_bonus = min(0.5, unit.fortify_bonus + 0.25)

    # 6. Advance to next player
    game.advance_turn()
    game.check_victory()
```

---

## Yield Calculation

```python
def compute_city_yields(city, tiles, civ):
    totals = {"food": 0, "prod": 0, "gold": 0, "science": 0, "culture": 0}

    for (q, r) in city.worked_tiles:
        tile = tiles.get((q, r))
        if not tile:
            continue
        t = TERRAIN_YIELDS[tile.terrain]
        totals["food"] += t["food"]
        totals["prod"] += t["prod"]
        totals["gold"] += t["gold"]

        # Resource bonus (if visible to civ)
        if tile.resource:
            res = RESOURCES[tile.resource]
            req = res.get("requires_tech")
            if req is None or req in civ.techs_researched:
                for k, v in res["yield_bonus"].items():
                    totals[k] = totals.get(k, 0) + v

        # Improvement bonus
        if tile.improvement:
            imp = IMPROVEMENT_DEFS[tile.improvement]
            for k, v in imp["yield_bonus"].items():
                totals[k] = totals.get(k, 0) + v

    # Building bonuses
    for b_key in city.buildings:
        b = BUILDING_DEFS[b_key]
        eff = b["effects"]
        totals["food"]    += eff.get("food_per_turn", 0)
        totals["prod"]    += eff.get("prod_per_turn", 0)
        totals["gold"]    += eff.get("gold_per_turn", 0)
        totals["science"] += eff.get("science_per_turn", 0)
        totals["culture"] += eff.get("culture_per_turn", 0)

    # Base science
    totals["science"] += 1  # every city generates 1 base science

    return totals
```

---

## Movement

```python
def get_reachable_tiles(unit, tiles, civ_units_by_pos):
    """
    BFS from unit's position.
    Returns set of (q,r) the unit can move to this turn.
    Rules:
    - Cost to enter any passable tile = 1 move point
    - Ocean tiles: impassable for all land units
    - Can't end turn on tile occupied by own unit of same class
      (military can't stack with military; civilian can't stack with civilian)
    - CAN move through own tiles freely
    - Enemy military unit tile: can attack (melee), don't add to reachable for movement
    """
    from collections import deque
    start = (unit.q, unit.r)
    max_moves = unit.moves_left
    visited = {start: 0}  # (q,r) → moves used
    queue = deque([(start, 0)])
    reachable = set()

    while queue:
        (q, r), used = queue.popleft()
        for nq, nr in hex_neighbors(q, r):
            tile = tiles.get((nq, nr))
            if not tile:
                continue
            if not TERRAIN_PASSABLE[tile.terrain]:
                continue
            cost = used + 1
            if cost > max_moves:
                continue
            if (nq, nr) in visited and visited[(nq, nr)] <= cost:
                continue
            visited[(nq, nr)] = cost
            # Check occupancy
            occupant = tile.unit  # military
            if occupant and occupant.owner == unit.owner:
                continue  # friendly block for military
            reachable.add((nq, nr))
            queue.append(((nq, nr), cost))

    return reachable
```

---

## Camera / Viewport

```python
@dataclass
class Camera:
    offset_x: int = 0
    offset_y: int = 0
    zoom: int = 1          # 1 = normal, 0 = zoomed out (hex_size * 0.6)

    def pan(self, dx, dy):
        self.offset_x += dx
        self.offset_y += dy

    def effective_hex_size(self):
        return HEX_SIZE if self.zoom == 1 else int(HEX_SIZE * 0.6)
```

Pan with arrow keys (10px per frame held) or middle-mouse drag. Clamp offsets so map doesn't scroll completely off-screen.

---

## Input Handling

```python
# In main game loop:
for event in pygame.event.get():
    if event.type == pygame.QUIT:
        running = False

    elif event.type == pygame.KEYDOWN:
        if event.key == pygame.K_RETURN:
            game.end_turn()
        elif event.key == pygame.K_t:
            ui_state.toggle_tech_screen()
        elif event.key == pygame.K_b and ui_state.selected_city:
            ui_state.toggle_city_screen()
        elif event.key == pygame.K_c:
            camera.center_on(game.current_civ().original_capital)

    elif event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:   # left click
            handle_left_click(event.pos, game, ui_state, camera)
        elif event.button == 3: # right click
            ui_state.deselect()
        elif event.button == 2: # middle click — start pan drag
            ui_state.pan_start = event.pos
        elif event.button == 4: # scroll up — zoom in
            camera.zoom = 1
        elif event.button == 5: # scroll down — zoom out
            camera.zoom = 0

    elif event.type == pygame.MOUSEMOTION:
        if ui_state.pan_start:
            dx = event.pos[0] - ui_state.pan_start[0]
            dy = event.pos[1] - ui_state.pan_start[1]
            camera.pan(dx, dy)
            ui_state.pan_start = event.pos

    elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 2:
            ui_state.pan_start = None

def handle_left_click(pos, game, ui_state, camera):
    # Convert screen pos to hex
    q, r = pixel_to_hex(pos[0], pos[1], camera.offset_x, camera.offset_y)
    tile = game.tiles.get((q, r))
    if not tile:
        return

    selected = ui_state.selected_unit

    if selected and (q, r) in ui_state.reachable_tiles:
        # Move unit
        game.move_unit(selected, q, r)
        ui_state.reachable_tiles = set()
        ui_state.selected_unit = None
    elif tile.unit and tile.unit.owner == game.current_player:
        # Select unit
        ui_state.selected_unit = tile.unit
        ui_state.reachable_tiles = get_reachable_tiles(tile.unit, game.tiles, ...)
    elif tile.city and tile.city.owner == game.current_player:
        ui_state.selected_city = tile.city
        ui_state.toggle_city_screen()
    else:
        ui_state.selected_tile = tile
        ui_state.selected_unit = None
```

---

## Rendering

```python
def render(screen, game, camera, ui_state):
    screen.fill((0, 0, 0))

    # Layer 1: Terrain hexes
    for (q, r), tile in game.tiles.items():
        cx, cy = hex_to_pixel(q, r, camera.offset_x, camera.offset_y)
        if not on_screen(cx, cy):
            continue
        color = TERRAIN_COLORS[tile.terrain]
        corners = hex_corners(cx, cy)
        pygame.draw.polygon(screen, color, corners)
        pygame.draw.polygon(screen, COLOR_HEX_BORDER, corners, 1)

    # Layer 2: Resource dots
    for (q, r), tile in game.tiles.items():
        if tile.resource:
            # Only show if revealed to current player
            if is_resource_visible(tile.resource, game.current_civ()):
                cx, cy = hex_to_pixel(q, r, camera.offset_x, camera.offset_y)
                color = RESOURCE_COLORS[tile.resource]
                pygame.draw.circle(screen, color, (cx + 10, cy - 10), 5)

    # Layer 3: Improvement labels
    for (q, r), tile in game.tiles.items():
        if tile.improvement:
            cx, cy = hex_to_pixel(q, r, camera.offset_x, camera.offset_y)
            label = IMPROVEMENT_DEFS[tile.improvement]["label"]
            draw_small_text(screen, label, cx - 12, cy + 10)

    # Layer 4: Territory borders
    for (q, r), tile in game.tiles.items():
        if tile.owner is not None:
            cx, cy = hex_to_pixel(q, r, camera.offset_x, camera.offset_y)
            color = PLAYER_COLORS[tile.owner]
            corners = hex_corners(cx, cy)
            pygame.draw.polygon(screen, (*color, 80), corners)  # semi-transparent fill
            # Draw border edges only on edges adjacent to different owner
            draw_territory_borders(screen, tile, game.tiles, camera)

    # Layer 5: Cities
    for civ in game.civs:
        for city in civ.cities:
            cx, cy = hex_to_pixel(city.q, city.r, camera.offset_x, camera.offset_y)
            pygame.draw.circle(screen, civ.color, (cx, cy), 14)
            pygame.draw.circle(screen, (0,0,0), (cx, cy), 14, 2)
            draw_text(screen, city.name, cx, cy - 20, font_size=12)
            draw_text(screen, str(city.population), cx, cy, font_size=11)
            if city.hp < 50:
                draw_hp_bar(screen, cx, cy + 18, city.hp, 50)

    # Layer 6: Units
    for civ in game.civs:
        for unit in civ.units:
            cx, cy = hex_to_pixel(unit.q, unit.r, camera.offset_x, camera.offset_y)
            offset = (0, 0) if UNIT_DEFS[unit.unit_type]["type"] != "civilian" else (8, 8)
            ux, uy = cx + offset[0], cy + offset[1]
            pygame.draw.circle(screen, civ.color, (ux, uy), 11)
            pygame.draw.circle(screen, (0,0,0), (ux, uy), 11, 2)
            draw_text(screen, UNIT_DEFS[unit.unit_type]["label"], ux, uy, font_size=10)
            if unit.hp < 100:
                draw_hp_bar(screen, ux, uy + 14, unit.hp, 100)

    # Layer 7: Selection + movement range
    if ui_state.selected_unit:
        u = ui_state.selected_unit
        cx, cy = hex_to_pixel(u.q, u.r, camera.offset_x, camera.offset_y)
        pygame.draw.circle(screen, (255, 255, 255), (cx, cy), 13, 3)
        for (q, r) in ui_state.reachable_tiles:
            cx2, cy2 = hex_to_pixel(q, r, camera.offset_x, camera.offset_y)
            corners = hex_corners(cx2, cy2)
            pygame.draw.polygon(screen, (255, 255, 100, 60), corners)
            pygame.draw.polygon(screen, (255, 255, 100), corners, 2)

    # Layer 8: HUD
    render_hud(screen, game, ui_state)

    # Layer 9: City screen popup (if open)
    if ui_state.city_screen_open and ui_state.selected_city:
        render_city_screen(screen, ui_state.selected_city, game.current_civ())

    # Layer 10: Tech tree (if open)
    if ui_state.tech_screen_open:
        render_tech_screen(screen, game.current_civ())

    # Layer 11: Turn banner (show briefly at start of each player's turn)
    if ui_state.turn_banner_timer > 0:
        render_turn_banner(screen, game.current_player)
        ui_state.turn_banner_timer -= 1

    pygame.display.flip()
```

---

## HUD Layout

Bottom bar (full width, HUD_HEIGHT = 120px):

```
┌─────────────────────────────────────────────────────────────────┐
│  [Selected tile/unit info]   │  Turn: 42  Player 2 (Blue)       │
│  Terrain: Plains             │  Gold: 47  Science: 12/80        │
│  Resource: Gold (+3 gold)    │  Research: Writing               │
│  Yields: F:1 P:1 G:3         │  Happiness: 2                    │
│                              │              [END TURN]          │
└─────────────────────────────────────────────────────────────────┘
```

END TURN button: rect in bottom-right, click or press Enter.

---

## City Screen Popup

Centered modal panel (~500×400px):

```
┌── [City Name] (Pop: 3) ─────────────────────────┐
│ Yields: F:6  P:4  G:3  Sci:3  Cult:2            │
│ Food: 6/27 stored (3 turns to grow)              │
│                                                  │
│ Production: [Warrior.............. 2 turns]      │
│ Queue: [change]                                  │
│                                                  │
│ Buildings: Monument, Granary                     │
│                                                  │
│ Available to build:                              │
│   [Library - 100 prod - 25 turns]                │
│   [Barracks - 80 prod - 20 turns]                │
│                    [CLOSE]                       │
└──────────────────────────────────────────────────┘
```

---

## Tech Screen Overlay

Full-screen semi-transparent overlay. Draw tech nodes as rounded rects connected by lines:

```
ANCIENT ERA                    CLASSICAL ERA
[Mining] ──────────────────► [Iron Working]
   └──► [Bronze Working] ──►/
[Animal Husb.] ─────────────► [Horseback Riding]
[Archery]
[Pottery] ──────────────────► [Writing] ──► [Mathematics]
                                        └──► [Currency]
```

- Researched techs: filled with civ color
- Current research: pulsing border
- Available (prereqs met): white border
- Locked (prereqs not met): grey, dimmed

Click a tech to set as current research.

---

## main.py Entry Point

```python
import pygame
from civ_game.game import Game
from civ_game.ui.renderer import render
from civ_game.ui.hud import UIState

def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("CivPy")
    clock = pygame.time.Clock()

    game = Game(num_players=4, map_cols=32, map_rows=20, seed=42)
    ui_state = UIState()
    ui_state.turn_banner_timer = 120

    running = True
    while running:
        for event in pygame.event.get():
            handle_event(event, game, ui_state)
            if event.type == pygame.QUIT:
                running = False

        # Arrow key pan
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:  game.camera.pan(-8, 0)
        if keys[pygame.K_RIGHT]: game.camera.pan(8, 0)
        if keys[pygame.K_UP]:    game.camera.pan(0, -8)
        if keys[pygame.K_DOWN]:  game.camera.pan(0, 8)

        render(screen, game, game.camera, ui_state)
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
```

---

## Implementation Order (Phases)

### Phase 1 — Hex Map (start here)
1. Create package skeleton with all `__init__.py` files
2. Implement `hex_grid.py` (all math functions above)
3. Implement `terrain.py` (constants + TERRAIN_YIELDS)
4. Implement `generator.py` (numpy terrain + resource placement)
5. Implement `game.py` (Game class holding tiles dict + Camera)
6. Implement `renderer.py` (layers 1–2 only: terrain + resources)
7. Implement `hud.py` (show selected tile info)
8. Wire up `main.py` with pan + zoom + click-to-select
9. **Verify**: run main.py, see 32×20 hex map, click tiles, pan

### Phase 2 — Cities & Workers
1. `entities/unit.py` — Settler + Worker only
2. `entities/city.py` — founding, territory, food growth
3. `systems/yields.py` — compute_city_yields
4. `entities/improvement.py` + Worker build logic
5. `systems/production.py` — queue + building completion
6. `ui/city_screen.py`
7. Add Settler/Worker to renderer
8. **Verify**: move Settler, found city, build Granary, watch pop grow

### Phase 3 — Combat & Units
1. `data/units.py` — full unit defs
2. Full unit movement (BFS reachable tiles)
3. `systems/combat.py` — melee + ranged + city bombard/capture
4. Domination victory check
5. **Verify**: declare war, attack, capture capital, win screen

### Phase 4 — Tech Tree
1. `data/techs.py` + `data/buildings.py`
2. `systems/tech_tree.py` — research progress
3. `ui/tech_screen.py` — clickable overlay
4. Gate units/buildings/improvements behind techs
5. Strategic resource gating for Swordsman/Horseman
6. **Verify**: research Writing, Library becomes available, build it

### Phase 5 — Hotseat Polish
1. 4-player turn manager with banners
2. Gold maintenance (1 gold/unit/turn)
3. Notifications system (small popup messages)
4. Happiness counter from luxuries
5. Elimination detection (no cities left)
6. **Verify**: 4-player full game to domination victory

---

## Notes for Implementation Session

- Run the game with: `cd /workspace && .venv/bin/python main.py`
- pygame and numpy are already installed in `/workspace/.venv`
- The existing file `/workspace/setup/Untitled-1.py` is just a hello-world; ignore it or repurpose
- Use `pygame.font.SysFont("monospace", size)` for all text — no font files needed
- Semi-transparent surfaces: create a separate Surface with `pygame.SRCALPHA`, draw on it, then `screen.blit()`
- For the tech tree layout, hardcode the x/y positions of each node (10 nodes is manageable)
- Keep all game state in the `Game` object; keep all UI state in `UIState`; never mix them
