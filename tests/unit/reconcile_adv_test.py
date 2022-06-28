from utils.enums import AdvantageType
from utils.functions import reconcile_adv


def test_reconcile_adv():
    """
    8 cases: (adv, dis, ea)

    a d e | out
    =======+====
    0 0 0 | 0
    1 0 0 | 1
    1 1 0 | 0
    1 1 1 | 0
    1 0 1 | 2
    0 1 0 | -1
    0 1 1 | 0
    0 0 1 | 2

    """
    assert reconcile_adv(adv=False, dis=False, eadv=False) == AdvantageType.NONE
    assert reconcile_adv(adv=True, dis=False, eadv=False) == AdvantageType.ADV
    assert reconcile_adv(adv=True, dis=True, eadv=False) == AdvantageType.NONE
    assert reconcile_adv(adv=True, dis=True, eadv=True) == AdvantageType.NONE
    assert reconcile_adv(adv=True, dis=False, eadv=True) == AdvantageType.ELVEN
    assert reconcile_adv(adv=False, dis=True, eadv=False) == AdvantageType.DIS
    assert reconcile_adv(adv=False, dis=True, eadv=True) == AdvantageType.NONE
    assert reconcile_adv(adv=False, dis=False, eadv=True) == AdvantageType.ELVEN
