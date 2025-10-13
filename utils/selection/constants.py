"""
Constants for the selection utilities.

This module contains all constants used across the selection system to ensure
consistency and maintainability.
"""

# System Default
ENABLE_BUTTON_SELECTION_DEFAULT = False

# Timeout Values
SELECTION_TIMEOUT = 60
DM_NOTIFICATION_TIMEOUT = 60

# Event Limits
MAX_EVENTS = 100

# Pagination
MAX_BUTTONS_PER_ROW = 5  # Change this to auto arrange btns (recommended: 4 or 5)
CHOICES_PER_PAGE = MAX_BUTTONS_PER_ROW * 2  # 2 rows of selection buttons
