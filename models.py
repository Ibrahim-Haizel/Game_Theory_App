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
        """Parse the clue into a set of allowed (row, col) positions on the grid."""
        import re
        positions: set[tuple[int,int]] = set()
        clue_lower = self.clue.lower()
        # Pattern: Row is N
        m_row = re.search(r"row\s+is\s+(\d+)", clue_lower)
        if m_row:
            r = int(m_row.group(1)) - 1
            if 0 <= r < grid_size:
                for c in range(grid_size):
                    positions.add((r, c))
        # Pattern: Column is Letter
        m_col = re.search(r"column\s+is\s*([a-zA-Z])", clue_lower)
        if m_col:
            c_letter = m_col.group(1).upper()
            c = ord(c_letter) - ord('A')
            if 0 <= c < grid_size:
                for rr in range(grid_size):
                    positions.add((rr, c))
        # If no specific parse, allow all
        if not positions:
            positions = {(rr, cc) for rr in range(grid_size) for cc in range(grid_size)}
        return positions


@dataclass
class Treasure:  # noqa: D101
    value: int
    claimed: bool = False


Grid = List[List[Optional[Treasure]]]
Coalition = FrozenSet[int]  # index set → immutable & hashable


# ---------- JSON helpers ----------------------------------------------------

COLOR_PALETTE: list[Tuple[int, int, int]] = [
    (255, 99, 71),    # tomato
    (60, 179, 113),   # medium‑sea‑green
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
        for t in data["treasures"]:
            grid[t["row"]][t["col"]] = Treasure(value=t["value"])
    else:
        # --- Random scatter: ~size treasures, coin values 20–80 -------------
        for _ in range(size):
            r, c = random.randrange(size), random.randrange(size)
            if grid[r][c] is None:
                grid[r][c] = Treasure(value=random.choice([20, 40, 60, 80]))
    return grid
