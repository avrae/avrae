"""
To fix circular import issues, this file exposes the base instance all combatants inherit from
without having to import a bunch of other things.

Yup. It's just an empty class. Small as can be.

Is this an indicator that the init system is too deeply entangled with other systems? Probably.
"""

import enum


class BaseCombatant:
    __slots__ = ()


class CombatantType(enum.Enum):
    GENERIC = "common"
    PLAYER = "player"
    MONSTER = "monster"
    GROUP = "group"
