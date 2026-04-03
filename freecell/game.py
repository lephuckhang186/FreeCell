"""Main pygame loop and player interaction."""

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
    FAB_DRAG_THRESHOLD_SQ,
    FOOTER_HEIGHT,
    FPS,
    NEW_GAME_LEVEL_RANGES,
    OUTER_PADDING,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SOLVER_AUTOSOLVE_TIMEOUT_S,
    TITLE,
)
from .layout import BoardLayout
from .rules import PileRef, PileType, apply_move, tableau_descending_alternating, validate_move
from .models import Card, Suit
from .state import GameState, get_card_from_str, load_game_from_testcase_file
from .ui import Renderer, fab_hit_at, fab_outer_size
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
        # Standard framed window (not fullscreen / not borderless).
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.layout = BoardLayout(self.screen.get_size())
        self.renderer = Renderer(self.screen)

        self.active_deal_label: str = ""
        self.state: GameState = self._build_generated_state(DEFAULT_NEW_GAME_DIFFICULTY, DEFAULT_NEW_GAME_LEVEL)
        # Retry (R key): restore the exact same generated board without re-generating.
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
        self.pressed_button_label: str = ""
        self.pressed_button_until: float = 0.0
        self.paused: bool = False
        fw, fh = fab_outer_size()
        sh = self.screen.get_height()
        self.fab_x = float(OUTER_PADDING)
        self.fab_y = float(sh - fh) / 2.0
        self.fab_hover_main: str | None = None
        self.fab_hover_algo: str | None = None
        self._fab_down: tuple[int, int] | None = None
        self._fab_dragging: bool = False
        self._fab_grab: tuple[float, float] = (0.0, 0.0)
        self.new_game_menu_open: bool = False
        self.new_game_menu_hover: str | None = None
        self.new_game_menu_mode: str = "difficulty"  # "difficulty" | "levels"
        self.new_game_menu_category: str | None = None

    def _clamp_fab(self) -> None:
        sw, sh = self.screen.get_size()
        fw, fh = fab_outer_size()
        self.fab_x = max(0.0, min(self.fab_x, float(sw - fw)))
        self.fab_y = max(0.0, min(self.fab_y, float(sh - fh)))

    def _fab_pressed_flash(self) -> tuple[str | None, str | None]:
        if time() > self.pressed_button_until:
            return None, None
        l = self.pressed_button_label
        if l in ("IDS", "BFS", "UCS", "A*"):
            return None, l
        return l, None

    def _update_fab_hover(self) -> None:
        if self.new_game_menu_open or self._fab_dragging:
            self.fab_hover_main = None
            self.fab_hover_algo = None
            return
        h = fab_hit_at(pygame.mouse.get_pos(), int(self.fab_x), int(self.fab_y))
        if h[0] == "main":
            self.fab_hover_main = h[1]
            self.fab_hover_algo = None
        elif h[0] == "algo":
            self.fab_hover_main = None
            self.fab_hover_algo = h[1]
        else:
            self.fab_hover_main = None
            self.fab_hover_algo = None

    def _fab_dispatch_main(self, key: str) -> None:
        if key == "NEW GAME":
            self.open_new_game_menu()
        elif key == "UNDO":
            self.undo()
        elif key == "REDO":
            self.redo()
        elif key == "MENU":
            self.toggle_pause()
        elif key == "HINT":
            pass
        elif key == "AI":
            pass

    def handle_fab_mousemove(self, pos: tuple[int, int]) -> None:
        if self.new_game_menu_open:
            return
        if self._fab_down is None:
            return
        dx = pos[0] - self._fab_down[0]
        dy = pos[1] - self._fab_down[1]
        if dx * dx + dy * dy > FAB_DRAG_THRESHOLD_SQ:
            self._fab_dragging = True
        if self._fab_dragging:
            self.fab_x = float(pos[0]) - self._fab_grab[0]
            self.fab_y = float(pos[1]) - self._fab_grab[1]
            self._clamp_fab()

    def handle_fab_mousedown(self, pos: tuple[int, int]) -> bool:
        if self.new_game_menu_open:
            return False
        h = fab_hit_at(pos, int(self.fab_x), int(self.fab_y))
        if h[0] == "none":
            return False
        self._fab_down = pos
        self._fab_dragging = False
        self._fab_grab = (float(pos[0]) - self.fab_x, float(pos[1]) - self.fab_y)
        return True

    def handle_fab_mouseup(self, pos: tuple[int, int]) -> bool:
        if self.new_game_menu_open:
            return False
        if self._fab_down is None:
            return False
        was_drag = self._fab_dragging
        self._fab_dragging = False
        self._fab_down = None
        if was_drag:
            return True
        h = fab_hit_at(pos, int(self.fab_x), int(self.fab_y))
        if h[0] == "algo" and h[1]:
            self.pressed_button_label = h[1]
            self.pressed_button_until = time() + 0.12
            if self._solver_thread and self._solver_thread.is_alive():
                self.set_status("Solver dang chay! Vui long doi...", 2.0)
            else:
                self.run_solver(h[1])
        elif h[0] == "main" and h[1]:
            self.pressed_button_label = h[1]
            self.pressed_button_until = time() + 0.12
            self._fab_dispatch_main(h[1])
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

    def open_new_game_menu(self) -> None:
        self.new_game_menu_open = True
        self.new_game_menu_hover = None
        self.new_game_menu_mode = "difficulty"
        self.new_game_menu_category = None
        self.drag = None
        self.mouse_down_pos = None

    def _build_generated_state(self, category: str, level: int) -> GameState:
        """Generate a fresh deal using freecell/generate_test.py at a specific LEVEL."""
        generate_test.LEVEL = level
        generate_test.MOVES, generate_test.BLOCK_DEPTH, generate_test.MIN_SEQ, generate_test.NOISE = generate_test.LEVEL_CONFIG[level]
        nums_tableau, _ = generate_test.generate()
        state = GameState()
        for col_idx, col in enumerate(nums_tableau):
            if col_idx >= len(state.tableau):
                break
            state.tableau[col_idx] = [get_card_from_str(generate_test.card_str(n)) for n in col]
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
        self.pressed_button_label = ""
        self.pressed_button_until = 0.0
        self.paused = False
        self._fab_down = None
        self._fab_dragging = False
        self.new_game_menu_open = False
        self.new_game_menu_hover = None

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
        self.pressed_button_label = ""
        self.pressed_button_until = 0.0
        self.paused = False
        self._fab_down = None
        self._fab_dragging = False
        self.new_game_menu_open = False
        self.new_game_menu_hover = None
        self.new_game_menu_mode = "difficulty"
        self.new_game_menu_category = None

    def _new_game_menu_button_rects(self) -> list[tuple[pygame.Rect, str]]:
        sw, sh = self.screen.get_size()
        if self.new_game_menu_mode == "difficulty":
            opts = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]
        else:
            cat = self.new_game_menu_category or DEFAULT_NEW_GAME_DIFFICULTY
            lo, hi = NEW_GAME_LEVEL_RANGES[cat]
            opts = [(str(lvl), str(lvl)) for lvl in range(lo, hi + 1)]
        bw, bh = 168, 52
        gap = 14
        total_w = len(opts) * bw + (len(opts) - 1) * gap
        x0 = (sw - total_w) // 2
        y0 = sh // 2 - 10
        return [
            (pygame.Rect(x0 + i * (bw + gap), y0, bw, bh), opts[i][0])
            for i in range(len(opts))
        ]

    def _handle_new_game_menu_click(self, pos: tuple[int, int]) -> bool:
        for rect, key in self._new_game_menu_button_rects():
            if rect.collidepoint(pos):
                if self.new_game_menu_mode == "difficulty":
                    self.new_game_menu_mode = "levels"
                    self.new_game_menu_category = key
                    self.new_game_menu_hover = None
                    return True
                # levels mode
                try:
                    lvl = int(key)
                except ValueError:
                    return True
                cat = self.new_game_menu_category or DEFAULT_NEW_GAME_DIFFICULTY
                self._apply_new_deal(cat, lvl)
                return True
        self.new_game_menu_open = False
        self.new_game_menu_hover = None
        self.new_game_menu_mode = "difficulty"
        self.new_game_menu_category = None
        return True

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

        self.set_status(f"Dang giai bang {label}... Vui long doi...", 100.0)
        self._solver_result = None
        self._solver_label = label
        self._solver_started_at = time()
        self._solver_timed_out = False
        self.solver_game_over = False
        self._solver_cancel_event.clear()

        # Deepcopy state passing to background thread to avoid conflict with main thread
        state_copy = deepcopy(self.state)
        self._solver_thread = threading.Thread(
            target=self._run_solver_task,
            args=(label, state_copy),
            daemon=True
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
        self.add_score(-5)   # penalty for undo
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

    def start_state_transition_animation(self, from_state: GameState, to_state: GameState, duration: float = 0.16) -> None:
        """Animate cards between two board states (used for undo/redo)."""
        self.transition_anims.clear()
        from_pos = self.card_positions(from_state)
        to_pos = self.card_positions(to_state)
        moved_cards = [card for card in from_pos if card in to_pos and from_pos[card] != to_pos[card]]
        for card in moved_cards:
            sx, sy = from_pos[card]
            ex, ey = to_pos[card]
            self.transition_anims.append(
                CardAnimation(card=card, tween=Tween(sx, sy, ex, ey, duration), x=sx, y=sy)
            )

    def source_at_pos(self, pos: tuple[int, int], top_only_tableau: bool = False) -> tuple[PileRef, int] | None:
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

    def start_drop_animation(self, cards: list, dst: PileRef, start_x: float, start_y: float) -> None:
        end_x, end_y = self.card_position_for_destination(dst, len(cards))
        tween = Tween(start_x, start_y, end_x, end_y, DROP_ANIM_DURATION)
        self.drop_anim = DropAnimation(cards=cards, tween=tween, dst=dst, count=len(cards), x=start_x, y=start_y)

    def card_position_for_destination(self, dst: PileRef, count: int) -> tuple[float, float]:
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

    def card_source_position(self, src: PileRef, start_index: int = -1) -> tuple[float, float]:
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
        cards = [self.state.tableau[src.index][-1]] if src.kind == PileType.TABLEAU else []
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
            candidates = [i for i, c in enumerate(self.state.free_cells) if c is None and i != src.index]
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
        empty_free = next((i for i, c in enumerate(self.state.free_cells) if c is None), None)
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
                if validate_move(self.state, src, PileRef(PileType.FREECELL, i), cards).ok:
                    targets.add(("freecell", i))
            for i in range(4):
                if validate_move(self.state, src, PileRef(PileType.FOUNDATION, i), cards).ok:
                    targets.add(("foundation", i))
            for i in range(8):
                if validate_move(self.state, src, PileRef(PileType.TABLEAU, i), cards).ok:
                    targets.add(("tableau", i))
        return targets

    def update(self, dt: float) -> None:
        self._update_fab_hover()
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
                        f"Giai xong voi {self._solver_label}! Dang choi thu...", 3.0
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
            self.start_state_transition_animation(old_state, self.state, duration=0.15)

        if self.drag:
            mx, my = pygame.mouse.get_pos()
            self.drag.target_x = mx - self.drag.offset_x
            self.drag.target_y = my - self.drag.offset_y
            self.drag.smooth_x += (self.drag.target_x - self.drag.smooth_x) * DRAG_SMOOTH_FACTOR
            self.drag.smooth_y += (self.drag.target_y - self.drag.smooth_y) * DRAG_SMOOTH_FACTOR
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
        self.renderer.draw_static_board(self.layout, self.state, highlight_targets=self.collect_highlight_targets())

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
                hidden_from = len(self.state.tableau[self.drop_anim.dst.index]) - self.drop_anim.count
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
        self.renderer.draw_footer_bar(
            self.score,
            self.elapsed,
            self.moves,
            n_found,
            self.active_deal_label,
            n_fc,
        )

        if self.status_text and time() <= self.status_until:
            font = pygame.font.SysFont("segoeui", 24, bold=True)
            msg = font.render(self.status_text, True, (255, 216, 120))
            self.screen.blit(msg, (24, self.screen.get_height() - FOOTER_HEIGHT - 36))

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
                    f"Memory Usage: {stats.get('memory_usage_bytes', 0)} bytes"
                ]
                if 'depth_reached' in stats:
                    lines.append(f"Depth Reached: {stats['depth_reached']}")

                sy = self.screen.get_height() // 2 + 60
                for line in lines:
                    text_surface = font.render(line, True, (255, 255, 255))
                    tw = text_surface.get_width()
                    self.screen.blit(text_surface, (self.screen.get_width() // 2 - tw // 2, sy))
                    sy += 36

        elif self.paused:
            self.renderer.draw_pause_overlay()

        pm, pa = self._fab_pressed_flash()
        self.renderer.draw_floating_toolbar(
            int(self.fab_x),
            int(self.fab_y),
            self.fab_hover_main,
            self.fab_hover_algo,
            pm,
            pa,
            self._fab_dragging,
        )
        if self.new_game_menu_open:
            self.renderer.draw_new_game_menu(
                self.new_game_menu_mode,
                self.new_game_menu_category,
                self.new_game_menu_hover,
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
                        if self.new_game_menu_open:
                            self.new_game_menu_open = False
                            self.new_game_menu_hover = None
                        else:
                            running = False
                    elif event.key == pygame.K_r:
                        if self.new_game_menu_open:
                            self.new_game_menu_open = False
                            self.new_game_menu_hover = None
                        else:
                            self.retry_current_deal()
                    elif event.key == pygame.K_p:
                        self.toggle_pause()
                    elif not self.paused and event.key == pygame.K_z:
                        self.undo()
                    elif not self.paused and event.key == pygame.K_y:
                        self.redo()
                elif event.type == pygame.VIDEORESIZE:
                    # Keep a regular window and re-center board layout on resize.
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.layout.resize(self.screen.get_size())
                    self._clamp_fab()
                elif event.type == pygame.MOUSEMOTION:
                    if self.new_game_menu_open:
                        self.new_game_menu_hover = None
                        for rect, key in self._new_game_menu_button_rects():
                            if rect.collidepoint(event.pos):
                                self.new_game_menu_hover = key
                                break
                    self.handle_fab_mousemove(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.new_game_menu_open:
                        self._handle_new_game_menu_click(event.pos)
                        continue
                    if self.handle_fab_mousedown(event.pos):
                        continue
                    if self.paused:
                        continue
                    if self.state.won or self.solver_game_over:
                        continue
                    # pygame 2 provides event.clicks; fallback to timestamp check.
                    is_double = bool(getattr(event, "clicks", 0) >= 2)
                    now = time()
                    if not is_double and now - self.last_click_at <= DOUBLE_CLICK_SECONDS:
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
                    if self.new_game_menu_open:
                        continue
                    if self.handle_fab_mouseup(event.pos):
                        continue
                    if self.state.won or self.solver_game_over:
                        continue
                    if self.paused:
                        continue
                    # Click without drag: try auto-move top card to foundation.
                    if self.mouse_down_pos and self.drag:
                        dx = abs(event.pos[0] - self.mouse_down_pos[0])
                        dy = abs(event.pos[1] - self.mouse_down_pos[1])
                        if dx <= 4 and dy <= 4 and len(self.drag.cards) == 1:
                            if self.try_auto_move_from_source(self.drag.src, self.drag.start_index):
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

