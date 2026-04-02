"""Uniform Cost Search (UCS)."""

from __future__ import annotations

import heapq
import sys
import time

from .rules import apply_move
from .skill import FreeCellSolverBase, MoveCostConfig, REPORT_INTERVAL_UCS_ASTAR


class UcsSolverMixin:
    def ucs_solving(self) -> dict:
        from .rules import undo_move

        assert isinstance(self, FreeCellSolverBase)
        start_time = time.time()
        expanded_nodes = 0

        count = 0
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation_v2(initial_state)

        queue = [(0.0, count, initial_state, init_auto)]
        best_cost = {self.hash_state(initial_state): 0.0}
        config = MoveCostConfig("ucs")

        while queue:
            if self._solver_cancelled():
                return self._return_cancelled(start_time, expanded_nodes)

            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)

            cost, _, current_state, path = heapq.heappop(queue)
            state_hash = self.hash_state(current_state)

            if state_hash in best_cost and best_cost[state_hash] < cost - 0.001:
                continue

            expanded_nodes += 1
            self._report_stats(
                "UCS",
                start_time,
                expanded_nodes,
                len(queue),
                len(path),
                interval=REPORT_INTERVAL_UCS_ASTAR,
            )

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(best_cost) + sys.getsizeof(queue)
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "total_cost": cost,
                    "memory_usage_bytes": memory_usage,
                }

            for move in self.get_all_possible_move(current_state):
                if self._solver_cancelled():
                    return self._return_cancelled(start_time, expanded_nodes)

                move_cost = self.get_move_cost(current_state, move, config)
                new_cost = cost + move_cost

                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation_v2(current_state)

                new_hash = self.hash_state(current_state)
                if new_hash not in best_cost or new_cost < best_cost[new_hash] - 0.001:
                    best_cost[new_hash] = new_cost
                    count += 1
                    new_state = current_state.clone()
                    heapq.heappush(
                        queue, (new_cost, count, new_state, path + [move] + auto_moves)
                    )

                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(
                        current_state, auto_moves[i][0], auto_moves[i][1], auto_cards[i]
                    )
                undo_move(current_state, move[0], move[1], moved)

        return {
            "path": None,
            "search_time": time.time() - start_time,
            "expanded_nodes": expanded_nodes,
        }
