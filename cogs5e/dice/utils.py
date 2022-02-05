import re

import d20

ADV_WORD_RE = re.compile(r'(?:^|\s+)(adv|dis)(?:\s+|$)')


def string_search_adv(dice_str: str):
    """
    Given a dice string, returns whether the word adv or dis was found within it, and the string with the word removed.

    >>> string_search_adv("1d20 adv")
    ("1d20 ", d20.AdvType.ADV)
    >>> string_search_adv("1d20")
    ("1d20", d20.AdvType.NONE)
    """
    adv = d20.AdvType.NONE
    if (match := ADV_WORD_RE.search(dice_str)) is not None:
        adv = d20.AdvType.ADV if match.group(1) == 'adv' else d20.AdvType.DIS
        return dice_str[:match.start(1)] + dice_str[match.end():], adv
    return dice_str, adv
