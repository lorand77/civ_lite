from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Civilization:
    player_index: int
    name: str
    color: tuple

    cities: list = field(default_factory=list)
    units: list = field(default_factory=list)

    gold: int = 0
    gold_per_turn: int = 0
    science: int = 0
    science_per_turn: int = 0
    culture: int = 0


    current_research: str | None = None
    techs_researched: set = field(default_factory=set)
    original_capital: object = None
    is_eliminated: bool = False
    pending_messages: list = field(default_factory=list)  # shown at start of next turn
    research_just_completed: bool = False  # set when a tech finishes this turn
    is_cpu: bool = False
