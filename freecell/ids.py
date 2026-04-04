"""Iterative Deepening Search (IDS)."""

from __future__ import annotations

import sys
import time

from .rules import apply_move
from .skill import (
    FreeCellSolverBase,
    REPORT_INTERVAL_BFS_IDS,
    SOLVER_IDS_CANCELLED,
)


class IdsSolverMixin:
    def ids_solving(self, max_depth: int = 100) -> dict:
        assert isinstance(self, FreeCellSolverBase)
        start_time = time.time()
        expanded_nodes = 0

        global_visited: dict = {}

        def dls(state, depth_limit, current_depth, last_move, path, path_set):
            nonlocal expanded_nodes
            expanded_nodes += 1
            if self._solver_cancelled():
                return SOLVER_IDS_CANCELLED

            self._report_stats(
                "IDS",
                start_time,
                expanded_nodes,
                len(path),
                current_depth,
                interval=REPORT_INTERVAL_BFS_IDS,
            )

            if self.is_win_state(state):
                return list(path)

            if current_depth >= depth_limit:
                return None

            remaining = depth_limit - current_depth

            for move in self.get_all_possible_move(state):
                if self._solver_cancelled():
                    return SOLVER_IDS_CANCELLED

                if last_move and move[0] == last_move[1] and move[1] == last_move[0]:
                    continue

                _, moved = apply_move(state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation_v2(state)

                s_hash = self.hash_state(state)
                if (
                    s_hash in global_visited and global_visited[s_hash] >= remaining - 1
                ) or (s_hash in path_set):
                    from .rules import undo_move

                    for i in range(len(auto_moves) - 1, -1, -1):
                        undo_move(
                            state, auto_moves[i][0], auto_moves[i][1], auto_cards[i]
                        )
                    undo_move(state, move[0], move[1], moved)
                    continue

                global_visited[s_hash] = remaining - 1
                path_set.add(s_hash)
                path.append(move)
                path.extend(auto_moves)

                result = dls(
                    state, depth_limit, current_depth + 1, move, path, path_set
                )
                if result is SOLVER_IDS_CANCELLED:
                    return SOLVER_IDS_CANCELLED
                if result is not None:
                    return result

                for _ in range(len(auto_moves) + 1):
                    path.pop()
                path_set.remove(s_hash)

                from .rules import undo_move

                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(state, auto_moves[i][0], auto_moves[i][1], auto_cards[i])
                undo_move(state, move[0], move[1], moved)

            return None

        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation_v2(initial_state)
        init_hash = self.hash_state(initial_state)

        if self.is_win_state(initial_state):
            return {
                "path": init_auto,
                "search_time": time.time() - start_time,
                "expanded_nodes": expanded_nodes,
                "search_length": len(init_auto),
            }

        for d_limit in range(1, max_depth + 1):
            if self._solver_cancelled():
                return self._return_cancelled(
                    start_time,
                    expanded_nodes,
                    memory_usage_bytes=sys.getsizeof(global_visited)
                    + len(global_visited) * (sys.getsizeof(init_hash) + 28),
                )

            path_set = {init_hash}
            res = dls(initial_state, d_limit, 0, None, list(init_auto), path_set)

            if res is SOLVER_IDS_CANCELLED:
                return self._return_cancelled(
                    start_time,
                    expanded_nodes,
                    memory_usage_bytes=sys.getsizeof(global_visited)
                    + len(global_visited) * (sys.getsizeof(init_hash) + 28),
                )

            if res is not None:
                memory_usage = (
                    sys.getsizeof(global_visited)
                    + len(global_visited) * (sys.getsizeof(init_hash) + 28)
                    + sys.getsizeof(path_set)
                )
                return {
                    "path": res,
                    "search_time": time.time() - start_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(res),
                    "depth_reached": d_limit,
                    "memory_usage_bytes": memory_usage,
                }

        search_time = time.time() - start_time
        return {
            "path": None,
            "search_time": search_time,
            "expanded_nodes": expanded_nodes,
            "memory_usage_bytes": sys.getsizeof(global_visited)
            + len(global_visited) * (sys.getsizeof(init_hash) + 28),
        }
