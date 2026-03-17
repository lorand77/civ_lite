# Civ V-Style Game — Design Document

This document reflects the **actual implemented state** of the game. It is the single source of truth for the codebase at `/workspace/civ_lite_py/`.

---

## Overview

- **Genre**: Turn-based 4X strategy (Explore, Expand, Exploit, Exterminate)
- **Players**: 4 humans, hotseat (pass the keyboard)
- **Victory**: Domination only — capture all other civilizations' original capitals
- **AI**: None in v1
- **Map**: 32 × 20 pointy-top hex grid, procedurally generated
- **Art**: Colored shapes only — no external image assets
- **Libraries**: `pygame`, `numpy` (installed in `.venv`)
- **Python**: 3.12 (`.venv` at `/workspace/.venv`)
- **Entry point**: `cd /workspace/civ_lite_py && ../.venv/bin/python main.py`

---

## Project Structure

```
/workspace/
├── DESIGN.md                    ← this file
└── civ_lite_py/
    ├── main.py                  ← entry point
    └── civ_game/
        ├── __init__.py
        ├── game.py              # Game state, Camera, turn manager, win detection
        ├── map/
        │   ├── hex_grid.py      # Axial hex math, pixel↔hex, neighbors, distance
        │   ├── terrain.py       # Terrain & resource definitions + yields
        │   └── generator.py     # Procedural map generation (numpy)
        ├── entities/
        │   ├── civilization.py  # Per-player state
        │   ├── city.py          # City: population, food, production, buildings
        │   ├── unit.py          # Unit instance + movement/attack BFS
        │   └── improvement.py   # Tile improvement definitions
        ├── systems/
        │   ├── combat.py        # Melee/ranged damage + city capture
        │   ├── production.py    # Production queue processing
        │   ├── tech_tree.py     # Tech prerequisites helper functions
        │   └── yields.py        # Per-city yield calculation
        ├── ui/
        │   ├── renderer.py      # All pygame drawing
        │   ├── hud.py           # Bottom info bar + UIState dataclass
        │   ├── city_screen.py   # City detail popup
        │   └── tech_screen.py   # Tech tree overlay
        └── data/
            ├── units.py         # Unit type definitions (static)
            ├── buildings.py     # Building definitions (static)
            └── techs.py         # Tech tree definitions (static)
```

---

## Constants

```python
# Map
MAP_COLS = 32
MAP_ROWS = 20
NUM_PLAYERS = 4

# Hex
HEX_SIZE = 72          # pixels from center to corner (pointy-top)

# Window
SCREEN_W = 1850
SCREEN_H = 1000
HUD_HEIGHT = 180       # bottom bar height in pixels

# Player colors (R, G, B)
PLAYER_COLORS = [
    (220, 50,  50),    # Player 1: Red
    (50,  100, 220),   # Player 2: Blue
    (50,  180, 50),    # Player 3: Green
    (220, 180, 50),    # Player 4: Yellow
]

PLAYER_NAMES = ["Player 1", "Player 2", "Player 3", "Player 4"]

# City name pools (5 names per player, cycling)
CITY_NAMES = [
    ["Rome",    "Florence", "Venice",  "Genoa",   "Naples"],
    ["Athens",  "Sparta",   "Corinth", "Thebes",  "Argos"],
    ["Delhi",   "Agra",     "Patna",   "Mysore",  "Lahore"],
    ["Babylon", "Ur",       "Nineveh", "Kish",    "Akkad"],
]
```

---

## Hex Grid Math (Pointy-Top Axial Coordinates)

File: `map/hex_grid.py`

```python
HEX_SIZE = 72          # center-to-corner distance in pixels

HEX_DIRECTIONS = [(1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1)]

def hex_to_pixel(q, r, offset_x=0, offset_y=0, hex_size=HEX_SIZE) -> (x, y)
def pixel_to_hex(px, py, offset_x=0, offset_y=0, hex_size=HEX_SIZE) -> (q, r)
def axial_round(q, r) -> (q, r)
def hex_neighbors(q, r) -> list[(q,r)]
def hex_distance(q1, r1, q2, r2) -> int
def hex_ring(q, r, radius) -> list[(q,r)]
def hexes_in_range(q, r, n) -> list[(q,r)]
def hex_corners(cx, cy, hex_size=HEX_SIZE) -> list[(x,y)]
def offset_to_axial(col, row) -> (q, r)
```

---

## Map Storage

`tiles: dict {(q, r): Tile}` — defined in `map/generator.py`

```python
@dataclass
class Tile:
    q: int
    r: int
    terrain: str              # "grassland"|"plains"|"hills"|"forest"|"ocean"
    resource: str | None      # "iron"|"horses"|"gold"|"silver"|"diamonds"|None
    improvement: str | None   # "farm"|"mine"|"pasture"|None
    improvement_turns_left: int = 0
    city: City | None = None
    unit: Unit | None = None        # military unit
    civilian: Unit | None = None    # civilian unit (Settler/Worker)
    owner: int | None = None        # player index who owns this tile
```

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
    "hills":     0.25,   # +25% effective strength
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
    "hills":     2,    # costs 2 move points to enter
    "forest":    2,
    "ocean":     99,   # impassable
}

TERRAIN_COLORS = {
    "grassland": (106, 168, 79),
    "plains":    (182, 215, 168),
    "hills":     (153, 102, 51),
    "forest":    (39, 78, 19),
    "ocean":     (30, 90, 180),
}
```

---

## Resources

```python
RESOURCES = {
    "iron": {
        "type": "strategic",
        "valid_terrain": ["hills"],
        "yield_bonus": {"prod": 1},
        "requires_tech": "mining",       # hidden until Mining is researched
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
        "requires_tech": None,           # always visible
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
```

Resource visibility: shown on the map only if `requires_tech` is None or the current
player has researched that tech.

Strategic resource connection: a unit/building requiring a resource can be built in
**any** of that player's cities if the resource appears in the worked tiles of **any**
of that player's cities (and is visible).

---

## Map Generation

File: `map/generator.py` — `generate_map(cols, rows, seed=None) -> dict {(q,r): Tile}`

1. Generate elevation noise with numpy, apply 2-pass box blur for smoothing
2. Apply edge penalty so map borders become ocean
3. Assign terrain per cell:
   - `e > 0.54` → hills
   - `e > 0.46` → forest
   - `e > 0.16` → plains (40%) or grassland (60%)
   - `e ≤ 0.16` → ocean; all border cells forced ocean
4. Scatter resources: iron×8, horses×6, gold×4, silver×5, diamonds×3
5. Starting positions: 4 quadrants — each player gets Settler + Worker + Warrior
   placed on a grassland/plains tile in their quadrant

---

## Civilization (Player State)

File: `entities/civilization.py`

```python
@dataclass
class Civilization:
    player_index: int
    name: str
    color: tuple                    # RGB

    cities: list[City]
    units: list[Unit]

    gold: int = 0
    science: int = 0                # accumulated beakers
    culture: int = 0                # total accumulated culture

    current_research: str | None = None
    techs_researched: set = field(default_factory=set)
    original_capital: City | None = None
    is_eliminated: bool = False

    pending_messages: list = field(default_factory=list)
    # Messages shown at the START of that player's NEXT turn (after turn banner).
    # Includes: tech completions, unit/building completions, bankruptcy notices.

    research_just_completed: bool = False
    # Set True when a tech finishes this turn. Consumed in _do_end_turn to
    # auto-open the tech screen on the player's next turn.
```

---

## City

File: `entities/city.py`

```python
@dataclass
class City:
    name: str
    q: int
    r: int
    owner: int
    population: int = 1
    food_stored: int = 0
    hp: int = 50                    # max 50; regenerates 5/turn when damaged
    buildings: list[str] = field(default_factory=list)
    production_queue: list[str] = field(default_factory=list)
    production_progress: int = 0
    worked_tiles: list[tuple] = field(default_factory=list)
    is_original_capital: bool = False
    culture_stored: int = 0         # accumulates toward next border expansion

@property
def food_growth_threshold(self) -> int:
    return 15 + 6 * self.population
    # Pop 1 → 21, Pop 2 → 27, Pop 3 → 33, ...
```

**Territory**: all tiles within `hex_distance <= 3` of the city center owned by
that player. Founding claims radius 1 immediately. Each 20 `culture_stored` per city
→ one best-yield adjacent unclaimed tile is claimed.

**Worked tiles**: city center tile + top `(population - 1)` adjacent non-ocean tiles
sorted by yield score `(food × 1.1 + prod + gold)`. Re-assigned on population growth.

---

## Units

File: `entities/unit.py`

```python
@dataclass
class Unit:
    unit_type: str         # key into UNIT_DEFS
    owner: int
    q: int
    r: int
    hp: int
    moves_left: int
    fortified: bool = False
    fortify_bonus: float = 0.0   # 0.0 → 0.25 → 0.5 (max after 2 turns fortified)
    healing: bool = False
    building_improvement: str | None = None
    build_turns_left: int = 0
    xp: int = 0

# Computed properties
is_civilian: bool   # True if UNIT_DEFS[unit_type]["type"] == "civilian"
label: str          # UNIT_DEFS[unit_type]["label"]
name: str           # UNIT_DEFS[unit_type]["name"]
```

### Unit Definitions

```python
UNIT_DEFS = {
    "warrior":   { "type": "melee",    "strength": 8,
                   "moves": 2, "hp_max": 100, "prod_cost": 40,
                   "requires_tech": None,  "requires_resource": None, "label": "W"  },
    "archer":    { "type": "ranged",   "strength": 5, "ranged_strength": 7, "range": 2,
                   "moves": 2, "hp_max": 100, "prod_cost": 40,
                   "requires_tech": "archery", "requires_resource": None, "label": "A" },
    "settler":   { "type": "civilian", "strength": 0,
                   "moves": 2, "hp_max": 100, "prod_cost": 100,
                   "requires_tech": None,  "requires_resource": None, "label": "Se" },
    "worker":    { "type": "civilian", "strength": 0,
                   "moves": 2, "hp_max": 100, "prod_cost": 60,
                   "requires_tech": None,  "requires_resource": None, "label": "Wo" },
    "spearman":  { "type": "melee",    "strength": 11,
                   "moves": 2, "hp_max": 100, "prod_cost": 60,
                   "requires_tech": "bronze_working", "requires_resource": None,
                   "bonus_vs": {"horseman": 1.0},      "label": "Sp" },
    "swordsman": { "type": "melee",    "strength": 14,
                   "moves": 2, "hp_max": 100, "prod_cost": 80,
                   "requires_tech": "iron_working", "requires_resource": "iron",
                   "label": "Sw" },
    "horseman":  { "type": "melee",    "strength": 12,
                   "moves": 4, "hp_max": 100, "prod_cost": 80,
                   "requires_tech": "horseback_riding", "requires_resource": "horses",
                   "label": "H"  },
    "catapult":  { "type": "ranged",   "strength": 5, "ranged_strength": 8, "range": 2,
                   "moves": 2, "hp_max": 100, "prod_cost": 100,
                   "requires_tech": "mathematics", "requires_resource": None,
                   "bonus_vs_city": 2.0,               "label": "Ca" },
}
```

---

## Buildings

File: `data/buildings.py`

```python
BUILDING_DEFS = {
    "palace":   { "prod_cost": 0,   "requires_tech": None,
                  "effects": {"prod_per_turn": 3, "gold_per_turn": 3, "culture_per_turn": 2},
                  "maintenance": 0 },
    "monument": { "prod_cost": 60,  "requires_tech": None,
                  "effects": {"culture_per_turn": 2},
                  "maintenance": 0 },
    "granary":  { "prod_cost": 80,  "requires_tech": "pottery",
                  "effects": {"food_per_turn": 2},
                  "maintenance": 1 },
    "library":  { "prod_cost": 100, "requires_tech": "writing",
                  "effects": {"science_per_turn": 2},
                  "maintenance": 1 },
    "market":   { "prod_cost": 100, "requires_tech": "currency",
                  "effects": {"gold_per_turn": 2},
                  "maintenance": 0 },
    "forge":    { "prod_cost": 120, "requires_tech": "iron_working",
                  "effects": {"prod_bonus_hills": 1},  # +1 prod per hills tile worked
                  "maintenance": 1 },
}
```

Palace is added automatically when a player founds their original capital.
It cannot be built or removed manually.

---

## Worker Improvements

File: `entities/improvement.py`

```python
IMPROVEMENT_DEFS = {
    "farm":    { "build_turns": 3, "valid_terrain": ["grassland", "plains"],
                 "requires_tech": None,               # available from the start
                 "yield_bonus": {"food": 1}, "label": "f" },
    "mine":    { "build_turns": 3, "valid_terrain": ["hills", "forest"],
                 "requires_tech": "mining",
                 "yield_bonus": {"prod": 1}, "label": "m" },
    "pasture": { "build_turns": 3, "valid_terrain": ["grassland", "plains"],
                 "requires_tech": "animal_husbandry",
                 "yield_bonus": {"prod": 1}, "label": "p" },
}
```

---

## Tech Tree

File: `data/techs.py`

```
ANCIENT ERA                         CLASSICAL ERA
──────────────────────────────────────────────────────────────
Mining ──────────► Bronze Working ──────────► Iron Working
                                              (Swordsman, Forge)
Animal Husbandry ───────────────────────────► Horseback Riding
                                              (Horseman)
Archery
Pottery ─────────────────────────────────► Writing ──► Mathematics
                                                    └──► Currency
```

Science costs: Mining/Animal Husbandry/Archery/Pottery = 35, Bronze Working = 55,
Iron Working/Horseback Riding/Writing = 80, Mathematics/Currency = 100.

Each tech has: `era`, `science_cost`, `prerequisites`, `unlocks_units`,
`unlocks_buildings`, `unlocks_improvements`, `reveals_resources`.

Research flow:
- Player sets `civ.current_research` via the tech screen (T key)
- Science accumulates each turn; tech completes when `science >= science_cost`
- Completion message queued in `civ.pending_messages` (shown next turn)
- Tech screen auto-opens on next turn so player can choose next research

---

## Yield Calculation

File: `systems/yields.py` — `compute_city_yields(city, tiles, civ) -> dict`

```python
totals = {"food": 0, "prod": 0, "gold": 0, "science": 0, "culture": 0}

for each (q, r) in city.worked_tiles:
    totals += TERRAIN_YIELDS[terrain]
    if resource is visible (requires_tech is None or tech researched):
        totals += resource["yield_bonus"]
    if improvement exists:
        totals += IMPROVEMENT_DEFS[improvement]["yield_bonus"]
    if "forge" in city.buildings and terrain == "hills":
        totals["prod"] += 1           # Forge: +1 prod per hills tile worked

for each building in city.buildings:
    totals += building["effects"]     # food/prod/gold/science/culture per turn
    totals["gold"] -= building["maintenance"]

# Base science (always applied)
totals["science"] += 1 + city.population
# Science per city = 1 (base) + population + 2 (Library) = up to pop+3 with Library
```

---

## Combat System

File: `systems/combat.py`

```python
def calc_damage(attacker_str, defender_str) -> int:
    diff = attacker_str - defender_str
    return max(1, min(50, int(30 * exp(0.04 * diff))))

def effective_strength(unit, tile, vs_unit_type=None) -> float:
    base          = UNIT_DEFS[unit.unit_type]["strength"]
    terrain_bonus = TERRAIN_DEFENSE_BONUS[tile.terrain]     # 0 or 0.25
    fortify_bonus = unit.fortify_bonus                       # 0.0 / 0.25 / 0.5
    hp_modifier   = 0.5 + 0.5 * (unit.hp / hp_max)         # 0.5 → 1.0
    unit_bonus    = bonus_vs.get(vs_unit_type, 0.0)         # e.g. Spearman vs Horseman
    return base * (1 + terrain_bonus + fortify_bonus + unit_bonus) * hp_modifier

def melee_attack(attacker, defender, attacker_tile, defender_tile):
    # Both units take damage simultaneously
    a_str = effective_strength(attacker, attacker_tile, vs_unit_type=defender.unit_type)
    d_str = effective_strength(defender, defender_tile, vs_unit_type=attacker.unit_type)
    attacker.hp -= calc_damage(d_str, a_str)   # defender retaliates
    defender.hp -= calc_damage(a_str, d_str)   # attacker strikes

def ranged_attack(attacker, defender, defender_tile):
    # Only defender takes damage (no retaliation)
    a_str = ranged_strength (or strength if no ranged_strength defined)
    defender.hp -= calc_damage(a_str, effective_strength(defender, defender_tile))

def bombard_city(attacker, city):
    a_str = ranged_strength (or strength)
    # bonus_vs_city multiplier applied if defined (Catapult: 2.0 → 3× city damage)
    dmg = max(1, min(20, int(a_str * 0.4)))
    city.hp -= dmg
```

**City capture**: melee unit defeats last defender (or attacks undefended city to 0 HP)
→ attacker moves in, city transfers owner, all territory tiles within radius 3 transfer.
If old owner loses all cities → eliminated (all units removed, skipped in turn order).

---

## Movement

File: `entities/unit.py`

```python
def get_reachable_tiles(unit, tiles, turn=99) -> dict {(q,r): cost}
```

BFS. Entry cost = `TERRAIN_MOVE_COST[terrain]`.

**Civilian rules** (Settler, Worker):
- Blocked by **any** civilian on destination tile (own or enemy)
- Blocked by enemy military
- On turn 1: also blocked by tiles containing any enemy settler

**Military rules** (Warrior, Spearman, etc.):
- Blocked by friendly military
- Enemy military tile: attackable (shown red), not in reachable set
- Enemy undefended city: BFS passes through but cannot end there
- Enemy civilian tile: reachable (captures civilian on move), cannot pass through
- On turn 1: tiles with enemy settlers are impassable

```python
def get_attackable_tiles(unit, tiles) -> set {(q,r)}
```

Returns empty set if unit is civilian or has 0 moves left.
- Melee (range 1): adjacent tiles with any enemy unit, civilian, or city
- Ranged: all tiles within `hex_distance <= range` with enemy unit, civilian, or city

---

## Turn Processing

File: `game.py` — `end_turn()`

```
for each city in civ.cities:
    food_stored += yields["food"] - population * 2
    food_stored = max(0, food_stored)
    if food_stored >= food_growth_threshold:
        population += 1; food_stored = 0; re-assign worked_tiles

    civ.gold    += yields["gold"]      # net of building maintenance
    civ.science += yields["science"]
    civ.culture += yields["culture"]

    city.culture_stored += yields["culture"]
    while city.culture_stored >= 20:
        city.culture_stored -= 20
        _expand_border(civ)            # claim 1 best adjacent unclaimed tile

    city.hp = min(50, city.hp + 5)    # city HP regenerates 5/turn

# Unit maintenance
for each military unit: civ.gold -= 1

# Research completion
if current_research and science >= cost:
    science -= cost
    techs_researched.add(key)
    pending_messages.append("{tech} researched!")
    research_just_completed = True
    current_research = None

# Worker improvements
for each worker building: build_turns_left -= 1
    if build_turns_left == 0: tile.improvement = key

# Production
for each city:
    production_progress += yields["prod"]
    if progress >= cost:
        complete item; progress -= cost
        pending_messages.append("{city}: {item} built/trained!")

# Unit reset
for each unit:
    if healing:
        heal_amount = 20 if tile.owner == civ.player_index else 10
        unit.hp = min(hp_max, unit.hp + heal_amount)
    unit.moves_left = UNIT_DEFS[type]["moves"]
    if fortified: fortify_bonus = min(0.5, fortify_bonus + 0.25)

# Bankruptcy
if civ.gold < 0:
    lose one random military unit OR non-palace building
    civ.gold = 0
    pending_messages.append("Bankruptcy! {item} lost")

# Advance to next non-eliminated player
# self.turn increments when wrapping back to player 0
```

---

## Hotseat Turn Flow

When a player presses Enter or clicks END TURN (`_do_end_turn` in `main.py`):

1. `game.end_turn()` processes all turn logic and advances `current_player`
2. Camera centers on new player's **original capital** (or their settler if no capital yet)
3. Turn banner: `"[Player Name]'s Turn — Turn N"` shown for 120 frames (2 seconds)
4. Player clicks or presses any key to dismiss the banner
5. On dismiss: `civ.pending_messages` shown as popup notification; if
   `research_just_completed`, tech screen opens automatically

---

## Economy Summary

```
Per-turn gold (net) =
    Σ cities:
        terrain gold yields
      + building gold bonuses (Palace +3, Market +2)
      − building maintenance (Granary −1, Library −1, Forge −1)
    − 1 per military unit

If gold ends turn negative:
    → lose 1 random military unit or non-palace building
    → gold reset to 0
    → notification queued for next turn
```

---

## Victory Condition

**Domination**: own all original capitals (first city of each player).

- Checked after every attack
- **Not checked on turn 1** — prevents instant win before all players settle
- Eliminated player (all cities lost): units removed, skipped in turn order

---

## Camera

```python
class Camera:
    offset_x, offset_y: float   # pan offset in pixels
    zoom: int                    # 1 = full size (HEX_SIZE=72), 0 = 60% (≈43px)

    effective_hex_size() -> int
    pan(dx, dy)                  # move + clamp to map bounds (80px margin)
    center_on_pixel(px, py)      # snap camera to pixel + clamp
```

Auto-centers on the new player's original capital at each turn handoff.
If the player has no capital yet, centers on their settler.

---

## Input Handling

**Keyboard:**

| Key        | Action |
|------------|--------|
| Enter      | End turn |
| Arrow keys | Pan camera (8px per frame) |
| T          | Toggle tech screen |
| B          | Open city screen (selected city, or city at selected unit's tile) |
| Escape     | Close modal → deselect |
| F          | Found city (Settler only) |
| A          | Build Farm (Worker only) |
| M          | Build Mine (Worker only) |
| P          | Build Pasture (Worker only) |
| K          | Fortify unit (military only) |
| H          | Heal unit — only if at full movement points (military only) |

**Mouse:**

| Button       | Action |
|--------------|--------|
| Left click   | Select unit / move / attack / city screen item / end turn button |
| Right click  | Deselect |
| Middle drag  | Pan camera |
| Scroll up    | Zoom in  (or scroll city list up when city screen open) |
| Scroll down  | Zoom out (or scroll city list down when city screen open) |

---

## Rendering Layers

File: `ui/renderer.py` — `render(screen, game, camera, ui_state)`

```
Layer  1 — Background fill (dark blue)
Layer  2 — Terrain hexes (filled polygons + black border)
Layer  3 — Territory border lines (player color on edges where owner changes)
Layer  4 — Resources (colored dot, only if revealed to current player)
Layer  5 — Improvement labels ("f", "m", "p" in yellow)
Layer  6 — Movement/attack overlays
             yellow fill + border = reachable tiles
             red fill + border    = attackable tiles
Layer  7 — Cities
             colored circle, name above, population inside
             gold ring if original capital
             HP bar if damaged
Layer  8 — Units
             colored circle, label text
             civilian: offset (+x, +y) to avoid overlap with military
             blue ring = fortified, green ring = healing
             dim overlay if no moves left (current player only)
             "[N]" counter if building improvement
             HP bar if damaged
Layer  9 — Selection ring (yellow hex outline on selected tile/unit)
Layer 10 — HUD (bottom info bar)
Layer 11 — Tech screen modal (if open)
Layer 12 — City screen modal (if open)
Layer 13 — Notification popup (multi-line, semi-transparent, auto-dismiss 3 sec)
Layer 14 — Turn banner (hotseat handoff, dismissible by click/key)
Layer 15 — Win screen (domination victory overlay, blocks all input)
```

---

## HUD Layout

Bottom bar: full width × 180px.

```
Left half                                  Right half
──────────────────────────────────────────────────────────────
[Unit: name, HP, moves, strength]          Turn N
[City: name, pop, food stored, yields]     Player X  (in player color)
[Tile: terrain, resource, yields]          Gold: 12   Sci: 45/80   Mining
[Context hints]                            [control hints]
                                                       [END TURN]
```

END TURN button: `(SCREEN_W − 220, SCREEN_H − 66, 200 × 48)`.

---

## City Screen

Centered modal: `720 × 620 px`.

Contents (top to bottom):
1. Header: city name, population
2. Yields row: Food / Prod / Gold / Sci / Culture
3. Food progress: stored/threshold, net/turn, turns to grow
4. Production section: current item progress bar + turns remaining (or "nothing queued")
5. Buildings list (all built buildings except palace)
6. Scrollable build list: available units and buildings
   - Filtered by tech requirements and resource availability
   - Shows prod cost and turns to build at current yield
   - Click to enqueue (or dequeue if already queued)
7. Scrollbar on right edge (if list overflows)
8. Close button (bottom-right)

Scroll with mouse wheel when city screen is open.

---

## Tech Screen

Full-screen semi-transparent overlay. Tech nodes as rounded rectangles, arranged
in two era columns with prerequisite arrows between them.

Node states:
- **Green fill** — already researched
- **Blue pulsing** — currently being researched (progress shown)
- **White/light** — prerequisites met, available to choose
- **Dark grey** — locked (prerequisites not met)

Click a node to set it as `current_research`. Click outside panel or press Escape
to close. Prerequisite arrows colored by research state.

---

## Notifications

Two classes of notifications:

**Immediate** (combat): attack results, captures, eliminations — shown at once as
centered popup, auto-dismiss after 3 seconds.

**Queued** (end-of-turn events): tech completions, unit/building completions,
bankruptcy — stored in `civ.pending_messages`, shown at the **start of that
player's next turn** after the turn banner is dismissed. Multiple messages stack
in one popup. If a tech completed, the tech screen also opens automatically.
