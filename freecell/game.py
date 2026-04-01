"""Main pygame loop and player interaction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from time import time
import threading
import threading

import pygame

from .animation import Tween
from .constants import (
    DOUBLE_CLICK_SECONDS,
    DRAG_SMOOTH_FACTOR,
    FPS,
    DROP_ANIM_DURATION,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TITLE,
)
from .layout import BoardLayout
from .rules import PileRef, PileType, apply_move, tableau_descending_alternating, validate_move
from .models import Card, Suit
from .state import GameState, deal_new_game, generate_state_testcase
from .ui import Renderer
from .algorithm import FreeCellSolver


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

        self.state: GameState = generate_state_testcase(2)
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
        self.transition_anims: list[CardAnimation] = []
        self.auto_foundation_active = False
        self.solution_moves: list = []
        # UI state
        self.game_id: int = 2  # endgame demo (BFS ~4 moves)
        self.score: int = 0
        self.elapsed: float = 0.0
        self.pressed_button_label: str = ""
        self.pressed_button_until: float = 0.0

    def set_status(self, message: str, seconds: float = 1.2) -> None:
        self.status_text = message
        self.status_until = time() + seconds

    def new_game(self) -> None:
        self.state = generate_state_testcase(2)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.drag = None
        self.drop_anim = None
        self.status_text = ""
        self.status_until = 0.0
        self.solver_stats = None
        self._solver_thread = None
        self._solver_result = None
        self.auto_foundation_active = False
        self.transition_anims.clear()
        self.solution_moves = []
        self.score = 0
        self.elapsed = 0.0
        self.pressed_button_label = ""
        self.pressed_button_until = 0.0

    def add_score(self, delta: int) -> None:
        """Add delta to score, clamped to >= 0."""
        self.score = max(0, self.score + delta)

    def action_buttons(self) -> list[tuple[str, pygame.Rect]]:
        """Bottom toolbar: [New][Undo][Hint][DFS][BFS][UCS][A*] left | [More] right."""
        W = self.screen.get_width()
        btn_h = 46
        y = self.screen.get_height() - btn_h - 14

        # Left group — wider buttons with generous gap
        specs = [("New", 106), ("Undo", 114), ("Hint", 100),
                 ("IDS", 88), ("BFS", 88), ("UCS", 88), ("A*", 76)]
        gap = 12
        x = 14
        out: list[tuple[str, pygame.Rect]] = []
        for label, w in specs:
            out.append((label, pygame.Rect(x, y, w, btn_h)))
            x += w + gap

        # Right: More
        more_w = 106
        out.append(("More", pygame.Rect(W - more_w - 14, y, more_w, btn_h)))
        return out

    def handle_button_click(self, pos: tuple[int, int]) -> bool:
        for label, rect in self.action_buttons():
            if not rect.collidepoint(pos):
                continue
            # Visual press effect — show highlight for 0.12s
            self.pressed_button_label = label
            self.pressed_button_until = time() + 0.12
            if label == "New":
                self.new_game()
            elif label == "Undo":
                self.undo()
            elif label in ("IDS", "BFS", "UCS", "A*"):
                if self._solver_thread and self._solver_thread.is_alive():
                    self.set_status("Solver dang chay! Vui long doi...", 2.0)
                else:
                    self.run_solver(label)
            elif label in ("Hint", "More"):
                pass  # chưa có chức năng
            return True
        return False

    def _run_solver_task(self, label: str, state_copy: GameState) -> None:
        solver = FreeCellSolver(state_copy)
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
        
        # Deepcopy state passing to background thread to avoid conflict with main thread
        state_copy = deepcopy(self.state)
        self._solver_thread = threading.Thread(
            target=self._run_solver_task,
            args=(label, state_copy),
            daemon=True
        )
        self._solver_thread.start()

    def push_undo_snapshot(self) -> None:
        self.undo_stack.append(deepcopy(self.state))
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            self.set_status("Khong con nuoc de undo.")
            return
        self.solution_moves.clear()
        old_state = deepcopy(self.state)
        self.redo_stack.append(deepcopy(self.state))
        self.state = self.undo_stack.pop()
        self.add_score(-5)   # penalty for undo
        self.start_state_transition_animation(old_state, self.state)
        self.drag = None
        self.drop_anim = None
        self.auto_foundation_active = False

    def redo(self) -> None:
        if not self.redo_stack:
            self.set_status("Khong co nuoc de redo.")
            return
        self.solution_moves.clear()
        old_state = deepcopy(self.state)
        self.undo_stack.append(deepcopy(self.state))
        self.state = self.redo_stack.pop()
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

        for i, rect in enumerate(self.layout.foundations):
            suit = list(self.state.foundations.keys())[i]
            if rect.collidepoint(pos) and self.state.foundations[suit]:
                return PileRef(PileType.FOUNDATION, i), -1

        for col_idx, rect in enumerate(self.layout.tableau):
            if not rect.inflate(0, 560).collidepoint(pos):
                continue
            col = self.state.tableau[col_idx]
            if not col:
                continue
            idx = self.layout.tableau_pick_index(col_idx, pos, len(col))
            if top_only_tableau and idx != len(col) - 1:
                return None
            return PileRef(PileType.TABLEAU, col_idx), idx
        return None

    def try_pick_from_pos(self, pos: tuple[int, int]) -> None:
        if self.drop_anim or (self._solver_thread and self._solver_thread.is_alive()) or self.solution_moves or self.transition_anims:
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

        # Foundation slots
        for i, rect in enumerate(self.layout.foundations):
            suit = list(self.state.foundations.keys())[i]
            pile = self.state.foundations[suit]
            if rect.collidepoint(pos) and pile:
                card = pile[-1]
                self.drag = DragState(
                    src=PileRef(PileType.FOUNDATION, i),
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
        for col_idx, rect in enumerate(self.layout.tableau):
            if not rect.inflate(0, 560).collidepoint(pos):
                continue
            col = self.state.tableau[col_idx]
            if not col:
                continue

            start_idx = self.layout.tableau_pick_index(col_idx, pos, len(col))
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
        if src.kind == PileType.FOUNDATION:
            suit = list(self.state.foundations.keys())[src.index]
            pile = self.state.foundations[suit]
            cards = [pile[-1]] if pile else []
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
                    self.start_drop_animation(moved_cards, dst, sx, sy)
                    return True
            return False

        # 4) For double-click from tableau/foundation with no legal target, park into empty free cell.
        empty_free = next((i for i, c in enumerate(self.state.free_cells) if c is None), None)
        if empty_free is not None:
            dst = PileRef(PileType.FREECELL, empty_free)
            if validate_move(self.state, src, dst, cards).ok:
                self.push_undo_snapshot()
                sx, sy = self.card_source_position(src, start_index)
                res, moved_cards = apply_move(self.state, src, dst, start_index)
                if res.ok:
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
        # Advance game timer
        if not self.state.won:
            self.elapsed += dt

        # Check if background solver finished
        if self._solver_thread and not self._solver_thread.is_alive():
            if self._solver_result is not None:
                stats = self._solver_result
                if stats and stats.get("path") is not None:
                    self.solver_stats = stats
                    self.solution_moves = stats["path"].copy()
                    self.set_status(f"Giai xong voi {self._solver_label}! Dang choi thu...", 3.0)
                else:
                    self.set_status(f"{self._solver_label} khong the tim ra duong giai.", 3.0)
                    self.solver_stats = None
                self._solver_result = None
            self._solver_thread = None

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
        self.renderer.draw_header(self.score, self.elapsed)
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

        if self.state.won:
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

        if self.status_text and time() <= self.status_until:
            font = pygame.font.SysFont("segoeui", 24, bold=True)
            msg = font.render(self.status_text, True, (255, 216, 120))
            self.screen.blit(msg, (24, self.screen.get_height() - 68))

        self.renderer.draw_action_buttons(
            self.action_buttons(),
            pressed=self.pressed_button_label if time() <= self.pressed_button_until else "",
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
                        running = False
                    elif event.key == pygame.K_r:
                        self.new_game()
                    elif event.key == pygame.K_z:
                        self.undo()
                    elif event.key == pygame.K_y:
                        self.redo()
                elif event.type == pygame.VIDEORESIZE:
                    # Keep a regular window and re-center board layout on resize.
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.layout.resize(self.screen.get_size())
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.handle_button_click(event.pos):
                        continue
                    if self.state.won:
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
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and not self.state.won:
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

