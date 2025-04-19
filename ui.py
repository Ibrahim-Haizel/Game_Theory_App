"""UI components (buttons, grid, panels) for the game – no external deps."""
from __future__ import annotations

import pygame as pg
from typing import Callable, Tuple, List, Dict, Set, Optional

# Assuming models.py has Player defined
from models import Player

pg.init()
pg.font.init()  # Ensure font module is initialized

Font = pg.font.SysFont("consolas", 16)
FontSmall = pg.font.SysFont("consolas", 12)

COLOR_INACTIVE = pg.Color('lightskyblue3')
COLOR_ACTIVE = pg.Color('dodgerblue2')
TEXT_COLOR = pg.Color('black')

# Simple TextInput for setup phase (can be expanded)
class TextInput:
    def __init__(self, rect: pg.Rect, prompt: str):
        self.rect = rect
        self.prompt = prompt
        self.text = ""
        self.active = False
        self.color = COLOR_INACTIVE
        self.prompt_surface = Font.render(prompt, True, TEXT_COLOR)
        self.txt_surface = Font.render(self.text, True, TEXT_COLOR)

    def handle_event(self, event: pg.event.Event):
        if event.type == pg.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = not self.active
            else:
                self.active = False
            self.color = COLOR_ACTIVE if self.active else COLOR_INACTIVE
        if event.type == pg.KEYDOWN:
            if self.active:
                if event.key == pg.K_RETURN:
                    print(f"Input finalized: {self.text}")  # Or call a callback
                    self.active = False
                    self.color = COLOR_INACTIVE
                elif event.key == pg.K_BACKSPACE:
                    self.text = self.text[:-1]
                else:
                    # Basic validation - allow only digits for now
                    if event.unicode.isdigit():
                        self.text += event.unicode
                self.txt_surface = Font.render(self.text, True, TEXT_COLOR)

    def draw(self, screen: pg.Surface):
        # Draw prompt to the left of the box
        screen.blit(self.prompt_surface, (self.rect.x - self.prompt_surface.get_width() - 10, self.rect.y + 5))
        # Draw the input box
        pg.draw.rect(screen, self.color, self.rect, 2)
        screen.blit(self.txt_surface, (self.rect.x + 5, self.rect.y + 5))
        # Make box slightly wider to fit text
        self.rect.w = max(200, self.txt_surface.get_width() + 10)

    def get_text(self) -> str:
        return self.text


class Button:  # noqa: D101
    def __init__(
        self,
        rect: pg.Rect,
        text: str,
        onclick: Callable[[], None],
        toggle: bool = False,
        *,
        font: pg.font.Font = Font,
        color: Tuple[int, int, int] = (30, 144, 255),  # Dodger Blue
        active_color: Tuple[int, int, int] = (34, 139, 34),  # Forest Green (for toggle)
        text_color: Tuple[int, int, int] = (255, 255, 255),  # White
        text_hover_color: Optional[Tuple[int, int, int]] = None, # Optional hover text color
    ) -> None:
        self.rect, self.text, self.onclick, self.toggle = rect, text, onclick, toggle
        self.font, self.color, self.active_color, self.text_color = font, color, active_color, text_color
        
        # Ensure text_hover_color is always initialized
        if text_hover_color is None:
            tr, tg, tb = self.text_color # Use self.text_color which is guaranteed to exist
            self.text_hover_color = (min(tr + 50, 255), min(tg + 50, 255), min(tb + 50, 255))
        else:
            self.text_hover_color = text_hover_color
            
        self.active = False  # Tracks toggle state
        self._is_hovered = False  # For visual feedback

    def handle_event(self, event: pg.event.Event) -> None:
        if event.type == pg.MOUSEMOTION:
            self._is_hovered = self.rect.collidepoint(event.pos)
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.toggle:
                    self.active = not self.active
                self.onclick()
                # Prevent immediate re-toggle on fast clicks for toggle buttons?
                # Might need debounce logic if it becomes an issue.

    def draw(self, surf: pg.Surface) -> None:
        border_color = (0, 0, 0)
        current_bg_color = self.color
        current_text_color = self.text_color # Default text color

        if self.toggle and self.active:
            current_bg_color = self.active_color

        if self._is_hovered:
            r, g, b = current_bg_color
            hover_bg_color = (min(r + 30, 255), min(g + 30, 255), min(b + 30, 255))
            pg.draw.rect(surf, hover_bg_color, self.rect)
            current_text_color = self.text_hover_color # Use hover text color
        else:
            pg.draw.rect(surf, current_bg_color, self.rect)

        pg.draw.rect(surf, border_color, self.rect, 2)  # Draw border

        # --- Text Wrapping ---
        padding = 5
        max_width = self.rect.width - 2 * padding
        words = self.text.split(' ')
        lines = []
        current_line = ""
        
        if not self.text.strip():
            return # Nothing to draw if text is empty

        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            test_size = self.font.size(test_line)
            
            if test_size[0] <= max_width:
                current_line = test_line
            else:
                if current_line: # Add the completed line
                    lines.append(current_line)
                # Handle word longer than max_width - just add it, will be clipped
                if self.font.size(word)[0] > max_width:
                     lines.append(word)
                     current_line = ""
                else: # Start new line with current word
                     current_line = word
        
        if current_line: # Add the last line
            lines.append(current_line)

        # --- Render and Blit Lines ---
        line_height = self.font.get_linesize()
        total_height = len(lines) * line_height
        start_y = self.rect.centery - total_height // 2

        for i, line in enumerate(lines):
            line_surf = self.font.render(line, True, current_text_color)
            line_rect = line_surf.get_rect(centerx=self.rect.centerx, top=start_y + i * line_height)

            # Clip and draw
            clip_rect = line_rect.clip(self.rect)
            source_area = clip_rect.move(-line_rect.left, -line_rect.top)
            
            if clip_rect.width > 0 and clip_rect.height > 0:
                surf.blit(line_surf, clip_rect.topleft, area=source_area)


class GridView:  # noqa: D101
    def __init__(
        self,
        topleft: Tuple[int, int],
        size_px: int,
        n: int,
        onclick: Callable[[int, int], None],
    ) -> None:
        self.x0, self.y0 = topleft
        self.size_px, self.n, self.onclick = size_px, n, onclick
        self.cell_size = size_px // n

    def handle_event(self, event: pg.event.Event) -> None:  # noqa: D401, D102
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            if self.x0 <= x < self.x0 + self.size_px and self.y0 <= y < self.y0 + self.size_px:
                r = (y - self.y0) // self.cell_size
                c = (x - self.x0) // self.cell_size
                # Check bounds just in case
                if 0 <= r < self.n and 0 <= c < self.n:
                    self.onclick(r, c)

    def draw(
        self,
        surf: pg.Surface,
        revealed: List[Tuple[int, int, bool]],
        grid: List[List[Optional['Treasure']]],
        allowed: Optional[Set[Tuple[int, int]]] = None,
        clue_positions: List[Tuple[int, Set[Tuple[int, int]], bool]] = None,
        players: Optional[List['Player']] = None,
    ) -> None:
        # Board background
        bg_rect = pg.Rect(self.x0, self.y0, self.size_px, self.size_px)
        pg.draw.rect(surf, (20, 20, 20), bg_rect)  # Dark background for the grid

        # Player-specific clue outlines (each player gets a different color)
        if clue_positions:
            # Draw each player's clue area with their assigned color
            for (player_idx, positions, is_restrictive) in clue_positions:
                # Determine player color (ensure it exists)
                if players and 0 <= player_idx < len(players):
                    player_color = players[player_idx].color
                else:
                    player_color = (255, 0, 0) # Default red if player not found
                
                # Use the player's exact color for the outline
                outline_color = player_color 

                if is_restrictive:
                    # Restrictive: Draw outlines for specific cells directly onto the main surface
                    outline_thickness = 3 
                    for (r_idx, c_idx) in positions:
                        cell_x = self.x0 + c_idx * self.cell_size
                        cell_y = self.y0 + r_idx * self.cell_size
                        cell_rect = pg.Rect(cell_x, cell_y, self.cell_size, self.cell_size)
                        # Draw directly onto surf, no intermediate alpha surface
                        pg.draw.rect(surf, outline_color, cell_rect, outline_thickness) 
                else:
                    # Non-restrictive: Draw outline around the entire grid perimeter
                    perimeter_rect = pg.Rect(self.x0, self.y0, self.size_px, self.size_px)
                    outline_thickness = 4 
                    pg.draw.rect(surf, outline_color, perimeter_rect, outline_thickness)

        # Highlight allowed guess cells
        if allowed is not None:
            # translucent highlight surface
            hl = pg.Surface((self.cell_size, self.cell_size), pg.SRCALPHA)
            hl.fill((0, 255, 0, 50))  # semi-transparent green
            for (r, c) in allowed:
                rect = pg.Rect(
                    self.x0 + c * self.cell_size,
                    self.y0 + r * self.cell_size,
                    self.cell_size,
                    self.cell_size,
                )
                surf.blit(hl, rect.topleft)

        # Draw revealed treasures first (optional)
        for r in range(self.n):
            for c in range(self.n):
                cell_rect = pg.Rect(self.x0 + c * self.cell_size, self.y0 + r * self.cell_size, self.cell_size, self.cell_size)
                cell = grid[r][c]
                if cell and cell.claimed:
                    # Draw a coin or value perhaps?
                    coin_color = (255, 215, 0)  # Gold
                    pg.draw.circle(surf, coin_color, cell_rect.center, self.cell_size // 4)
                    value_txt = FontSmall.render(str(cell.value), True, (0, 0, 0))
                    txt_rect = value_txt.get_rect(center=cell_rect.center)
                    surf.blit(value_txt, txt_rect)

        # Draw hit/miss markers over treasure display
        for r, c, hit in revealed:
            center = (
                self.x0 + c * self.cell_size + self.cell_size // 2,
                self.y0 + r * self.cell_size + self.cell_size // 2,
            )
            color = (34, 139, 34) if hit else (178, 34, 34)  # Green for hit, Red for miss
            pg.draw.circle(surf, color, center, self.cell_size // 3)
            # Optionally draw an X for miss, checkmark for hit?
            # ... (add drawing code here if desired)

        # Grid lines (draw last, on top)
        line_color = (100, 100, 100)  # Grey grid lines
        line_thickness = 1 # Reverted thickness
        label_margin = 8 # Increased margin for labels
        for i in range(self.n + 1):
            # verticals
            pg.draw.line(surf, line_color, (self.x0 + i * self.cell_size, self.y0), (self.x0 + i * self.cell_size, self.y0 + self.size_px), line_thickness)
            # horizontals
            pg.draw.line(surf, line_color, (self.x0, self.y0 + i * self.cell_size), (self.x0 + self.size_px, self.y0 + i * self.cell_size), line_thickness)
        # Draw column labels (A, B, C, ...)
        for c in range(self.n):
            letter = chr(ord('A') + c)
            label_surf = FontSmall.render(letter, True, TEXT_COLOR)
            x = self.x0 + c * self.cell_size + self.cell_size // 2
            # Adjusted y for increased margin
            y = self.y0 - label_surf.get_height() // 2 - label_margin 
            surf.blit(label_surf, (x - label_surf.get_width() // 2, y))
        # Draw row labels (1, 2, 3, ...)
        for r in range(self.n):
            number = str(r + 1)
            label_surf = FontSmall.render(number, True, TEXT_COLOR)
            # Adjusted x for increased margin
            x = self.x0 - label_surf.get_width() // 2 - label_margin
            y = self.y0 + r * self.cell_size + self.cell_size // 2 - label_surf.get_height() // 2
            surf.blit(label_surf, (x, y))


# --- NEW: PlayerPanel --- needs Player from models.py
class PlayerPanel:
    def __init__(self, rect: pg.Rect, players: List[Player], commit_callback: Callable[[int], None]):
        self.rect = rect
        self.players = players
        self.commit_callback = commit_callback
        self.commit_states = [False] * len(players)
        self.reveal_coalition: Set[int] = set()
        self.buttons: List[Button] = []
        self._create_player_widgets()

    def _create_player_widgets(self):
        self.buttons = []
        y_offset = self.rect.y + 5
        widget_h = 35  # Height for each player row
        toggle_w = 20
        name_w = 100

        for i, player in enumerate(self.players):
            # Commit Toggle (using a Button)
            toggle_rect = pg.Rect(self.rect.x + 5, y_offset + 5, toggle_w, toggle_w)
            # Use a lambda that captures the current player index 'i'
            callback = (lambda idx=i: self.commit_callback(idx))
            commit_button = Button(toggle_rect, "", callback, toggle=True, color=(200, 200, 200), active_color=player.color)
            self.buttons.append(commit_button)

            # Player Name/Initial Label (drawn directly)
            # Clue Text Label (drawn conditionally)
            y_offset += widget_h

    def update_commits(self, commit_states: List[bool]):
        self.commit_states = commit_states
        for i, button in enumerate(self.buttons):
            button.active = commit_states[i]

    def reveal_clues(self, coalition_indices: Set[int]):
        self.reveal_coalition = coalition_indices
        # Disable toggles after revealing?
        # for button in self.buttons: button.disabled = True # Need to add disabled state to Button

    def reset_view(self):
        self.reveal_coalition = set()
        self.commit_states = [False] * len(self.players)
        for button in self.buttons:
            button.active = False
            # button.disabled = False # Re-enable toggles

    def handle_event(self, event: pg.event.Event):
        for button in self.buttons:
            button.handle_event(event)

    def draw(self, screen: pg.Surface):
        pg.draw.rect(screen, (220, 220, 220), self.rect)  # Light grey background
        pg.draw.rect(screen, (0, 0, 0), self.rect, 1)  # Border
        y_offset = self.rect.y + 5
        widget_h = 35

        # --- Determine which clues are restrictive (useful) ---
        all_committed = len(self.reveal_coalition) == len(self.players) and len(self.players) > 0
        grid_size = 10  # Default, or could be passed in
        clue_types = []
        if all_committed:
            for player in self.players:
                pos = player.allowed_positions(grid_size)
                if len(pos) == grid_size * grid_size:
                    clue_types.append('nonrestrictive')
                else:
                    clue_types.append('restrictive')
        else:
            clue_types = [None] * len(self.players)

        for i, player in enumerate(self.players):
            # Draw Commit Toggle
            self.buttons[i].draw(screen)

            # Draw Player Name
            name_color = player.color if hasattr(player, 'color') else (0, 0, 0)
            name_txt = Font.render(f"{player.get_short_name()}: {player.name}", True, name_color)
            name_pos = (self.rect.x + 30, y_offset + 8)
            screen.blit(name_txt, name_pos)

            # Draw Clue if revealed for this player
            if i in self.reveal_coalition:
                clue_txt = FontSmall.render(f"   Clue: {player.clue}", True, (50, 50, 50))
                clue_pos = (self.rect.x + 30, y_offset + 22)
                screen.blit(clue_txt, clue_pos)
            else:
                clue_txt = FontSmall.render("   Clue: [Hidden]", True, (150, 150, 150))
                screen.blit(clue_txt, (self.rect.x + 30, y_offset + 22))

            y_offset += widget_h


class LedgerPanel:  # noqa: D101
    def __init__(self, rect: pg.Rect):
        self.rect = rect
        self.scroll = 0
        self.font = Font
        self.font_small = FontSmall

    def draw(self, surf: pg.Surface, ledger_items: List[Tuple[Coalition, int]], players: List[Player]):
        pg.draw.rect(surf, (245, 245, 245), self.rect)  # Background
        pg.draw.rect(surf, (0, 0, 0), self.rect, 2)  # Border
        header = self.font.render("Coalition      Coins", True, (0, 0, 0))
        surf.blit(header, (self.rect.x + 4, self.rect.y + 4))
        pg.draw.line(surf, (150, 150, 150), (self.rect.x, self.rect.y + 22), (self.rect.right, self.rect.y + 22), 1)

        y = self.rect.y + 26 - self.scroll
        max_y = self.rect.bottom - 5

        # Draw ledger entries (newest first)
        for coalition_indices, coins in reversed(ledger_items):
            if y < self.rect.y + 24: break  # Don't draw above header
            if y > max_y: continue  # Simple clipping

            # Map indices to player short names
            try:
                names = "+".join(sorted(players[i].get_short_name() for i in coalition_indices))
            except IndexError:
                names = "ErrorIdx"  # Handle potential index error if players list changes
            except AttributeError:
                names = "NoShortName"  # Handle if get_short_name is missing

            txt = self.font_small.render(f"{names:<13} {coins:>5}", True, (0, 0, 0))
            surf.blit(txt, (self.rect.x + 4, y))
            y += 16  # Smaller font, less spacing
