from civ_game.data.techs import TECH_DEFS


def can_research(tech_key: str, techs_researched: set) -> bool:
    """Returns True if prerequisites are met and tech not yet researched."""
    if tech_key in techs_researched:
        return False
    return all(p in techs_researched for p in TECH_DEFS[tech_key]["prerequisites"])


def available_techs(techs_researched: set) -> list:
    """All techs whose prerequisites are met and not yet researched."""
    return [k for k in TECH_DEFS if can_research(k, techs_researched)]
