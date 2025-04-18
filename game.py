"""Orchestrates state machine: setup → rounds → end‑game."""
from __future__ import annotations

import pygame as pg
from pathlib import Path
from typing import Dict, Tuple, List, FrozenSet, Optional
import io
import requests
import csv # For CSV export

from models import Player, Treasure, Grid, Coalition, load_clues, load_board
from shapley import shapley_sample
from ui import Button, GridView, LedgerPanel, Font, PlayerPanel, TextInput # Added PlayerPanel, TextInput

# ---------------------------------------------------------------------------
# Constants
TopBarH = 40 # Increased height for more info
WINDOW_W, WINDOW_H = 900, 700
GRID_PX = 650
RIGHT_W = WINDOW_W - GRID_PX
GRID_TOP_MARGIN = 20
GRID_LEFT_MARGIN = 20
PANEL_MARGIN = 10
BUTTON_H = 30
BG_COLOR = (240, 248, 255) # Alice Blue
GRID_BG_COLOR = (20, 20, 20) # Darker Grid BG
PLAYER_PANEL_Y = TopBarH + PANEL_MARGIN
PLAYER_PANEL_H = 300 # Allocate space for player panel
LEDGER_Y = PLAYER_PANEL_Y + PLAYER_PANEL_H + PANEL_MARGIN
LEDGER_H = WINDOW_H - LEDGER_Y - BUTTON_H - PANEL_MARGIN * 2 # Adjust height
RIGHT_PANEL_X = GRID_PX + PANEL_MARGIN
RIGHT_PANEL_W = RIGHT_W - PANEL_MARGIN * 2

# Game States
SETUP = "SETUP"
AWAIT_COMMIT = "AWAIT_COMMIT" # Waiting for players to toggle commits and press Lock
AWAIT_GUESS = "AWAIT_GUESS"   # Coalition locked, clues revealed, waiting for grid click
REVEAL = "REVEAL"             # Brief state to show hit/miss before resetting
END = "END"

class Game:
    # ---------- Lifecycle ---------------------------------------------------
    def __init__(self) -> None:
        pg.mixer.init()
        pg.font.init() # Ensure font module is initialized
        self.screen = pg.display.set_mode((WINDOW_W, WINDOW_H))
        pg.display.set_caption("Battleship Treasure Hunt")
        self.clock = pg.time.Clock()
        self.running = True
        self.font = Font # Use the font from ui.py

        # --- Game State ---
        self.state = SETUP
        self.players: List[Player] = []
        self.grid: Grid = []
        self.grid_size = 10 # Default, can be changed in setup
        self.ledger: Dict[Coalition, int] = {}
        self.revealed: List[Tuple[int, int, bool]] = [] # (r, c, hit)
        self.commits: List[bool] = []
        self.current_coalition: Coalition = frozenset()
        self.coalition_locked = False
        self.round = 0
        self.payouts: Optional[List[float]] = None
        self.last_guess_result: Optional[Tuple[int, int, bool, int]] = None # (r, c, hit, coins)

        # --- UI Widgets ---
        # Setup Screen UI (Example - needs proper implementation)
        self.setup_input = TextInput(pg.Rect(100, 100, 300, 30), "Enter number of players (3-6):")
        self.load_clues_button = Button(pg.Rect(100, 150, 150, 30), "Load Clues", self._load_clues_action)
        self.start_game_button = Button(pg.Rect(100, 200, 150, 30), "Start Game", self._start_game_action)

        # Play Screen UI (initialized in _start_game_action)
        self.grid_view: Optional[GridView] = None
        self.player_panel: Optional[PlayerPanel] = None # Placeholder for PlayerPanel
        self.ledger_panel = LedgerPanel(pg.Rect(RIGHT_PANEL_X, LEDGER_Y, RIGHT_PANEL_W, LEDGER_H))
        self.lock_coalition_button = Button(
            pg.Rect(RIGHT_PANEL_X, WINDOW_H - BUTTON_H - PANEL_MARGIN, RIGHT_PANEL_W // 2 - PANEL_MARGIN // 2, BUTTON_H),
            "Lock Coalition", self._lock_coalition_action
        )
        self.end_button = Button(
            pg.Rect(RIGHT_PANEL_X + RIGHT_PANEL_W // 2 + PANEL_MARGIN // 2, WINDOW_H - BUTTON_H - PANEL_MARGIN, RIGHT_PANEL_W // 2 - PANEL_MARGIN // 2, BUTTON_H),
            "End Game", self._confirm_end_game
        )

        # End Screen UI (initialized in _end_game)
        self.export_button: Optional[Button] = None
        self.restart_button: Optional[Button] = None

        # --- Sound ---
        self.sound_urls = {
            "hit": "https://raw.githubusercontent.com/simondevyoutube/ProceduralTerrain_Part1/master/tutorial/sounds/explosion1.wav",
            "miss": "https://raw.githubusercontent.com/simondevyoutube/ProceduralTerrain_Part1/master/tutorial/sounds/blip1.wav",
            "coin": "https://raw.githubusercontent.com/freesound/freesound/develop/freesound/data/sounds/coin1.wav", # Example coin sound
            "commit": "https://raw.githubusercontent.com/freesound/freesound/develop/freesound/data/sounds/click1.wav", # Example commit sound
        }
        self.sfx: Dict[str, Optional[pg.mixer.Sound]] = {
            name: self._load_wav(name, url) for name, url in self.sound_urls.items()
        }

    # ---------- Helpers -----------------------------------------------------
    @staticmethod
    def _load_wav(name: str, url: str) -> Optional[pg.mixer.Sound]:
        print(f"Attempting to load sound '{name}' from {url}...")
        if not url:
            print(f"Warning: No URL provided for sound '{name}'.")
            return None
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            wav_data = io.BytesIO(response.content)
            sound = pg.mixer.Sound(wav_data)
            print(f"Successfully loaded sound '{name}'.")
            return sound
        except requests.exceptions.RequestException as e:
            print(f"Error downloading sound '{name}': {e}")
            return None
        except pg.error as e:
            print(f"Error loading sound data for '{name}': {e}")
            return None
        except Exception as e:
             print(f"Unexpected error loading sound '{name}': {e}")
             return None

    def _play_sfx(self, name: str):
        if name in self.sfx and self.sfx[name]:
            self.sfx[name].play()
        else:
            print(f"Debug: Sound '{name}' not loaded or unavailable.")

    # ---------- State Transition Actions ------------------------------------

    def _load_clues_action(self):
        # Placeholder: Implement file dialog to select clues.json
        # For now, assumes default clues.json exists
        print("Load Clues button clicked (placeholder)")
        try:
            clues_path = Path("clues.json")
            if not clues_path.exists():
                 # Try demo clues if default not found
                 clues_path = Path("./demo_clues.json")
                 if not clues_path.exists():
                      print("Error: clues.json or demo_clues.json not found!")
                      return # Stay in setup
            self.players = load_clues(clues_path)
            self.commits = [False] * len(self.players)
            print(f"Loaded {len(self.players)} players from {clues_path}.")
            # Update setup UI if needed (e.g., show loaded player names)
        except Exception as e:
            print(f"Error loading clues: {e}")
            # Reset players if loading failed?
            self.players = []
            self.commits = []


    def _start_game_action(self):
        print("Start Game button clicked")
        
        # --- Get Player Count from TextInput ---
        try:
            num_players_str = self.setup_input.get_text()
            if not num_players_str:
                 print("Error: Please enter the number of players (3-6).")
                 return
            num_players = int(num_players_str)
            if not (3 <= num_players <= 6):
                 print(f"Error: Invalid number of players ({num_players}). Must be 3-6.")
                 return
        except ValueError:
            print(f"Error: Invalid input '{num_players_str}'. Please enter a number.")
            return
        
        # --- Load Clues (If not already loaded or if player count mismatch?) ---
        # Option 1: Assume clues are loaded via button first.
        if not self.players:
             print("Error: Load clues before starting.")
             return
        if len(self.players) != num_players:
             print(f"Error: Number of players entered ({num_players}) does not match loaded clues ({len(self.players)}).")
             # Optional: Try reloading default clues matching num_players? Requires changes to load_clues/JSON structure.
             # Or just force user to load correct file.
             print("Please load a clues file matching the entered number of players.")
             return

        # --- Initialize Play State (rest of the function remains the same) ---
        print(f"Starting game with {num_players} players...")
        self.grid = load_board(Path("board.json"), self.grid_size)
        self.ledger = {}
        self.revealed = []
        self.round = 1
        self.current_coalition = frozenset()
        self.coalition_locked = False
        self.last_guess_result = None

        self.grid_view = GridView(
            (GRID_LEFT_MARGIN, TopBarH + GRID_TOP_MARGIN),
            GRID_PX,
            self.grid_size,
            self._handle_grid_click
        )
        self.player_panel = PlayerPanel(
             pg.Rect(RIGHT_PANEL_X, PLAYER_PANEL_Y, RIGHT_PANEL_W, PLAYER_PANEL_H),
             self.players,
             self._handle_commit_toggle
        )
        self.state = AWAIT_COMMIT

    def _handle_commit_toggle(self, player_index: int):
         if self.state == AWAIT_COMMIT:
              # Allow toggling only before locking coalition
              self.commits[player_index] = not self.commits[player_index]
              if self.player_panel:
                   self.player_panel.update_commits(self.commits) # Update visual state
              self._play_sfx("commit")
         else:
              print("Cannot toggle commit - coalition locked or game not in commit phase.")


    def _lock_coalition_action(self):
        if self.state != AWAIT_COMMIT:
            print("Not in commit phase.")
            return
        
        committed_indices = {i for i, committed in enumerate(self.commits) if committed}
        if not committed_indices:
            print("No players committed. Cannot lock empty coalition.")
            return

        self.current_coalition = frozenset(committed_indices)
        self.coalition_locked = True
        if self.player_panel:
             self.player_panel.reveal_clues(self.current_coalition) # Show clues for committed players
        self.state = AWAIT_GUESS
        print(f"Coalition locked: {self.current_coalition}. Waiting for guess.")

    def _handle_grid_click(self, r: int, c: int):
        if self.state != AWAIT_GUESS:
            print("Not awaiting guess.")
            return
        if not self.coalition_locked:
             print("Coalition not locked yet!")
             return

        print(f"Grid clicked at ({r}, {c}) by coalition {self.current_coalition}")
        cell = self.grid[r][c]
        hit = bool(cell and not cell.claimed)
        coins = 0

        if hit:
            cell.claimed = True
            coins = cell.value
            self._play_sfx("hit")
            self._play_sfx("coin") # Play coin sound on hit
        else:
            self._play_sfx("miss")

        # Update Ledger
        self.ledger[self.current_coalition] = self.ledger.get(self.current_coalition, 0) + coins
        self.revealed.append((r, c, hit))
        self.last_guess_result = (r, c, hit, coins)

        # Check for game end condition
        if all(t is None or t.claimed for row in self.grid for t in row):
            print("All treasures claimed!")
            self._end_game()
        else:
            # Transition to reveal state briefly? Or directly to reset?
            # Let's reset directly for now
            self._reset_for_next_round()


    def _reset_for_next_round(self):
        self.round += 1
        self.current_coalition = frozenset()
        self.coalition_locked = False
        self.commits = [False] * len(self.players) # Reset commits
        if self.player_panel:
             self.player_panel.reset_view() # Hide clues, reset toggles visually
        self.state = AWAIT_COMMIT
        print(f"--- Starting Round {self.round} ---")

    def _confirm_end_game(self):
        # Optional: Add a confirmation dialog
        print("End Game button clicked.")
        self._end_game()

    def _end_game(self):
        if self.state == END: return # Already ended
        print("Ending game and calculating payouts...")
        self.state = END
        values = {k: v for k, v in self.ledger.items()}
        weights = [p.weight for p in self.players]
        try:
             # Use a slightly higher default sample count
             self.payouts = shapley_sample(values, len(self.players), weights, samples=10000)
             print(f"Shapley Payouts: {self.payouts}")
        except Exception as e:
             print(f"Error calculating Shapley values: {e}")
             self.payouts = None # Indicate calculation failure

        # Initialize End Screen UI
        self.export_button = Button(pg.Rect(WINDOW_W // 2 - 160, WINDOW_H - 60, 150, 30), "Export Results", self._export_results)
        self.restart_button = Button(pg.Rect(WINDOW_W // 2 + 10, WINDOW_H - 60, 150, 30), "Restart Game", self._restart_game)


    def _export_results(self):
        if self.state != END: return
        print("Exporting results...")
        filename = "game_results.csv"
        try:
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                # Header
                writer.writerow(["Coalition", "Total Coins Earned"])
                # Ledger Data
                for coalition_indices, coins in self.ledger.items():
                     coalition_names = "+".join(sorted(self.players[i].get_short_name() for i in coalition_indices))
                     writer.writerow([coalition_names, coins])
                # Empty row separator
                writer.writerow([])
                # Payouts
                writer.writerow(["Player", "Shapley Value (Coins)"])
                if self.payouts:
                     for i, player in enumerate(self.players):
                          writer.writerow([player.name, f"{self.payouts[i]:.2f}"])
                else:
                     writer.writerow(["Calculation Error", "N/A"])
            print(f"Results exported successfully to {filename}")
        except Exception as e:
            print(f"Error exporting results to CSV: {e}")


    def _restart_game(self):
        print("Restarting game...")
        # Reset all state by creating a new Game instance perhaps?
        # Or manually reset all variables:
        self.__init__() # Re-initialize the game object


    # ---------- Public API --------------------------------------------------
    def run(self) -> None:
        while self.running:
            # --- Event Handling ---
            events = pg.event.get()
            for event in events:
                if event.type == pg.QUIT:
                    self.running = False
                # Pass event to the handler for the current state
                self.handle_event(event)

            # --- Update ---
            self.update() # Currently empty, but good practice

            # --- Drawing ---
            self.draw() # Call main draw method
            pg.display.flip()

            self.clock.tick(60) # Limit FPS

        pg.quit()


    def handle_event(self, event: pg.event.Event) -> None:
        """Delegate event handling based on the current game state."""
        if self.state == SETUP:
            self._handle_setup_event(event)
        elif self.state == AWAIT_COMMIT:
            self._handle_await_commit_event(event)
        elif self.state == AWAIT_GUESS:
            self._handle_await_guess_event(event)
        elif self.state == REVEAL: # Currently unused, resets directly
             pass # Could add a timer here
        elif self.state == END:
            self._handle_end_event(event)

    def update(self) -> None:
        """Update game logic (e.g., animations, timers)."""
        # Placeholder for future updates
        pass

    def draw(self) -> None:
        """Draw the current game state to the screen."""
        self.screen.fill(BG_COLOR)
        self._draw_top_bar() # Draw common top bar

        if self.state == SETUP:
            self._draw_setup()
        elif self.state in [AWAIT_COMMIT, AWAIT_GUESS, REVEAL]:
            self._draw_play()
        elif self.state == END:
            self._draw_end()


    # ---------- State-Specific Event Handlers -------------------------------

    def _handle_setup_event(self, event: pg.event.Event):
         # Handle input for setup_input, button clicks
         self.setup_input.handle_event(event)
         self.load_clues_button.handle_event(event)
         self.start_game_button.handle_event(event)
         
         # Allow pressing Enter in the text box OR clicking Start button
         start_triggered = False
         if event.type == pg.KEYDOWN and event.key == pg.K_RETURN and self.setup_input.active:
             self.setup_input.active = False # Deactivate input on enter
             self.setup_input.color = COLOR_INACTIVE # Update color
             start_triggered = True
         # Check button clicks as well (handled by button.handle_event)
         # If start button was clicked, its onclick (_start_game_action) is called directly.
         
         # If Enter was pressed in the box, call the start action
         if start_triggered:
              self._start_game_action()

    def _handle_await_commit_event(self, event: pg.event.Event):
         if self.player_panel:
              self.player_panel.handle_event(event) # Handles commit toggles via callback
         self.lock_coalition_button.handle_event(event)
         self.end_button.handle_event(event) # End game always possible

    def _handle_await_guess_event(self, event: pg.event.Event):
         if self.grid_view:
              self.grid_view.handle_event(event) # Handles grid clicks
         self.end_button.handle_event(event) # End game always possible
         # Allow deselecting coalition? Maybe add a button later.

    def _handle_end_event(self, event: pg.event.Event):
         if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
              self.running = False # Allow closing end screen
         if self.export_button:
              self.export_button.handle_event(event)
         if self.restart_button:
              self.restart_button.handle_event(event)


    # ---------- State-Specific Draw Methods ---------------------------------

    def _draw_top_bar(self):
        bar_rect = pg.Rect(0, 0, WINDOW_W, TopBarH)
        pg.draw.rect(self.screen, (50, 50, 50), bar_rect) # Dark grey bar
        title_txt = self.font.render("Battleship Treasure Hunt", True, (255, 255, 255))
        self.screen.blit(title_txt, (10, 10))

        if self.state != SETUP:
             round_txt = self.font.render(f"Round: {self.round}", True, (255, 255, 255))
             self.screen.blit(round_txt, (WINDOW_W // 2 - 50, 10))

             coalition_str = "None"
             if self.current_coalition:
                  # Use short names (e.g., initials) if available
                  names = sorted(self.players[i].get_short_name() for i in self.current_coalition)
                  coalition_str = ",".join(names)
             coalition_txt = self.font.render(f"Coalition: {coalition_str}", True, (255, 255, 255))
             self.screen.blit(coalition_txt, (WINDOW_W - 250, 10))


    def _draw_setup(self):
        # Draw setup UI elements centered or positioned nicely
        title_txt = self.font.render("Game Setup", True, (0,0,0), BG_COLOR)
        self.screen.blit(title_txt, (WINDOW_W // 2 - title_txt.get_width() // 2, 50))

        self.setup_input.draw(self.screen)
        self.load_clues_button.draw(self.screen)
        self.start_game_button.draw(self.screen)

        # Display loaded players?
        if self.players:
             y = 250
             player_list_txt = self.font.render("Loaded Players:", True, (0,0,0))
             self.screen.blit(player_list_txt, (100, y))
             y += 20
             for player in self.players:
                  p_txt = self.font.render(f"- {player.name}", True, player.color)
                  self.screen.blit(p_txt, (120, y))
                  y += 20


    def _draw_play(self):
        # Draw Grid
        if self.grid_view:
            self.grid_view.draw(self.screen, self.revealed, self.grid) # Pass grid for potential treasure display

        # Draw Right Panel Elements
        if self.player_panel:
            self.player_panel.draw(self.screen)
        self.ledger_panel.draw(self.screen, list(self.ledger.items()), self.players) # Pass players for name mapping
        self.lock_coalition_button.draw(self.screen)
        self.end_button.draw(self.screen)

        # Highlight if coalition is locked and clues revealed?
        if self.state == AWAIT_GUESS:
             # Draw instruction text
             guess_txt = self.font.render("Click on the grid to make a guess!", True, (200, 0, 0))
             self.screen.blit(guess_txt, (GRID_LEFT_MARGIN, TopBarH + GRID_TOP_MARGIN + GRID_PX + 5))


    def _draw_end(self):
        y = 80
        header = self.font.render("Game Over – Shapley Payouts", True, (0, 0, 0))
        header_rect = header.get_rect(center=(WINDOW_W // 2, y))
        self.screen.blit(header, header_rect)
        y += 50

        if self.payouts is not None:
            total_ledger = sum(self.ledger.values())
            total_payout = sum(self.payouts)
            info_txt = self.font.render(f"Total Treasure Found: {total_ledger} coins. Total Payout: {total_payout:.2f} coins.", True, (50, 50, 50))
            info_rect = info_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(info_txt, info_rect)
            y += 30

        for i, p in enumerate(self.players):
                # Ensure payout list length matches player list
                if i < len(self.payouts):
                     payout_val = self.payouts[i]
                     txt = self.font.render(f"{p.name}: {payout_val:.2f} coins", True, p.color)
                     txt_rect = txt.get_rect(center=(WINDOW_W // 2, y))
                     self.screen.blit(txt, txt_rect)
                     y += 25
                else:
                     print(f"Warning: Payout list length mismatch for player {i}")
        else:
            error_txt = self.font.render("Error calculating Shapley values.", True, (255, 0, 0))
            error_rect = error_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(error_txt, error_rect)
            y += 30

        # Draw end screen buttons
        if self.export_button: self.export_button.draw(self.screen)
        if self.restart_button: self.restart_button.draw(self.screen)

# --- Entry Point (If this file is run directly, usually in main.py) ---
if __name__ == '__main__':
     print("This file contains the Game class. Run main.py to start.")
     # Basic test to check sound loading
     pg.init()
     game = Game()
     game._play_sfx("hit")
     game._play_sfx("miss")
     game._play_sfx("coin")
     pg.quit()
