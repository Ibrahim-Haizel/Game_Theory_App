"""Data models and helper loaders for Battleship Treasure Hunt."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, FrozenSet, Optional
import json

# ---------- Basic types -----------------------------------------------------

@dataclass
class Player:  # noqa: D101
    name: str
    clue: str
    weight: int = 1
    color: Tuple[int, int, int] = (0, 0, 0)  # RGB for UI highlights

    def get_short_name(self) -> str:
        """Return the player's initial (first letter of name)."""
        return self.name[0].upper() if self.name else "?"

    def allowed_positions(self, grid_size: int) -> set[tuple[int, int]]:
        """Support specialized truth-based clue types by detecting keywords."""
        clue = self.clue.lower()
        # 1) Shallow-Sea Scout: rows 0 through 3
        if "no deeper" in clue or "northern edge" in clue:
            return {(r, c) for r in range(0, min(4, grid_size)) for c in range(grid_size)}
        # 2) Prime Numerist: columns 2,3,5,7 (0-based primes)
        if "prime sentinel" in clue or "prime" in clue:
            primes = {2, 3, 5, 7}
            return {(r, c) for r in range(grid_size) for c in primes if c < grid_size}
        # 3) Parity Jester: (row+col)%2 == 1
        if "odd laugh" in clue or "parity" in clue:
            return {(r, c) for r in range(grid_size) for c in range(grid_size) if (r + c) % 2 == 1}
        # 4) Humble Tactician: row < col
        if "rank is strictly smaller" in clue or "bows to the column" in clue:
            return {(r, c) for r in range(grid_size) for c in range(grid_size) if r < c}
        # 5) Western Cartographer: columns >= 6 (east of F)
        if "east of" in clue and "f" in clue:
            return {(r, c) for r in range(grid_size) for c in range(6, grid_size)}
        # 6) Three-Beat Chronomancer: row%3 == 2
        if "second beat" in clue or "in threes" in clue or "chronomancer" in clue:
            return {(r, c) for r in range(grid_size) for c in range(grid_size) if r % 3 == 2}
        # Fallback: allow full grid
        return {(r, c) for r in range(grid_size) for c in range(grid_size)}


@dataclass
class Treasure:  # noqa: D101
    value: int
    claimed: bool = False


Grid = List[List[Optional[Treasure]]]
Coalition = FrozenSet[int]  # index set → immutable & hashable


# ---------- JSON helpers ----------------------------------------------------

COLOR_PALETTE: list[Tuple[int, int, int]] = [
    (255, 99, 71),    # tomato
    (148, 0, 211),   # dark-violet (replaced medium-sea-green)
    (65, 105, 225),   # royal‑blue
    (238, 130, 238),  # violet
    (255, 215, 0),    # gold
    (255, 140, 0),    # dark‑orange
]


def load_clues(json_path: Path) -> List[Player]:
    """Load *players* array from ``clues.json`` and return ``Player`` objects."""
    data = json.loads(json_path.read_text())
    players = []
    for idx, p_data in enumerate(data["players"]):
        # Assign color from palette or use default if palette runs out
        player_color = p_data.get("color") # Allow overriding color in JSON
        if not player_color:
             player_color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]

        players.append(
            Player(
                name=p_data["name"],
                clue=p_data["clue"],
                weight=p_data.get("weight", 1),
                color=tuple(player_color), # Ensure it's a tuple
            )
        )
    return players


def make_empty_grid(size: int) -> Grid:
    """Return empty *size × size* grid of ``None``."""
    return [[None for _ in range(size)] for _ in range(size)]


def load_board(json_path: Optional[Path], size: int) -> Grid:
    """Return grid populated with treasures; randomise if *json_path* missing."""
    import random

    grid = make_empty_grid(size)

    if json_path and json_path.exists():
        data = json.loads(json_path.read_text())
        treasures = data.get("treasures", [])
        if treasures:
            t = treasures[0]
            grid[t["row"]][t["col"]] = Treasure(value=t["value"])
    else:
        # Random scatter: place exactly one treasure with random coin value
        r, c = random.randrange(size), random.randrange(size)
        grid[r][c] = Treasure(value=random.choice([20, 40, 60, 80]))
    return grid
