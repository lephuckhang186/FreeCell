"""Breadth-First Search."""

from __future__ import annotations

import sys
import time
from collections import deque

from .rules import apply_move
from .skill import FreeCellSolverBase, REPORT_INTERVAL_BFS_IDS


class BfsSolverMixin:
    def bfs_solving(self) -> dict:
        """
        BFS tối ưu với 3 kỹ thuật:
        1. Parent Tracking
        2. Auto-Foundation
        3. Dead-Move Pruning (trong get_all_possible_move)
        """
        assert isinstance(self, FreeCellSolverBase)
        start_time = time.time()
        expanded_nodes = 0

        initial_state_norm = self.initial_state.clone()
        _, initial_forced_moves = self._apply_forced_foundations(initial_state_norm)
        initial_hash = self.hash_state(initial_state_norm)

        parent: dict[bytes, tuple | None] = {initial_hash: None}
        queue: deque[tuple] = deque([(initial_state_norm, initial_hash, 0)])

        while queue:
            if self._solver_cancelled():
                return self._return_cancelled(start_time, expanded_nodes)

            if expanded_nodes > 0 and expanded_nodes % 2000 == 0:
                time.sleep(0.001)

            current_state, current_hash, depth = queue.popleft()
            expanded_nodes += 1

            self._report_stats(
                "BFS",
                start_time,
                expanded_nodes,
                len(queue),
                depth,
                interval=REPORT_INTERVAL_BFS_IDS,
            )

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(parent) + sys.getsizeof(queue)

                path = []
                h = current_hash
                while parent[h] is not None:
                    par_hash, moves_segment = parent[h]
                    path.extend(reversed(moves_segment))
                    h = par_hash
                path.reverse()
                path = initial_forced_moves + path

                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage,
                }

            possible_moves = self.get_all_possible_move(current_state)

            for move in possible_moves:
                if self._solver_cancelled():
                    return self._return_cancelled(start_time, expanded_nodes)

                new_state = current_state.clone()
                apply_move(new_state, move[0], move[1], move[2])

                _, forced_moves = self._apply_forced_foundations(new_state)

                state_hash = self.hash_state(new_state)
                if state_hash not in parent:
                    moves_segment = [move] + forced_moves
                    parent[state_hash] = (current_hash, moves_segment)
                    queue.append((new_state, state_hash, depth + 1))

        search_time = time.time() - start_time
        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes}
