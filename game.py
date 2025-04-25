"""Orchestrates state machine: setup → rounds → end‑game."""
from __future__ import annotations

import pygame as pg
from pathlib import Path
from typing import Dict, Tuple, List, FrozenSet, Optional, Set
import io
import requests
import csv # For CSV export
import itertools # Need this for combinations

from models import Player, Treasure, Grid, Coalition, load_clues, load_board
from shapley import shapley_sample
from ui import Button, GridView, LedgerPanel, Font, FontSmall, PlayerPanel, TextInput, COLOR_INACTIVE # Added COLOR_INACTIVE

# ---------------------------------------------------------------------------
# Constants
TopBarH = 40 # Increased height for more info
WINDOW_W, WINDOW_H = 900, 700
GRID_PX = 600 # Decreased grid size
RIGHT_W = WINDOW_W - GRID_PX
GRID_TOP_MARGIN = 30 # Increased
GRID_LEFT_MARGIN = 30 # Increased
PANEL_MARGIN = 20 # Increased margin
BUTTON_H = 50 # Increased height for wrapped text
BG_COLOR = (240, 248, 255) # Alice Blue
GRID_BG_COLOR = (20, 20, 20) # Darker Grid BG
PLAYER_PANEL_Y = TopBarH + PANEL_MARGIN # Correctly uses PANEL_MARGIN
PLAYER_PANEL_H = 300 # Allocate space for player panel
LEDGER_Y = PLAYER_PANEL_Y + PLAYER_PANEL_H + PANEL_MARGIN # Correctly uses PANEL_MARGIN
LEDGER_H = WINDOW_H - LEDGER_Y - BUTTON_H - PANEL_MARGIN * 2 # Correctly uses PANEL_MARGIN
RIGHT_PANEL_X = GRID_PX + GRID_LEFT_MARGIN + PANEL_MARGIN # Adjusted to account for grid left margin
RIGHT_PANEL_W = WINDOW_W - RIGHT_PANEL_X - PANEL_MARGIN # Adjusted to account for new X and right margin

# Game States
SETUP = "SETUP"
AWAIT_COMMIT = "AWAIT_COMMIT" # Waiting for players to toggle commits and press Lock
AWAIT_GUESS = "AWAIT_GUESS"   # Coalition locked, clues revealed, waiting for grid click
REVEAL = "REVEAL"             # Brief state to show hit/miss before resetting
END = "END"

MAX_PLAYERS = 6
MIN_PLAYERS = 3

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
        self.allowed_guesses: set[tuple[int,int]] | None = None  # Allowed cells after lock
        self.clue_positions = []  # List of (player_idx, positions, is_restrictive) for grid highlighting
        self.setup_error_message = "" # To display errors on setup screen

        # --- Setup UI Widgets ---
        input_w = 300
        input_h = 30
        button_w = 150
        # Start with MIN_PLAYERS input boxes
        self.player_name_inputs: List[TextInput] = [
            TextInput(pg.Rect(0, 0, input_w, input_h), f"Player {i+1} Name:") 
            for i in range(MIN_PLAYERS)
        ]
        self.add_player_button = Button(pg.Rect(0, 0, button_w, input_h), "Add Player", self._add_player_action)
        self.start_game_button = Button(pg.Rect(0, 0, button_w, BUTTON_H), "Start Game", self._start_game_action) 

        # Play Screen UI (initialized in _start_game_action)
        self.grid_view: Optional[GridView] = None
        self.player_panel: Optional[PlayerPanel] = None # Placeholder for PlayerPanel
        # Use constants directly, as they are now calculated correctly at the top level
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

    def _add_player_action(self):
        """Adds a new player name input box if below the max limit."""
        if len(self.player_name_inputs) < MAX_PLAYERS:
            next_player_num = len(self.player_name_inputs) + 1
            input_w = 300
            input_h = 30
            new_input = TextInput(pg.Rect(0, 0, input_w, input_h), f"Player {next_player_num} Name:")
            self.player_name_inputs.append(new_input)
            print(f"Added input for player {next_player_num}")
        else:
            print("Maximum number of players reached.")
            self.setup_error_message = f"Maximum {MAX_PLAYERS} players allowed."

    # ---------- State Transition Actions ------------------------------------

    def _start_game_action(self):
        print("Start Game button clicked")
        self.setup_error_message = "" # Clear previous errors

        # --- Get Player Names & Infer Count ---
        entered_names = []
        for input_box in self.player_name_inputs:
            name = input_box.get_text().strip()
            if name: # Only count non-empty names
                entered_names.append(name)
            # Optional: Clear the input box after reading? 
            # input_box.text = ""
            # input_box.txt_surface = Font.render("", True, TEXT_COLOR)

        num_players = len(entered_names)

        # --- Validate Player Count ---
        if not (MIN_PLAYERS <= num_players <= MAX_PLAYERS):
            self.setup_error_message = f"Error: Must have between {MIN_PLAYERS} and {MAX_PLAYERS} players with names entered. Found {num_players}."
            print(self.setup_error_message)
            return

        # --- Check for Duplicate Names ---
        if len(entered_names) != len(set(entered_names)):
            self.setup_error_message = "Error: Player names must be unique."
            print(self.setup_error_message)
            return

        # --- Load Clues Automatically ---
        loaded_players: List[Player] = []
        try:
            clues_path = Path("clues.json")
            if not clues_path.exists():
                 clues_path = Path("./demo_clues.json") # Try demo file
                 if not clues_path.exists():
                      self.setup_error_message = "Error: clues.json or demo_clues.json not found!"
                      print(self.setup_error_message)
                      return
            loaded_players = load_clues(clues_path)
            print(f"Loaded {len(loaded_players)} player definitions from {clues_path}.")

            if len(loaded_players) < num_players:
                self.setup_error_message = f"Error: Clues file only defines {len(loaded_players)} players, but {num_players} were entered."
                print(self.setup_error_message)
                return

            # Slice to get the requested number of players
            self.players = loaded_players[:num_players]

        except Exception as e:
            self.setup_error_message = f"Error loading clues: {e}"
            print(self.setup_error_message)
            self.players = [] # Ensure players list is empty on error
            return

        # --- Override Names ---
        for i, name in enumerate(entered_names):
            self.players[i].name = name
        print(f"Final player list: { [p.name for p in self.players] }")

        # --- Initialize Play State ---
        print(f"Starting game with {num_players} players: {[p.name for p in self.players]}")
        # Assuming board.json exists and is valid
        try:
            self.grid = load_board(Path("board.json"), self.grid_size) 
        except Exception as e:
            self.setup_error_message = f"Error loading board.json: {e}"
            print(self.setup_error_message)
            self.players = [] # Reset players
            return
        
        self.ledger = {}
        self.revealed = []
        self.commits = [False] * len(self.players) # Initialize commits based on final player count
        self.round = 1
        self.current_coalition = frozenset()
        self.coalition_locked = False
        self.last_guess_result = None
        self.allowed_guesses = None
        self.clue_positions = []

        # Initialize Play UI elements
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
        self.ledger_panel = LedgerPanel(pg.Rect(RIGHT_PANEL_X, LEDGER_Y, RIGHT_PANEL_W, LEDGER_H))

        self.state = AWAIT_COMMIT
        print("Transitioning to AWAIT_COMMIT state.")

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

        # Build allowed_guesses from committed players' clues
        allowed = set()
        # Store clue-specific positions for grid highlighting
        self.clue_positions = []
        for idx in self.current_coalition:
            player_positions = self.players[idx].allowed_positions(self.grid_size)
            self.clue_positions.append((idx, player_positions, len(player_positions) < self.grid_size * self.grid_size))
            allowed |= player_positions
        self.allowed_guesses = allowed or None
        self.state = AWAIT_GUESS
        print(f"Coalition locked: {self.current_coalition}. Waiting for guess.")

    def _handle_grid_click(self, r: int, c: int):
        if self.state != AWAIT_GUESS:
            print("Not awaiting guess.")
            return
        if not self.coalition_locked:
             print("Coalition not locked yet!")
             return

        # Restrict guesses to allowed positions
        if self.allowed_guesses is not None and (r, c) not in self.allowed_guesses:
            print(f"({r},{c}) not permitted by your committed clues.")
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
        self.allowed_guesses = None
        # Clear clue positions
        self.clue_positions = []
        print(f"--- Starting Round {self.round} ---")

    def _confirm_end_game(self):
        # Optional: Add a confirmation dialog
        print("End Game button clicked.")
        self._end_game()

    def _end_game(self):
        if self.state == END: return # Already ended
        print("Ending game and calculating payouts...")
        self.state = END
        
        # --- Calculate the characteristic function based on clues: number of eliminated positions by coalition ---
        values = self._calculate_clues_based_characteristic_function() # Use the new function
        
        weights = [p.weight for p in self.players]
        try:
             self.payouts = shapley_sample(values, len(self.players), weights, samples=10000)
             print(f"Shapley Payouts calculated (clues-based): {self.payouts}")
             # Verification: Check if sum of payouts roughly equals ledger total
             total_ledger_value = sum(self.ledger.values()) # Get actual ledger total
             print(f"Total treasure found (ledger sum) = {total_ledger_value}") # Use ledger total
             print(f"Sum of calculated Shapley payouts = {sum(self.payouts):.2f}")
        except Exception as e:
             print(f"Error calculating Shapley values: {e}")
             self.payouts = None # Indicate calculation failure

        # Initialize End Screen UI (or ensure they exist)
        self._initialize_end_buttons()

    def _initialize_end_buttons(self):
        """Helper to create end game buttons if they don't exist."""
        if not hasattr(self, 'export_button') or self.export_button is None:
            self.export_button = Button(pg.Rect(WINDOW_W // 2 - 160, WINDOW_H - 60, 150, 30), "Export Results", self._export_results)
        if not hasattr(self, 'restart_button') or self.restart_button is None:
            self.restart_button = Button(pg.Rect(WINDOW_W // 2 + 10, WINDOW_H - 60, 150, 30), "Restart Game", self._restart_game)

    def _calculate_clues_based_characteristic_function(self) -> Dict[FrozenSet[int], int]:
        """Calculates v(S) based on clues: number of eliminated positions by coalition."""
        print("Calculating clues-based characteristic function v(S)...")
        if not self.players:
            print("Warning: Cannot calculate v(S) without players.")
            return {}

        n = len(self.players)
        v: Dict[FrozenSet[int], int] = {}
        grid_size = self.grid_size
        total_cells = grid_size * grid_size

        # Iterate through all possible coalition sizes (0 to n)
        for k in range(n + 1):
            # Iterate through all coalitions S of size k
            for coalition_indices_tuple in itertools.combinations(range(n), k):
                S = frozenset(coalition_indices_tuple)

                if not S:
                    v[S] = 0
                else:
                    # Intersection of allowed positions of players in S
                    intersect_positions = {(r, c) for r in range(grid_size) for c in range(grid_size)}
                    for idx in S:
                        intersect_positions &= self.players[idx].allowed_positions(grid_size)
                    allowed_count = len(intersect_positions)
                    # v(S) is number of eliminated positions
                    v[S] = total_cells - allowed_count

        print("Finished calculating clues-based v(S).")
        return v

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
         # Handle input for all current TextInputs
         for input_box in self.player_name_inputs:
              input_box.handle_event(event)
         
         # Handle Add Player button click (only if shown)
         if len(self.player_name_inputs) < MAX_PLAYERS:
             self.add_player_button.handle_event(event)
             
         # Handle start button click
         self.start_game_button.handle_event(event)
         
         # Allow pressing Enter in ANY text box OR clicking Start button
         start_triggered = False
         if event.type == pg.KEYDOWN and event.key == pg.K_RETURN:
             active_input_found = False
             for input_box in self.player_name_inputs:
                if input_box.active:
                    input_box.active = False
                    input_box.color = COLOR_INACTIVE
                    active_input_found = True
                    break # Only deactivate one
             if active_input_found:
                start_triggered = True

         # If Enter was pressed OR start button was clicked, call the start action
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
        # Top bar with game state info
        pg.draw.rect(self.screen, (70, 130, 180), (0, 0, WINDOW_W, TopBarH)) # Steel Blue
        state_text = f"State: {self.state}"
        state_surf = self.font.render(state_text, True, (255, 255, 255))
        self.screen.blit(state_surf, (10, 10))

        if self.state != SETUP:
            round_text = f"Round: {self.round}"
            round_surf = self.font.render(round_text, True, (255, 255, 255))
            self.screen.blit(round_surf, (200, 10))
            
            coalition_text = f"Coalition: {', '.join(str(i) for i in sorted(self.current_coalition)) or 'None'}"
            coalition_surf = self.font.render(coalition_text, True, (255, 255, 255))
            self.screen.blit(coalition_surf, (400, 10))


    def _draw_setup(self):
        # Centered Title
        title_txt = self.font.render("Game Setup", True, (0, 0, 0))
        title_rect = title_txt.get_rect(center=(WINDOW_W // 2, 80))
        self.screen.blit(title_txt, title_rect)

        # Position UI elements vertically
        widget_y = 130 # Start a bit lower
        widget_spacing = 45 # Space between input boxes
        button_top_margin = 25 # Space above buttons

        # Player Name Inputs
        for i, input_box in enumerate(self.player_name_inputs):
            input_box.rect.centerx = WINDOW_W // 2
            input_box.rect.y = widget_y
            input_box.draw(self.screen)
            widget_y += widget_spacing
        
        widget_y += button_top_margin # Add space before buttons

        # Add Player Button (conditional)
        if len(self.player_name_inputs) < MAX_PLAYERS:
            self.add_player_button.rect.centerx = WINDOW_W // 2
            self.add_player_button.rect.y = widget_y
            self.add_player_button.draw(self.screen)
            widget_y += self.add_player_button.rect.height + 15 # Space after add button

        # Start Game Button
        self.start_game_button.rect.centerx = WINDOW_W // 2
        # Use the taller BUTTON_H for start button height
        self.start_game_button.rect.height = BUTTON_H 
        self.start_game_button.rect.y = widget_y 
        self.start_game_button.draw(self.screen)
        widget_y += self.start_game_button.rect.height + 15 # Space after start button

        # Display Error Message (if any)
        if self.setup_error_message:
            error_surf = self.font.render(self.setup_error_message, True, (200, 0, 0)) # Red color
            error_rect = error_surf.get_rect(center=(WINDOW_W // 2, widget_y))
            self.screen.blit(error_surf, error_rect)


    def _draw_play(self):
        # Draw Grid
        if self.grid_view:
            self.grid_view.draw(
                self.screen, 
                self.revealed, 
                self.grid, 
                self.allowed_guesses, 
                self.clue_positions if self.state == AWAIT_GUESS else [],
                players=self.players
            )

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
             # Adjust instruction text position based on new GRID_PX
             self.screen.blit(guess_txt, (GRID_LEFT_MARGIN, TopBarH + GRID_TOP_MARGIN + GRID_PX + 5))


    def _draw_end(self):
        y = 60 # Start slightly lower for more content
        
        # --- Header --- 
        header = self.font.render("Game Over", True, (0, 0, 0))
        header_rect = header.get_rect(center=(WINDOW_W // 2, y))
        self.screen.blit(header, header_rect)
        y += 40

        # --- Actual Results (Ledger) Section --- 
        sub_header_ledger = self.font.render("--- Actual Treasure Found ---", True, (0, 0, 128))
        sub_header_ledger_rect = sub_header_ledger.get_rect(center=(WINDOW_W // 2, y))
        self.screen.blit(sub_header_ledger, sub_header_ledger_rect)
        y += 25
        
        if self.ledger:
            total_ledger_val = sum(self.ledger.values())
            ledger_info_txt = self.font.render(f"Total Found: {total_ledger_val} coins", True, (50, 50, 50))
            ledger_info_rect = ledger_info_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(ledger_info_txt, ledger_info_rect)
            y += 20

            for coalition_indices, coins in self.ledger.items():
                # Format coalition names
                try:
                    names = "+".join(sorted(self.players[i].get_short_name() for i in coalition_indices))
                except (IndexError, AttributeError):
                    names = "ErrorCoalition"
                
                # Use the imported FontSmall directly
                ledger_entry_txt = FontSmall.render(f"Coalition [{names}]: {coins} coins", True, (0,0,0))
                ledger_entry_rect = ledger_entry_txt.get_rect(center=(WINDOW_W // 2, y))
                self.screen.blit(ledger_entry_txt, ledger_entry_rect)
                y += 18 # Smaller spacing for ledger entries
        else:
            no_ledger_txt = self.font.render("No treasure found during the game.", True, (100, 100, 100))
            no_ledger_rect = no_ledger_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(no_ledger_txt, no_ledger_rect)
            y += 20
             
        y += 25 # Add spacing before next section
        
        # --- Shapley Payouts Section --- 
        sub_header_shapley = self.font.render("--- Shapley Distribution of Found Treasure ---", True, (0, 0, 128))
        sub_header_shapley_rect = sub_header_shapley.get_rect(center=(WINDOW_W // 2, y))
        self.screen.blit(sub_header_shapley, sub_header_shapley_rect)
        y += 25

        # Enhanced explanation text for ledger-based value
        explanation_line1 = FontSmall.render("(Distributes found treasure based on average contribution to successful coalitions.)", True, (80, 80, 80))
        explanation_rect1 = explanation_line1.get_rect(center=(WINDOW_W // 2, y))
        self.screen.blit(explanation_line1, explanation_rect1)
        y += 16 # Space for next line
        explanation_line2 = FontSmall.render("(Players get credit if their participation was needed for a score listed above.)", True, (80, 80, 80))
        explanation_rect2 = explanation_line2.get_rect(center=(WINDOW_W // 2, y))
        self.screen.blit(explanation_line2, explanation_rect2)
        y += 25 

        if self.payouts is not None:
            # Display sum of Shapley values (should equal ledger total)
            total_payout = sum(self.payouts)
            info_txt = self.font.render(f"Sum of Payouts (Equals Found Treasure): {total_payout:.2f} coins", True, (50, 50, 50))
            info_rect = info_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(info_txt, info_rect)
            y += 25
            
            # Get set of players who were in any successful coalition
            successful_players = set()
            for coalition_indices in self.ledger.keys():
                 successful_players.update(coalition_indices)

            # Individual payouts with participation marker
            for i, p in enumerate(self.players):
                if i < len(self.payouts):
                     payout_val = self.payouts[i]
                     # Check if player was part of any success
                     marker = " [*]" if i in successful_players else "" 
                     txt_str = f"{p.name}: {payout_val:.2f} coins{marker}"
                     txt = self.font.render(txt_str, True, p.color)
                     txt_rect = txt.get_rect(center=(WINDOW_W // 2, y))
                     self.screen.blit(txt, txt_rect)
                     y += 25
                else:
                     # Error case (shouldn't happen ideally)
                     print(f"Error: Payout list length mismatch for player {i}")
                     error_surf = self.font.render(f"ERROR: PAYOUT MISMATCH {i}", True, (255,0,0))
                     error_rect = error_surf.get_rect(center=(WINDOW_W // 2, y))
                     self.screen.blit(error_surf, error_rect)
                     y += 25
                     break 
            
            # Add legend for the marker
            legend_txt = FontSmall.render("[*] = Member of a scoring coalition", True, (80, 80, 80))
            legend_rect = legend_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(legend_txt, legend_rect)
            y += 20 # Add a bit more space after legend
                    
        else: # self.payouts is None
            # Display calculation error message
            error_txt = self.font.render("Error calculating Shapley values.", True, (255, 0, 0))
            error_rect = error_txt.get_rect(center=(WINDOW_W // 2, y))
            self.screen.blit(error_txt, error_rect)
            y += 25

        # --- End Screen Buttons --- 
        # Ensure buttons are positioned below content
        button_y = max(y + 20, WINDOW_H - 60) # Position buttons near bottom, but below text
        
        # Indent the button drawing logic correctly
        if self.export_button:
            self.export_button.rect.y = button_y
            self.export_button.rect.centerx = WINDOW_W // 2 - self.export_button.rect.width // 2 - 10
            self.export_button.draw(self.screen)
        if self.restart_button: 
            self.restart_button.rect.y = button_y
            self.restart_button.rect.centerx = WINDOW_W // 2 + self.restart_button.rect.width // 2 + 10
            self.restart_button.draw(self.screen)

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
