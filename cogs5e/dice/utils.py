import re

import d20


def string_search_adv(dice_str):
    """
    Given a dice string, returns whether the word adv or dis was found within it, and the string with the word removed.

    >>> string_search_adv("1d20 adv")
    ("1d20", d20.AdvType.ADV)
    >>> string_search_adv("1d20")
    ("1d20", d20.AdvType.NONE)
    """
    adv = d20.AdvType.NONE
    if re.search(r'(^|\s+)(adv|dis)(\s+|$)', dice_str) is not None:
        adv = d20.AdvType.ADV if re.search(r'(^|\s+)adv(\s+|$)', dice_str) is not None else d20.AdvType.DIS
        dice_str = re.sub(r'(adv|dis)(\s+|$)', '', dice_str)
    return dice_str, adv
