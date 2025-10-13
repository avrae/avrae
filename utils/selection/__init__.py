"""
Selection system for interactive user choices.

This package provides a unified selection system supporting both button-based
and text-based user interactions for choosing from lists of options.
"""

from .selection import get_selection_with_buttons
from .selection_monster import select_monster_with_dm_feedback
from .selection_views import (
    StatelessSelectionView,
    create_selection_embed,
    create_pm_selection_embed,
    update_selection_view,
    set_expired_view,
)
from .selection_helpers import text_input_check

__all__ = (
    # Main selection functions
    "get_selection_with_buttons",
    "select_monster_with_dm_feedback",
    "text_input_check",
    # UI components
    "StatelessSelectionView",
    "create_selection_embed",
    "create_pm_selection_embed",
    "update_selection_view",
    "set_expired_view",
)
