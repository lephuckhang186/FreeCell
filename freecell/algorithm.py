"""
Solver aggregation module.

This module combines various search algorithms (BFS, IDS, UCS, A*) into a single
unified FreeCellSolver class. It leverages mixins and a common base logic
defined in `skill.py` to provide a consistent interface for the UI.
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
    """
    Unified FreeCell Solver.

    Combines multiple search strategies (BFS, IDS, UCS, A*) into one class.
    Each algorithm is provided via a Mixin class. The common logic for
    move generation, state hashing, and auto-foundation moves is inherited
    from `FreeCellSolverBase`.
    """

    pass


__all__ = [
    "DEBUG_STATS",
    "FreeCellSolver",
    "MoveCostConfig",
    "REPORT_INTERVAL_BFS_IDS",
    "REPORT_INTERVAL_UCS_ASTAR",
]
