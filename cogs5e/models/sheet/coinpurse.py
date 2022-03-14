import dataclasses

from cogs5e.models.errors import InvalidArgument
from .mixins import HasIntegrationMixin
from utils.constants import COIN_TYPES


@dataclasses.dataclass
class CoinsArgs:
    pp: int = 0
    gp: int = 0
    ep: int = 0
    sp: int = 0
    cp: int = 0
    explicit: bool = False

    @property
    def total(self) -> float:
        return (self.pp * 10) + self.gp + (self.ep * 0.5) + (self.sp * 0.1) + (self.cp * 0.01)


class Coinpurse(HasIntegrationMixin):
    def __init__(self, pp=0, gp=0, ep=0, sp=0, cp=0):
        super().__init__()
        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

    def __str__(self):
        return "\n".join(self.coin_string(coin_type) for coin_type in COIN_TYPES)

    def coin_string(self, coin_type, delta=0):
        if coin_type not in COIN_TYPES:
            raise ValueError("coin_type must be in ('pp', 'gp', 'ep', 'sp', 'cp')")
        delta_out = ""
        if delta:
            delta_out = f" ({delta:+,})"

        coin_value = f"{getattr(self, coin_type):,}"
        return f"{COIN_TYPES[coin_type]['icon']} {coin_value} {coin_type}{delta_out}"

    def compact_string(self, delta=0):
        delta_out = ""
        if delta:
            delta_out = f" ({delta:+,.2f})"
        return f"{COIN_TYPES['gp']['icon']} {self.total:,.2f} gp{delta_out}"

    @property
    def total(self):
        return (self.pp * 10) + self.gp + (self.ep * 0.5) + (self.sp * 0.1) + (self.cp * 0.01)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"pp": self.pp, "gp": self.gp, "ep": self.ep, "sp": self.sp, "cp": self.cp}

    def auto_convert_down(self, coins: CoinsArgs) -> CoinsArgs:
        """
        Given a CoinsArgs, resolves any negative currencies such that applying it to this coinpurse
        would not make any currency negative. Raises ``InvalidArgument`` if such a resolution
        is impossible.
        This modifies the given ``CoinsArgs`` in place.
        """
        if self.cp + coins.cp < 0:
            sp_borrowed = (coins.cp + self.cp) // 10
            coins.cp -= sp_borrowed * 10
            coins.sp += sp_borrowed
        if self.sp + coins.sp < 0:
            ep_borrowed = (coins.sp + self.sp) // 5
            coins.sp -= ep_borrowed * 5
            coins.ep += ep_borrowed
        if self.ep + coins.ep < 0:
            gp_borrowed = (coins.ep + self.ep) // 2
            coins.ep -= gp_borrowed * 2
            coins.gp += gp_borrowed
        if self.gp + coins.gp < 0:
            pp_borrowed = (coins.gp + self.gp) // 10
            coins.gp -= pp_borrowed * 10
            coins.pp += pp_borrowed
        if self.pp + coins.pp < 0:
            raise InvalidArgument("You do not have enough coins to cover this transaction.")
        return coins

    def consolidate_coins(self) -> CoinsArgs:
        total_cp = self.total * 100
        new_pp = int(total_cp // 1000)
        total_cp -= new_pp * 1000
        new_gp = int(total_cp // 100)
        total_cp -= new_gp * 100
        new_ep = int(total_cp // 50)
        total_cp -= new_ep * 50
        new_sp = int(total_cp // 10)
        total_cp -= new_sp * 10
        new_cp = int(total_cp)

        delta = CoinsArgs(
            pp=new_pp - self.pp, gp=new_gp - self.gp, ep=new_ep - self.ep, sp=new_sp - self.sp, cp=new_cp - self.cp
        )
        self.set_currency(pp=new_pp, gp=new_gp, ep=new_ep, sp=new_sp, cp=new_cp)

        return delta

    def update_currency(self, coins=None):
        self.set_currency(
            self.pp + coins.pp, self.gp + coins.gp, self.ep + coins.ep, self.sp + coins.sp, self.cp + coins.cp
        )

    def set_currency(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0):
        if not all(
            (isinstance(pp, int), isinstance(gp, int), isinstance(ep, int), isinstance(sp, int), isinstance(cp, int))
        ):
            raise TypeError("All values must be numeric.")

        if not all((pp >= 0, gp >= 0, ep >= 0, sp >= 0, cp >= 0)):
            raise InvalidArgument("You cannot put a currency into negative numbers.")

        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

        if self._live_integration:
            self._live_integration.sync_coins()
