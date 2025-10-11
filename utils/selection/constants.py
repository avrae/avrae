"""
Constants for the selection utilities.

This module contains all constants used across the selection system to ensure
consistency and maintainability.
"""

# System Default
ENABLE_BUTTON_SELECTION_DEFAULT = False

# Timeout Values
SELECTION_TIMEOUT = 60.0
DM_NOTIFICATION_TIMEOUT = 15

# Event Limits
MAX_EVENTS = 100

# Pagination
MAX_BUTTONS_PER_ROW = 5  # Change this to auto arrange btns (recommended: 4 or 5)
CHOICES_PER_PAGE = MAX_BUTTONS_PER_ROW * 2  # 2 rows of selection buttons
SELECTION_ROW_1 = 0
SELECTION_ROW_2 = 1
NAVIGATION_ROW = 2

# Action Constants
ACTION_SELECT_PREFIX = "select_"
ACTION_CANCEL = "cancel"
ACTION_NEXT = "next"
ACTION_PREV = "prev"

# Text Commands
TEXT_CMD_NEXT = "n"
TEXT_CMD_PREV = "p"
TEXT_CMD_CANCEL = "c"

# UI Labels
BUTTON_LABEL_PREVIOUS = "◀ Prev"
BUTTON_LABEL_NEXT = "Next ▶"
BUTTON_LABEL_CANCEL = "Cancel"

# Embed Text
EMBED_TITLE_MULTIPLE_MATCHES = "Multiple Matches Found"
EMBED_INSTRUCTION_BASE = "Which one were you looking for? (Type the number or `c` to cancel)"
EMBED_INSTRUCTION_NAVIGATION = "`n` to go to the next page, or `p` for previous"

# Error Messages
ERROR_UNAUTHORIZED_USER = "This menu belongs to someone else. Please start your own command to make a selection."

# Navigation Messages
MSG_ALREADY_LAST_PAGE = "⏭ You're already on the **last** page."
MSG_ALREADY_FIRST_PAGE = "⏮ You're already on the **first** page."

# Monster-Specific Messages
MSG_MONSTER_CANCELLED = "Monster selection cancelled."
MSG_PM_EXPLANATION = "This message was PMed to you to hide the monster name."
