"""
Solver tích hợp: ghép BFS, IDS, UCS, A* từ các module riêng.

- `skill.py`: nền chung (hash, move gen, heuristic, cost, auto-foundation, …)
- `bfs.py`, `ids.py`, `ucs.py`, `astar.py`: từng thuật toán
"""

from __future__ import annotations

from .astar import AstarSolverMixin
from .bfs import BfsSolverMixin
from .ids import IdsSolverMixin
from .skill import (
    DEBUG_STATS,
    FreeCellSolverBase,
    MoveCostConfig,
    REPORT_INTERVAL_BFS_IDS,
    REPORT_INTERVAL_UCS_ASTAR,
)
from .ucs import UcsSolverMixin


class FreeCellSolver(
    BfsSolverMixin,
    IdsSolverMixin,
    UcsSolverMixin,
    AstarSolverMixin,
    FreeCellSolverBase,
):
    """Gộp BFS, IDS, UCS, A*; cùng chung cơ sở trong `FreeCellSolverBase` (skill.py)."""

    pass


__all__ = [
    "DEBUG_STATS",
    "FreeCellSolver",
    "MoveCostConfig",
    "REPORT_INTERVAL_BFS_IDS",
    "REPORT_INTERVAL_UCS_ASTAR",
]
