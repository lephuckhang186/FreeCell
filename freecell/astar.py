"""A* Search."""

from __future__ import annotations

import heapq
import sys
import time

from .rules import PileRef, apply_move
from .skill import FreeCellSolverBase, MoveCostConfig, REPORT_INTERVAL_UCS_ASTAR


class AstarSolverMixin:
    def astar_solving(self) -> dict:
        from .rules import undo_move

        assert isinstance(self, FreeCellSolverBase)
        start_time = time.time()
        expanded_nodes = 0
        heuristic_cache: dict[bytes, int] = {}
        move_cache: dict[bytes, list[tuple[PileRef, PileRef, int]]] = {}

        count = 0
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation_v2(initial_state)
        start_hash = self.hash_state(initial_state)
        start_h = self.heuristic(initial_state)
        heuristic_cache[start_hash] = start_h
        queue = [(start_h, count, 0.0, initial_state, start_hash)]
        best_g: dict[bytes, float] = {start_hash: 0.0}
        parent: dict[bytes, tuple[bytes, list[tuple[PileRef, PileRef, int]]] | None] = {
            start_hash: None
        }
        depth_map: dict[bytes, int] = {start_hash: 0}
        config = MoveCostConfig("astar")

        while queue:
            if self._solver_cancelled():
                return self._return_cancelled(start_time, expanded_nodes)

            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)

            _, _, g_cost, current_state, current_hash = heapq.heappop(queue)

            if g_cost > best_g.get(current_hash, float("inf")) + config.EPSILON:
                continue

            expanded_nodes += 1
            self._report_stats(
                "A*",
                start_time,
                expanded_nodes,
                len(queue),
                depth_map.get(current_hash, 0),
                interval=REPORT_INTERVAL_UCS_ASTAR,
            )

            if self.is_win_state(current_state):
                path: list[tuple[PileRef, PileRef, int]] = []
                h = current_hash
                while parent[h] is not None:
                    par_hash, segment = parent[h]
                    path.extend(reversed(segment))
                    h = par_hash
                path.reverse()
                path = init_auto + path

                search_time = time.time() - start_time
                memory_usage = (
                    sys.getsizeof(best_g) + sys.getsizeof(parent) + sys.getsizeof(queue)
                )
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage,
                }

            current_exact_key = self._state_exact_key(current_state)
            moves = move_cache.get(current_exact_key)
            if moves is None:
                moves = self.get_all_possible_move(current_state)
                move_cache[current_exact_key] = moves

            for move in moves:
                if self._solver_cancelled():
                    return self._return_cancelled(start_time, expanded_nodes)

                move_cost = self.get_move_cost(current_state, move, config)
                new_g = g_cost + move_cost

                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation_v2(current_state)

                new_hash = self.hash_state(current_state)
                if new_g + config.EPSILON < best_g.get(new_hash, float("inf")):
                    best_g[new_hash] = new_g
                    segment = [move] + auto_moves
                    parent[new_hash] = (current_hash, segment)
                    depth_map[new_hash] = depth_map.get(current_hash, 0) + len(segment)
                    count += 1
                    new_h = heuristic_cache.get(new_hash)
                    if new_h is None:
                        new_h = self.heuristic(current_state)
                        heuristic_cache[new_hash] = new_h
                    new_f = new_g + new_h
                    new_state = current_state.clone()
                    heapq.heappush(
                        queue,
                        (new_f, count, new_g, new_state, new_hash),
                    )

                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(
                        current_state, auto_moves[i][0], auto_moves[i][1], auto_cards[i]
                    )
                undo_move(current_state, move[0], move[1], moved)

        search_time = time.time() - start_time
        return {
            "path": None,
            "search_time": search_time,
            "expanded_nodes": expanded_nodes,
        }
