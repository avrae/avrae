"""
Pagination utilities for selection interfaces.

This module provides efficient pagination functions for UI components.
"""

from typing import List, Any


def get_page_choices(choices: List[Any], page: int, per_page: int = 10) -> List[Any]:
    """Get choices for a specific page without creating all pages."""
    start_idx = page * per_page
    end_idx = start_idx + per_page
    return choices[start_idx:end_idx]


def get_total_pages(choices: List[Any], per_page: int = 10) -> int:
    """Calculate total pages needed for choices."""
    return (len(choices) + per_page - 1) // per_page
