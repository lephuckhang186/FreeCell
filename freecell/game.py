"""
FreeCell Application Entry Point.
This module defines the main game loop, event handling, and UI orchestration.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from time import time
import threading

import pygame

from .animation import Tween
from .constants import (
    DEFAULT_NEW_GAME_DIFFICULTY,
    DEFAULT_NEW_GAME_LEVEL,
    DOUBLE_CLICK_SECONDS,
    DRAG_SMOOTH_FACTOR,
    DROP_ANIM_DURATION,
    FOOTER_HEIGHT,
    FPS,
    MENU_ITEMS,
    MENU_ITEMS_WITH_SUBMENU,
    NEW_GAME_LEVEL_RANGES,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SOLVE_ALGO_ORDER,
    SOLVER_AUTOSOLVE_TIMEOUT_S,
    SOLVER_BTN_ACCENTS,
    TITLE,
)
from .layout import BoardLayout
from .rules import (
    PileRef,
    PileType,
    apply_move,
    tableau_descending_alternating,
    validate_move,
)
from .models import Card, Suit
from .state import GameState, get_card_from_str, load_game_from_testcase_file
from .ui import Renderer, menu_button_rect, dropup_layout, submenu_layout, sub2_layout
from .algorithm import FreeCellSolver
from . import generate_test


@dataclass(slots=True)
class DragState:
    src: PileRef
    start_index: int
    cards: list
    offset_x: float
    offset_y: float
    smooth_x: float
    smooth_y: float
    target_x: float
    target_y: float


@dataclass(slots=True)
class DropAnimation:
    cards: list
    tween: Tween
    dst: PileRef
    count: int
    x: float
    y: float


@dataclass(slots=True)
class CardAnimation:
    card: Card
    tween: Tween
    x: float
    y: float


class FreeCellGame:
    def _compute_window_size(self) -> tuple[int, int]:
        """Pick a windowed size that always fits desktop bounds."""
        desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        # Keep the frame/title bar visible by leaving safe margins.
        safe_w = max(1024, desktop_w - 140)
        safe_h = max(700, desktop_h - 180)
        return min(SCREEN_WIDTH, safe_w), min(SCREEN_HEIGHT, safe_h)

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption(TITLE)
        width, height = self._compute_window_size()
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.layout = BoardLayout(self.screen.get_size())
        self.renderer = Renderer(self.screen)

        self.active_deal_label: str = ""
        self.state: GameState = self._build_generated_state(
            DEFAULT_NEW_GAME_DIFFICULTY, DEFAULT_NEW_GAME_LEVEL
        )
        self._retry_category: str = DEFAULT_NEW_GAME_DIFFICULTY
        self._retry_level: int = DEFAULT_NEW_GAME_LEVEL
        self._retry_state: GameState = self.state.clone()
        self.undo_stack: list[GameState] = []
        self.redo_stack: list[GameState] = []
        self.drag: DragState | None = None
        self.drop_anim: DropAnimation | None = None
        self.mouse_down_pos: tuple[int, int] | None = None
        self.last_click_at = 0.0
        self.status_text = ""
        self.status_until = 0.0
        self.solver_stats: dict | None = None
        self._solver_thread: threading.Thread | None = None
        self._solver_result: dict | None = None
        self._solver_label: str = ""
        self._solver_started_at: float = 0.0
        self._solver_timed_out: bool = False
        self.solver_game_over: bool = False
        self._solver_cancel_event = threading.Event()
        self.transition_anims: list[CardAnimation] = []
        self.auto_foundation_active = False
        self.solution_moves: list = []
        # UI state
        self.score: int = 0
        self.elapsed: float = 0.0
        self.moves: int = 0
        self.paused: bool = False
        # Bottom-right menu
        self.menu_open: bool = False
        self.menu_btn_hover: bool = False
        self.menu_hover: str | None = None
        self.submenu_hover: str | None = None
        self.sub2_hover: str | None = None

    # ── Menu helpers ──────────────────────────────────────────────────────

    def _close_menu(self) -> None:
        self.menu_open = False
        self.menu_hover = None
        self.submenu_hover = None
        self.sub2_hover = None

    def _update_menu_hover(self, pos: tuple[int, int]) -> None:
        """Track hover across menu button, dropup, and cascading submenus.

        Uses "bridge" rectangles in the gap between a parent item and its
        flyout submenu so the user can move the cursor leftward without
        the submenu vanishing.
        """
        sw, sh = self.screen.get_size()
        self.menu_btn_hover = menu_button_rect(sw, sh).collidepoint(pos)

        if not self.menu_open:
            return

        drop_outer, drop_rects = dropup_layout(sw, sh)
        found_main: str | None = None
        found_sub: str | None = None
        found_sub2: str | None = None

        # Helper: build a bridge rect between a parent item and its submenu outer
        def _bridge(parent: "pygame.Rect", sub_outer: "pygame.Rect") -> "pygame.Rect":
            top = min(parent.top, sub_outer.top)
            bot = max(parent.bottom, sub_outer.bottom)
            return pygame.Rect(
                sub_outer.right, top, parent.left - sub_outer.right + 4, bot - top
            )

        # 1. Check sub2 (level numbers) — deepest first
        if self.menu_hover == "NEW GAME" and self.submenu_hover:
            cat = self.submenu_hover
            if cat in NEW_GAME_LEVEL_RANGES:
                parent = drop_rects["NEW GAME"]
                _, sub_rects = submenu_layout(
                    parent, ["easy", "medium", "hard"], screen_h=sh
                )
                if cat in sub_rects:
                    lo, hi = NEW_GAME_LEVEL_RANGES[cat]
                    levels = [str(l) for l in range(lo, hi + 1)]
                    s2_outer, s2_rects = sub2_layout(
                        sub_rects[cat], levels, screen_h=sh
                    )
                    for key in levels:
                        if s2_rects[key].collidepoint(pos):
                            found_sub2 = key
                            found_sub = cat
                            found_main = "NEW GAME"
                            break
                    # Bridge between difficulty item and level flyout
                    if found_main is None:
                        bridge = _bridge(sub_rects[cat], s2_outer)
                        if s2_outer.collidepoint(pos) or bridge.collidepoint(pos):
                            found_sub = cat
                            found_main = "NEW GAME"

        # 2. Check submenu
        if found_main is None:
            active = self.menu_hover
            if active == "NEW GAME":
                parent = drop_rects["NEW GAME"]
                cats = ["easy", "medium", "hard"]
                sub_outer, sub_rects = submenu_layout(parent, cats, screen_h=sh)
                for key in cats:
                    if sub_rects[key].collidepoint(pos):
                        found_sub = key
                        found_main = "NEW GAME"
                        break
                # Bridge between main item and difficulty flyout
                if found_main is None:
                    bridge = _bridge(parent, sub_outer)
                    if sub_outer.collidepoint(pos) or bridge.collidepoint(pos):
                        found_main = "NEW GAME"
            elif active == "SOLVE":
                parent = drop_rects["SOLVE"]
                algos = list(SOLVE_ALGO_ORDER)
                sub_outer, sub_rects = submenu_layout(parent, algos, screen_h=sh)
                for key in algos:
                    if sub_rects[key].collidepoint(pos):
                        found_sub = key
                        found_main = "SOLVE"
                        break
                # Bridge between main item and algo flyout
                if found_main is None:
                    bridge = _bridge(parent, sub_outer)
                    if sub_outer.collidepoint(pos) or bridge.collidepoint(pos):
                        found_main = "SOLVE"

        # 3. Check main dropup
        if found_main is None:
            for key in MENU_ITEMS:
                if drop_rects[key].collidepoint(pos):
                    found_main = key
                    break

        self.menu_hover = found_main
        self.submenu_hover = found_sub
        self.sub2_hover = found_sub2

    def _handle_menu_click(self, pos: tuple[int, int]) -> bool:
        """Handle a click when the menu is open.  Returns True = consumed."""
        sw, sh = self.screen.get_size()

        # Click on menu button → close
        if menu_button_rect(sw, sh).collidepoint(pos):
            self._close_menu()
            return True

        # Sub2 click: level number → new deal
        if self.menu_hover == "NEW GAME" and self.submenu_hover and self.sub2_hover:
            try:
                lvl = int(self.sub2_hover)
                self._apply_new_deal(self.submenu_hover, lvl)
            except ValueError:
                pass
            self._close_menu()
            return True

        # Submenu click: algorithm → run solver
        if self.menu_hover == "SOLVE" and self.submenu_hover:
            algo = self.submenu_hover
            if algo in SOLVE_ALGO_ORDER:
                if self._solver_thread and self._solver_thread.is_alive():
                    self.set_status("Solver dang chay! Vui long doi...", 2.0)
                else:
                    self.run_solver(algo)
            self._close_menu()
            return True

        # Main item click
        drop_outer, drop_rects = dropup_layout(sw, sh)
        for key in MENU_ITEMS:
            if drop_rects[key].collidepoint(pos):
                if key in MENU_ITEMS_WITH_SUBMENU:
                    return True  # do nothing, submenus open on hover
                if key == "UNDO":
                    self.undo()
                elif key == "REDO":
                    self.redo()
                elif key == "LOAD GAME":
                    self._close_menu()
                    self._load_game_dialog()
                    return True
                elif key == "PAUSE":
                    self.toggle_pause()
                self._close_menu()
                return True

    def _load_game_dialog(self) -> None:
        import tkinter as tk
        from tkinter import filedialog
        from .state import _parse_testcase_lines
        import os

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        testcase_dir = os.path.join(base_dir, "testcase")

        file_path = filedialog.askopenfilename(
            parent=root,
            initialdir=testcase_dir if os.path.exists(testcase_dir) else base_dir,
            title="Load Game",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        root.destroy()

        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f.readlines()]
                new_state = _parse_testcase_lines(lines)

                self.undo_stack.clear()
                self.redo_stack.clear()
                self.solution_moves.clear()
                self.solver_stats = None
                self._solver_result = None
                self.win_anim = None
                if self._solver_thread:
                    self._solver_cancel_event.set()
                self._solver_thread = None
                self.solver_game_over = False

                self.state = new_state
                self._retry_state = self.state.clone()
                self._retry_category = "Loaded"
                self._retry_level = -1
                self.moves = 0
                self.score = 0
                self.elapsed = 0.0
                file_name = os.path.basename(file_path)
                self.active_deal_label = f"Loaded: {file_name}"
                self.set_status("Loaded successfully!", 3.0)
            except Exception as e:
                self.set_status(f"Load failed: {e}", 3.0)

        # Click outside everything → close
        self._close_menu()
        return True

    def toggle_pause(self) -> None:
        if self.state.won or self.solver_game_over:
            return
        self.paused = not self.paused
        if self.paused:
            self.drag = None

    def set_status(self, message: str, seconds: float = 1.2) -> None:
        self.status_text = message
        self.status_until = time() + seconds

    def _build_generated_state(self, category: str, level: int) -> GameState:
        """Generate a fresh deal using freecell/generate_test.py at a specific LEVEL."""
        generate_test.LEVEL = level
        (
            generate_test.MOVES,
            generate_test.BLOCK_DEPTH,
            generate_test.MIN_SEQ,
            generate_test.NOISE,
        ) = generate_test.LEVEL_CONFIG[level]
        nums_tableau, _ = generate_test.generate()
        state = GameState()
        for col_idx, col in enumerate(nums_tableau):
            if col_idx >= len(state.tableau):
                break
            state.tableau[col_idx] = [
                get_card_from_str(generate_test.card_str(n)) for n in col
            ]
        self.active_deal_label = f"gen:{category} (L{level})"
        return state

    def _apply_new_deal(self, category: str, level: int) -> None:
        self._solver_cancel_event.set()
        self.state = self._build_generated_state(category, level)
        # Save snapshot for retry.
        self._retry_category = category
        self._retry_level = level
        self._retry_state = self.state.clone()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.drag = None
        self.drop_anim = None
        self.status_text = ""
        self.status_until = 0.0
        self.solver_stats = None
        self._solver_thread = None
        self._solver_result = None
        self._solver_started_at = 0.0
        self._solver_timed_out = False
        self.solver_game_over = False
        self.auto_foundation_active = False
        self.transition_anims.clear()
        self.solution_moves = []
        self.score = 0
        self.elapsed = 0.0
        self.moves = 0
        self.paused = False
        self._close_menu()

    def retry_current_deal(self) -> None:
        """Restore the last generated board (created by the most recent New game / level pick)."""
        self._solver_cancel_event.set()
        if self._retry_state is None:
            return
        self.state = self._retry_state.clone()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.drag = None
        self.drop_anim = None
        self.status_text = ""
        self.status_until = 0.0
        self.solver_stats = None
        self._solver_thread = None
        self._solver_result = None
        self._solver_started_at = 0.0
        self._solver_timed_out = False
        self.solver_game_over = False
        self.auto_foundation_active = False
        self.transition_anims.clear()
        self.solution_moves = []
        self.score = 0
        self.elapsed = 0.0
        self.moves = 0
        self.paused = False
        self._close_menu()

    def save_current_testcase(self) -> None:
        """Save the initial board state (_retry_state) to testcase/testcase{num}.txt."""
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        testcase_dir = os.path.join(base_dir, "testcase")
        if not os.path.exists(testcase_dir):
            os.makedirs(testcase_dir)
            
        max_num = 0
        for fname in os.listdir(testcase_dir):
            if fname.startswith("testcase") and fname.endswith(".txt"):
                num_part = fname[len("testcase"):-4]
                if num_part.isdigit():
                    max_num = max(max_num, int(num_part))
        next_num = max_num + 1
        filepath = os.path.join(testcase_dir, f"testcase{next_num}.txt")
        
        state_to_save = self._retry_state if self._retry_state else self.state
        
        def card_string(c: Card) -> str:
            r_str = "T" if c.rank == 10 else ("A" if c.rank == 1 else ("J" if c.rank == 11 else ("Q" if c.rank == 12 else ("K" if c.rank == 13 else str(c.rank)))))
            return f"{r_str}{c.suit.value}"

        lines = []
        lines.append("[FOUNDATION]")
        for suit in (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES):
            pile = state_to_save.foundations[suit]
            if pile:
                lines.append(f"{suit.value}: {card_string(pile[-1])}")
            else:
                lines.append(f"{suit.value}: empty")
                
        lines.append("")
        lines.append("[FREECELL]")
        for i, c in enumerate(state_to_save.free_cells):
            if c:
                lines.append(f"{i}: {card_string(c)}")
            else:
                lines.append(f"{i}: empty")
                
        lines.append("")
        lines.append("[TABLEAU]")
        for col in state_to_save.tableau:
            if col:
                lines.append(" ".join(card_string(c) for c in col))
            else:
                lines.append("empty")
                
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.set_status(f"Saved to testcase{next_num}.txt", 3.0)
        except Exception as e:
            self.set_status(f"Failed to save: {e}", 3.0)

    def add_score(self, delta: int) -> None:
        """Add delta to score, clamped to >= 0."""
        self.score = max(0, self.score + delta)

    def _run_solver_task(self, label: str, state_copy: GameState) -> None:
        solver = FreeCellSolver(state_copy, self._solver_cancel_event)
        stats = None
        try:
            if label == "BFS":
                stats = solver.bfs_solving()
            elif label == "IDS":
                stats = solver.ids_solving()
            elif label == "UCS":
                stats = solver.ucs_solving()
            elif label == "A*":
                stats = solver.astar_solving()
        except Exception:
            pass
        self._solver_result = stats if stats is not None else {}

    def run_solver(self, label: str) -> None:
        if self._solver_thread and self._solver_thread.is_alive():
            self.set_status("Solver dang chay, vui long doi!", 2.0)
            return

        self.set_status(f"Solving with {label}! Please wait...", 100.0)
        self._solver_result = None
        self._solver_label = label
        self._solver_started_at = time()
        self._solver_timed_out = False
        self.solver_game_over = False
        self._solver_cancel_event.clear()

        # Deepcopy state passing to background thread to avoid conflict with main thread
        state_copy = deepcopy(self.state)
        self._solver_thread = threading.Thread(
            target=self._run_solver_task, args=(label, state_copy), daemon=True
        )
        self._solver_thread.start()

    def _apply_solver_timeout(self) -> None:
        """Auto-solve exceeded SOLVER_AUTOSOLVE_TIMEOUT_S; end the run as game over."""
        self._solver_cancel_event.set()
        self._solver_timed_out = True
        self.solver_game_over = True
        self.solution_moves.clear()
        self.solver_stats = None
        self.auto_foundation_active = False
        self.set_status(
            f"Het thoi gian giai ({SOLVER_AUTOSOLVE_TIMEOUT_S // 60} phut). Game over!",
            12.0,
        )

    def push_undo_snapshot(self) -> None:
        self.undo_stack.append(deepcopy(self.state))
        self.redo_stack.clear()

    def undo(self) -> None:
        if self.solver_game_over:
            self.set_status("Game over — nhan R hoac New de choi lai.", 2.0)
            return
        if not self.undo_stack:
            self.set_status("Khong con nuoc de undo.")
            return
        self.solution_moves.clear()
        old_state = deepcopy(self.state)
        self.redo_stack.append(deepcopy(self.state))
        self.state = self.undo_stack.pop()
        self.moves += 1
        self.add_score(-5)  # penalty for undo
        self.start_state_transition_animation(old_state, self.state)
        self.drag = None
        self.drop_anim = None
        self.auto_foundation_active = False

    def redo(self) -> None:
        if self.solver_game_over:
            self.set_status("Game over — nhan R hoac New de choi lai.", 2.0)
            return
        if not self.redo_stack:
            self.set_status("Khong co nuoc de redo.")
            return
        self.solution_moves.clear()
        old_state = deepcopy(self.state)
        self.undo_stack.append(deepcopy(self.state))
        self.state = self.redo_stack.pop()
        self.moves += 1
        self.start_state_transition_animation(old_state, self.state)
        self.drag = None
        self.drop_anim = None
        self.auto_foundation_active = False

    def card_positions(self, state: GameState) -> dict[Card, tuple[float, float]]:
        """Compute pixel position of every visible card for animation mapping."""
        out: dict[Card, tuple[float, float]] = {}

        for i, card in enumerate(state.free_cells):
            if card is None:
                continue
            rect = self.layout.free_cells[i]
            out[card] = (float(rect.x), float(rect.y))

        for i, suit in enumerate(Suit):
            pile = state.foundations[suit]
            if pile:
                rect = self.layout.foundations[i]
                out[pile[-1]] = (float(rect.x), float(rect.y))

        for col_idx, col in enumerate(state.tableau):
            for row_idx, card in enumerate(col):
                rect = self.layout.card_rect_in_tableau(col_idx, row_idx)
                out[card] = (float(rect.x), float(rect.y))

        return out

    def start_state_transition_animation(
        self, from_state: GameState, to_state: GameState, duration: float = 0.16
    ) -> None:
        """Animate cards between two board states (used for undo/redo)."""
        self.transition_anims.clear()
        from_pos = self.card_positions(from_state)
        to_pos = self.card_positions(to_state)
        moved_cards = [
            card
            for card in from_pos
            if card in to_pos and from_pos[card] != to_pos[card]
        ]
        for card in moved_cards:
            sx, sy = from_pos[card]
            ex, ey = to_pos[card]
            self.transition_anims.append(
                CardAnimation(
                    card=card, tween=Tween(sx, sy, ex, ey, duration), x=sx, y=sy
                )
            )

    def source_at_pos(
        self, pos: tuple[int, int], top_only_tableau: bool = False
    ) -> tuple[PileRef, int] | None:
        for i, rect in enumerate(self.layout.free_cells):
            if rect.collidepoint(pos) and self.state.free_cells[i] is not None:
                return PileRef(PileType.FREECELL, i), -1

        for col_idx in range(len(self.layout.tableau)):
            col = self.state.tableau[col_idx]
            if not col:
                continue
            pick_r = self.layout.tableau_cards_pick_rect(col_idx, len(col))
            if not pick_r or not pick_r.collidepoint(pos):
                continue
            idx = self.layout.tableau_pick_index(col_idx, pos, len(col))
            if idx < 0:
                continue
            if top_only_tableau and idx != len(col) - 1:
                return None
            return PileRef(PileType.TABLEAU, col_idx), idx
        return None

    def try_pick_from_pos(self, pos: tuple[int, int]) -> None:
        if (
            self.drop_anim
            or (
                self._solver_thread
                and self._solver_thread.is_alive()
                and not self._solver_timed_out
            )
            or self.solution_moves
            or self.transition_anims
            or self.solver_game_over
        ):
            return
        # Free cells first
        for i, rect in enumerate(self.layout.free_cells):
            if rect.collidepoint(pos) and self.state.free_cells[i] is not None:
                card = self.state.free_cells[i]
                self.drag = DragState(
                    src=PileRef(PileType.FREECELL, i),
                    start_index=-1,
                    cards=[card],
                    offset_x=pos[0] - rect.x,
                    offset_y=pos[1] - rect.y,
                    smooth_x=float(rect.x),
                    smooth_y=float(rect.y),
                    target_x=float(rect.x),
                    target_y=float(rect.y),
                )
                return

        # Tableau columns.
        for col_idx in range(len(self.layout.tableau)):
            col = self.state.tableau[col_idx]
            if not col:
                continue
            pick_r = self.layout.tableau_cards_pick_rect(col_idx, len(col))
            if not pick_r or not pick_r.collidepoint(pos):
                continue

            start_idx = self.layout.tableau_pick_index(col_idx, pos, len(col))
            if start_idx < 0:
                continue
            candidate = col[start_idx:]
            # Only valid descending alternating sequence can be grabbed as a stack.
            if not tableau_descending_alternating(candidate):
                start_idx = len(col) - 1
                candidate = col[start_idx:]

            card_rect = self.layout.card_rect_in_tableau(col_idx, start_idx)
            self.drag = DragState(
                src=PileRef(PileType.TABLEAU, col_idx),
                start_index=start_idx,
                cards=list(candidate),
                offset_x=pos[0] - card_rect.x,
                offset_y=pos[1] - card_rect.y,
                smooth_x=float(card_rect.x),
                smooth_y=float(card_rect.y),
                target_x=float(card_rect.x),
                target_y=float(card_rect.y),
            )
            return

    def start_drop_animation(
        self, cards: list, dst: PileRef, start_x: float, start_y: float
    ) -> None:
        end_x, end_y = self.card_position_for_destination(dst, len(cards))
        tween = Tween(start_x, start_y, end_x, end_y, DROP_ANIM_DURATION)
        self.drop_anim = DropAnimation(
            cards=cards, tween=tween, dst=dst, count=len(cards), x=start_x, y=start_y
        )

    def card_position_for_destination(
        self, dst: PileRef, count: int
    ) -> tuple[float, float]:
        if dst.kind == PileType.FREECELL:
            rect = self.layout.free_cells[dst.index]
            return float(rect.x), float(rect.y)
        if dst.kind == PileType.FOUNDATION:
            rect = self.layout.foundations[dst.index]
            return float(rect.x), float(rect.y)
        col = self.state.tableau[dst.index]
        row = len(col) - count
        rect = self.layout.card_rect_in_tableau(dst.index, row)
        return float(rect.x), float(rect.y)

    def card_source_position(
        self, src: PileRef, start_index: int = -1
    ) -> tuple[float, float]:
        if src.kind == PileType.FREECELL:
            rect = self.layout.free_cells[src.index]
            return float(rect.x), float(rect.y)
        if src.kind == PileType.FOUNDATION:
            rect = self.layout.foundations[src.index]
            return float(rect.x), float(rect.y)
        col = self.state.tableau[src.index]
        if not col:
            base = self.layout.tableau[src.index]
            return float(base.x), float(base.y)
        if start_index < 0:
            start_index = len(col) - 1
        rect = self.layout.card_rect_in_tableau(src.index, start_index)
        return float(rect.x), float(rect.y)

    def auto_move_once(self, animate: bool = False) -> bool:
        # Check free cells.
        for i, card in enumerate(self.state.free_cells):
            if card is None:
                continue
            src = PileRef(PileType.FREECELL, i)
            for f_idx in range(4):
                dst = PileRef(PileType.FOUNDATION, f_idx)
                if validate_move(self.state, src, dst, [card]).ok:
                    sx, sy = self.card_source_position(src, -1)
                    _, moved_cards = apply_move(self.state, src, dst, -1)
                    if animate and moved_cards:
                        self.start_drop_animation(moved_cards, dst, sx, sy)
                    return True

        # Check top cards of tableau columns.
        for col_idx, col in enumerate(self.state.tableau):
            if not col:
                continue
            card = col[-1]
            src = PileRef(PileType.TABLEAU, col_idx)
            for f_idx in range(4):
                dst = PileRef(PileType.FOUNDATION, f_idx)
                if validate_move(self.state, src, dst, [card]).ok:
                    start_index = len(col) - 1
                    sx, sy = self.card_source_position(src, start_index)
                    _, moved_cards = apply_move(self.state, src, dst, start_index)
                    if animate and moved_cards:
                        self.start_drop_animation(moved_cards, dst, sx, sy)
                    return True
        return False

    def try_auto_move_from_source(self, src: PileRef, start_index: int) -> bool:
        cards = (
            [self.state.tableau[src.index][-1]] if src.kind == PileType.TABLEAU else []
        )
        if src.kind == PileType.FREECELL:
            card = self.state.free_cells[src.index]
            cards = [card] if card else []
        if not cards:
            return False

        # 1) Prefer moving straight to foundation.
        for f_idx in range(4):
            dst = PileRef(PileType.FOUNDATION, f_idx)
            if validate_move(self.state, src, dst, cards).ok:
                self.push_undo_snapshot()
                sx, sy = self.card_source_position(src, start_index)
                res, moved_cards = apply_move(self.state, src, dst, start_index)
                if res.ok:
                    self.moves += 1
                    self.add_score(5 * len(moved_cards))  # +5 per card (double-click)
                    self.start_drop_animation(moved_cards, dst, sx, sy)
                    return True

        # 2) For card already in free cell, try dropping into a tableau column first.
        if src.kind == PileType.FREECELL:
            for t_idx in range(8):
                dst = PileRef(PileType.TABLEAU, t_idx)
                if validate_move(self.state, src, dst, cards).ok:
                    self.push_undo_snapshot()
                    sx, sy = self.card_source_position(src, start_index)
                    res, moved_cards = apply_move(self.state, src, dst, start_index)
                    if res.ok:
                        self.moves += 1
                        self.start_drop_animation(moved_cards, dst, sx, sy)
                        return True

            # 3) If not placeable anywhere below, move only to another empty nearby free cell.
            candidates = [
                i
                for i, c in enumerate(self.state.free_cells)
                if c is None and i != src.index
            ]
            if candidates:
                candidates.sort(key=lambda idx: abs(idx - src.index))
                dst = PileRef(PileType.FREECELL, candidates[0])
                self.push_undo_snapshot()
                sx, sy = self.card_source_position(src, start_index)
                res, moved_cards = apply_move(self.state, src, dst, start_index)
                if res.ok:
                    self.moves += 1
                    self.start_drop_animation(moved_cards, dst, sx, sy)
                    return True
            return False

        # 4) For double-click from tableau with no legal target, park into empty free cell.
        empty_free = next(
            (i for i, c in enumerate(self.state.free_cells) if c is None), None
        )
        if empty_free is not None:
            dst = PileRef(PileType.FREECELL, empty_free)
            if validate_move(self.state, src, dst, cards).ok:
                self.push_undo_snapshot()
                sx, sy = self.card_source_position(src, start_index)
                res, moved_cards = apply_move(self.state, src, dst, start_index)
                if res.ok:
                    self.moves += 1
                    self.start_drop_animation(moved_cards, dst, sx, sy)
                    return True
        return False

    def release_drag(self, mouse_pos: tuple[int, int]) -> None:
        if not self.drag:
            return
        drag = self.drag
        self.drag = None

        dst = self.layout.drop_target(mouse_pos)
        if dst is None:
            return

        self.push_undo_snapshot()
        result, moved_cards = apply_move(self.state, drag.src, dst, drag.start_index)
        if not result.ok:
            if self.undo_stack:
                self.undo_stack.pop()
            self.set_status(result.reason)
            return

        self.moves += 1

        # Scoring: +10 per card moved to foundation
        if dst.kind == PileType.FOUNDATION:
            self.add_score(10 * len(moved_cards))

        self.start_drop_animation(drag.cards, dst, drag.smooth_x, drag.smooth_y)

    def collect_highlight_targets(self) -> set[tuple[str, int]]:
        targets: set[tuple[str, int]] = set()
        if self.drag:
            cards = self.drag.cards
            src = self.drag.src
            for i in range(4):
                if validate_move(
                    self.state, src, PileRef(PileType.FREECELL, i), cards
                ).ok:
                    targets.add(("freecell", i))
            for i in range(4):
                if validate_move(
                    self.state, src, PileRef(PileType.FOUNDATION, i), cards
                ).ok:
                    targets.add(("foundation", i))
            for i in range(8):
                if validate_move(
                    self.state, src, PileRef(PileType.TABLEAU, i), cards
                ).ok:
                    targets.add(("tableau", i))
        return targets

    def update(self, dt: float) -> None:
        self._update_menu_hover(pygame.mouse.get_pos())
        # Advance game timer
        if not self.paused and not self.state.won and not self.solver_game_over:
            self.elapsed += dt

        # Background solver finished
        if self._solver_thread and not self._solver_thread.is_alive():
            if not self._solver_timed_out and self._solver_result is not None:
                stats = self._solver_result
                if stats.get("cancelled"):
                    pass
                elif stats and stats.get("path") is not None:
                    self.solver_stats = stats
                    self.solution_moves = stats["path"].copy()
                    self.set_status(
                        f"Solved with {self._solver_label}! Playing...", 3.0
                    )
                else:
                    self.set_status(
                        f"{self._solver_label} khong the tim ra duong giai.", 3.0
                    )
                    self.solver_stats = None
                self._solver_result = None
            else:
                self._solver_result = None
            self._solver_thread = None

        # Still solving — wall-clock timeout (5 min)
        elif (
            self._solver_thread
            and self._solver_thread.is_alive()
            and not self._solver_timed_out
            and time() - self._solver_started_at >= SOLVER_AUTOSOLVE_TIMEOUT_S
        ):
            self._apply_solver_timeout()

        if self.paused:
            return

        if self.solution_moves and not self.drop_anim and not self.transition_anims:
            move = self.solution_moves.pop(0)
            old_state = deepcopy(self.state)
            apply_move(self.state, move[0], move[1], move[2])
            self.moves += 1
            self.start_state_transition_animation(old_state, self.state, duration=0.15)

        if self.drag:
            mx, my = pygame.mouse.get_pos()
            self.drag.target_x = mx - self.drag.offset_x
            self.drag.target_y = my - self.drag.offset_y
            self.drag.smooth_x += (
                self.drag.target_x - self.drag.smooth_x
            ) * DRAG_SMOOTH_FACTOR
            self.drag.smooth_y += (
                self.drag.target_y - self.drag.smooth_y
            ) * DRAG_SMOOTH_FACTOR
        if self.drop_anim:
            x, y, done = self.drop_anim.tween.step(dt)
            self.drop_anim.x = x
            self.drop_anim.y = y
            if done:
                self.drop_anim = None
        if self.auto_foundation_active and not self.drop_anim and not self.drag:
            if not self.auto_move_once(animate=True):
                self.auto_foundation_active = False
        if self.transition_anims:
            remaining: list[CardAnimation] = []
            for anim in self.transition_anims:
                x, y, done = anim.tween.step(dt)
                anim.x = x
                anim.y = y
                if not done:
                    remaining.append(anim)
            self.transition_anims = remaining

    def draw(self) -> None:
        self.renderer.draw_background()
        self.renderer.draw_static_board(
            self.layout, self.state, highlight_targets=self.collect_highlight_targets()
        )

        hidden_tableau = None
        hidden_freecell = None
        hidden_foundation = None
        if self.drag:
            if self.drag.src.kind == PileType.TABLEAU:
                hidden_tableau = (self.drag.src.index, self.drag.start_index)
            elif self.drag.src.kind == PileType.FREECELL:
                hidden_freecell = self.drag.src.index
            else:
                hidden_foundation = self.drag.src.index

        if self.drop_anim:
            if self.drop_anim.dst.kind == PileType.TABLEAU:
                hidden_from = (
                    len(self.state.tableau[self.drop_anim.dst.index])
                    - self.drop_anim.count
                )
                hidden_tableau = (self.drop_anim.dst.index, hidden_from)
            elif self.drop_anim.dst.kind == PileType.FREECELL:
                hidden_freecell = self.drop_anim.dst.index
            else:
                hidden_foundation = self.drop_anim.dst.index

        self.renderer.draw_state_cards(
            self.layout,
            self.state,
            hidden_tableau=hidden_tableau,
            hidden_freecell=hidden_freecell,
            hidden_foundation=hidden_foundation,
            hidden_cards={anim.card for anim in self.transition_anims},
        )

        if self.drag:
            for i, card in enumerate(self.drag.cards):
                self.renderer.draw_card(
                    card,
                    self.drag.smooth_x,
                    self.drag.smooth_y + i * 34,
                    shadow=True,
                )
        elif self.drop_anim:
            for i, card in enumerate(self.drop_anim.cards):
                self.renderer.draw_card(
                    card,
                    self.drop_anim.x,
                    self.drop_anim.y + i * 34,
                    shadow=True,
                )
        if self.transition_anims:
            for anim in self.transition_anims:
                self.renderer.draw_card(anim.card, anim.x, anim.y, shadow=True)

        n_found = sum(len(p) for p in self.state.foundations.values())
        n_fc = sum(1 for c in self.state.free_cells if c is not None)

        deal_label_to_draw = self.active_deal_label
        if self.status_text and time() <= self.status_until:
            deal_label_to_draw = self.status_text

        solver_anim_time = -1.0
        if self._solver_thread and self._solver_thread.is_alive():
            solver_anim_time = time() - self._solver_started_at

        self.renderer.draw_footer_bar(
            self.score,
            self.elapsed,
            self.moves,
            n_found,
            deal_label_to_draw,
            n_fc,
            menu_btn_hover=self.menu_btn_hover,
            menu_is_open=self.menu_open,
            solver_anim_time=solver_anim_time,
        )

        if self.solver_game_over:
            self.renderer.draw_solver_timeout_game_over_overlay()
        elif self.state.won:
            self.renderer.draw_win_overlay()
            if self.solver_stats:
                font = pygame.font.SysFont("segoeui", 28, bold=True)
                stats = self.solver_stats
                lines = [
                    f"Search Time: {stats.get('search_time', 0):.4f}s",
                    f"Expanded Nodes: {stats.get('expanded_nodes', 0)}",
                    f"Search Length: {stats.get('search_length', 0)} moves",
                    f"Memory Usage: {stats.get('memory_usage_bytes', 0)} bytes",
                ]
                if "depth_reached" in stats:
                    lines.append(f"Depth Reached: {stats['depth_reached']}")
                sy = self.screen.get_height() // 2 + 110
                for line in lines:
                    text_surface = font.render(line, True, (255, 255, 255))
                    tw = text_surface.get_width()
                    self.screen.blit(
                        text_surface, (self.screen.get_width() // 2 - tw // 2, sy)
                    )
                    sy += 36
        elif self.paused:
            self.renderer.draw_pause_overlay()

        # ── Cascading menu ──
        if self.menu_open:
            sw, sh = self.screen.get_size()
            drop_outer, drop_rects = dropup_layout(sw, sh)
            self.renderer.draw_dropup(drop_outer, drop_rects, self.menu_hover)

            # Submenu for NEW GAME → difficulty
            if self.menu_hover == "NEW GAME":
                cats = ["easy", "medium", "hard"]
                parent = drop_rects["NEW GAME"]
                sub_outer, sub_rects = submenu_layout(parent, cats, screen_h=sh)
                items = [(c, c.title()) for c in cats]
                self.renderer.draw_submenu(
                    sub_outer, items, sub_rects, self.submenu_hover, has_sub=True
                )

                # Sub-submenu: level numbers
                if self.submenu_hover and self.submenu_hover in NEW_GAME_LEVEL_RANGES:
                    lo, hi = NEW_GAME_LEVEL_RANGES[self.submenu_hover]
                    levels = [str(lvl) for lvl in range(lo, hi + 1)]
                    s2_outer, s2_rects = sub2_layout(
                        sub_rects[self.submenu_hover], levels, screen_h=sh
                    )
                    s2_items = [(lvl, lvl) for lvl in levels]
                    self.renderer.draw_submenu(
                        s2_outer, s2_items, s2_rects, self.sub2_hover
                    )

            # Submenu for SOLVE → algorithms
            elif self.menu_hover == "SOLVE":
                algos = list(SOLVE_ALGO_ORDER)
                parent = drop_rects["SOLVE"]
                sub_outer, sub_rects = submenu_layout(parent, algos, screen_h=sh)
                items = [(a, a) for a in algos]
                self.renderer.draw_submenu(
                    sub_outer,
                    items,
                    sub_rects,
                    self.submenu_hover,
                    accent_map=SOLVER_BTN_ACCENTS,
                )

        pygame.display.flip()

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.menu_open:
                            self._close_menu()
                        else:
                            running = False
                    elif event.key == pygame.K_r:
                        if self.menu_open:
                            self._close_menu()
                        else:
                            self.retry_current_deal()
                    elif event.key == pygame.K_p:
                        self.toggle_pause()
                    elif not self.paused and event.key == pygame.K_z:
                        self.undo()
                    elif not self.paused and event.key == pygame.K_y:
                        self.redo()
                    elif event.key == pygame.K_s:
                        if self.menu_open:
                            self._close_menu()
                        else:
                            self.save_current_testcase()
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )
                    self.layout.resize(self.screen.get_size())
                elif event.type == pygame.MOUSEMOTION:
                    self._update_menu_hover(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # Menu open → route to menu handler
                    if self.menu_open:
                        self._handle_menu_click(event.pos)
                        continue
                    # Menu button click → open menu
                    sw, sh = self.screen.get_size()
                    if menu_button_rect(sw, sh).collidepoint(event.pos):
                        self.menu_open = True
                        self.drag = None
                        self.mouse_down_pos = None
                        continue
                    if self.paused:
                        continue
                    if self.state.won or self.solver_game_over:
                        continue
                    # Double-click detection
                    is_double = bool(getattr(event, "clicks", 0) >= 2)
                    now = time()
                    if (
                        not is_double
                        and now - self.last_click_at <= DOUBLE_CLICK_SECONDS
                    ):
                        is_double = True
                    self.last_click_at = now
                    if is_double and not self.drop_anim:
                        src_info = self.source_at_pos(event.pos, top_only_tableau=True)
                        if src_info:
                            src, idx = src_info
                            if self.try_auto_move_from_source(src, idx):
                                continue
                    self.mouse_down_pos = event.pos
                    self.try_pick_from_pos(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self.menu_open:
                        continue
                    if self.state.won or self.solver_game_over:
                        continue
                    if self.paused:
                        continue
                    if self.mouse_down_pos and self.drag:
                        dx = abs(event.pos[0] - self.mouse_down_pos[0])
                        dy = abs(event.pos[1] - self.mouse_down_pos[1])
                        if dx <= 4 and dy <= 4 and len(self.drag.cards) == 1:
                            if self.try_auto_move_from_source(
                                self.drag.src, self.drag.start_index
                            ):
                                self.drag = None
                                self.mouse_down_pos = None
                                continue
                    self.release_drag(event.pos)
                    self.mouse_down_pos = None

            self.update(dt)
            self.draw()

        pygame.quit()


def run() -> None:
    FreeCellGame().run()
