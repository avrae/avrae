from cogs5e.models.errors import InvalidArgument
from .mixins import HasIntegrationMixin
from utils.functions import confirm
from utils.constants import COIN_TYPES


class Coinpurse(HasIntegrationMixin):
    def __init__(self, pp=0, gp=0, ep=0, sp=0, cp=0):
        super().__init__()
        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

    def __str__(self):
        return "\n".join(self.coin_string(coin_type, self.max_length) for coin_type in COIN_TYPES)

    def coin_string(self, coin_type, length=0, delta=0):
        if coin_type not in COIN_TYPES:
            raise ValueError("coin_type must be in ('pp', 'gp', 'ep', 'sp', 'cp')")
        delta_out = ""
        if delta:
            delta_out = f" ({delta:+})"

        style = ","
        coin_value = f"{getattr(self, coin_type):{style}}"
        # Attempt at right aligning coins
        # num_space = "\u2002"
        # if length > 0:
        #     coin_value = f"{coin_value:{num_space}>{length}}".replace("\u2002", "\u200A", 1)
        #     if "," in coin_value:
        #         coin_value = ("\u200A\u200A" * coin_value.count(',')) + coin_value
        return f"{COIN_TYPES[coin_type]['icon']} {coin_value} {coin_type}{delta_out}"

    def compact_string(self, delta=0):
        delta_out = ""
        if delta:
            delta_out = f" ({delta:+,.2f})"
        coin_value = self.total
        coin_type = 'gp'
        return f"{COIN_TYPES[coin_type]['icon']} {coin_value:,.2f} {coin_type}{delta_out}"

    @property
    def max_length(self):
        max_value = f"{max({self.pp, self.gp, self.ep, self.sp, self.cp}):,}"
        return len(str(max_value))

    @property
    def total(self):
        return (self.pp * 10) + self.gp + (self.ep * 0.5) + (self.sp * 0.1) + (self.cp * 0.01)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {
            "pp": self.pp, "gp": self.gp, "ep": self.ep, "sp": self.sp, "cp": self.cp
        }

    def auto_convert(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0):
        temp_pp = self.pp
        temp_gp = self.gp
        temp_ep = self.ep
        temp_sp = self.sp
        temp_cp = self.cp

        pp_change = pp
        gp_change = gp
        ep_change = ep
        sp_change = sp
        cp_change = cp

        if temp_cp + cp_change < 0:
            sp_borrowed = ((cp_change + temp_cp) // 10)
            cp_change -= sp_borrowed * 10
            sp_change += sp_borrowed
        if temp_sp + sp_change < 0:
            ep_borrowed = ((sp_change + temp_sp) // 5)
            sp_change -= ep_borrowed * 5
            ep_change += ep_borrowed
        if temp_ep + ep_change < 0:
            gp_borrowed = ((ep_change + temp_ep) // 2)
            ep_change -= gp_borrowed * 2
            gp_change += gp_borrowed
        if temp_gp + gp_change < 0:
            pp_borrowed = ((gp_change + temp_gp) // 10)
            gp_change -= pp_borrowed * 10
            pp_change += pp_borrowed
        if temp_pp + pp_change < 0:
            raise InvalidArgument("You do not have enough coins to cover this transaction.")
        return pp_change, gp_change, ep_change, sp_change, cp_change

    async def resolve_strict(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0,
                             explicit: bool = False, ctx=None):
        if not all((
            self.pp + pp >= 0,
            self.gp + gp >= 0,
            self.ep + ep >= 0,
            self.sp + sp >= 0,
            self.cp + cp >= 0
        )):
            if explicit and not await confirm(ctx,
                                              "You don't have enough of the chosen coins to complete this transaction. "
                                              "Auto convert from larger coins? (Reply with yes/no)"):
                raise InvalidArgument("You cannot put a currency into negative numbers.")
            pp, gp, ep, sp, cp = self.auto_convert(pp, gp, ep, sp, cp)
        self.update_currency(pp, gp, ep, sp, cp)
        return {"pp": pp, "gp": gp, "ep": ep, "sp": sp, "cp": cp}

    def update_currency(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0):
        self.set_currency(self.pp + pp, self.gp + gp, self.ep + ep, self.sp + sp, self.cp + cp)

    def set_currency(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0):
        if not all((
            isinstance(pp, int),
            isinstance(gp, int),
            isinstance(ep, int),
            isinstance(sp, int),
            isinstance(cp, int)
        )):
            raise TypeError("All values must be numeric.")

        if not all((
            pp >= 0,
            gp >= 0,
            ep >= 0,
            sp >= 0,
            cp >= 0
        )):
            raise InvalidArgument("You cannot put a currency into negative numbers.")

        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

        if self._live_integration:
            self._live_integration.sync_coins()
