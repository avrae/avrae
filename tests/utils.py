import pytest

from cogs5e.funcs.lookupFuncs import compendium

# commonly used patterns

# rolled dice: the individual results of dice
# matches:
# (5)
# (~~13~~, 16, ~~**1**~~)
# (1 -> 4, 5, 4)
# (4, ~~2 -> 4~~, ~~1 -> 4~~)
# (5 -> **6**, 5 -> **6**, ~~1 -> **6**~~)
ROLLED_DICE_PATTERN = r"\((~*(\**\d+\**( -> )?)+~*(, )?)+\)"

# d20: 1d20 or advantage variants plus potential modifier and result after
# matches:
# 1d20 (5)
# 1d20 (12) + 3
# 1d20 (**1**) - 1 = `0`
# 1d20 (**20**)
# 2d20kh1 (15, ~~2~~) = `15`
# 3d20kh1 (~~13~~, 16, ~~**1**~~)
D20_PATTERN = rf"\d?d20(\w+[lh<>]?\d+)? *{ROLLED_DICE_PATTERN}( *[+-] *\d+)?( *= *`\d+`)?"

# dice: any combination of valid dice, rolled or unrolled
DICE_PATTERN = rf"( *((\d*d\d+(\w+[lh<>]?\d+)?( *{ROLLED_DICE_PATTERN})?)|\d+|( *[-+*/]))( *\[.*\])?)+( *= *`\d+`)?"

# to hit: a to-hit section of an attack
TO_HIT_PATTERN = rf"\*\*To Hit:\*\* ({D20_PATTERN}{DICE_PATTERN} = `\d+`)|(Automatic (hit|miss)!)"

# damage: a damage section of an attack
DAMAGE_PATTERN = rf"(\*\*Damage (\(CRIT!\))?:\*\* {DICE_PATTERN})|(\*\*Miss!\*\*)"

# attack: to hit and damage on two lines
ATTACK_PATTERN = rf"{TO_HIT_PATTERN}\n{DAMAGE_PATTERN}"


def requires_data(datatypes=None):
    """A wrapper that skips a test if data is not loaded."""
    if datatypes is None:
        datatypes = ["spells"]  # generally, if spells aren't loaded, nothing is
    if isinstance(datatypes, str):
        datatypes = [datatypes]

    for datatype in datatypes:
        if not getattr(compendium, datatype, None):
            return pytest.mark.skip(reason=f"Test requires {datatype} data")

    return lambda func: func
