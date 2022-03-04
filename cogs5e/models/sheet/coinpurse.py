from cogs5e.models.errors import InvalidArgument
from .mixins import HasIntegrationMixin
from utils.functions import confirm

CoinTypes = {
    "pp": {
        "icon": "<:DDBPlatinum:948681049326624849>",
        "name": "Platinum",
        "gSheet": {
            "v14": "D72",
            "v2": "D15",
        }
    },
    "gp": {
        "icon": "<:DDBGold:948681049221775370>",
        "name": "Gold",
        "gSheet": {
            "v14": "D69",
            "v2": "D12",
        }
    },
    "ep": {
        "icon": "<:DDBElectrum:948681048932364401>",
        "name": "Electrum",
        "gSheet": {
            "v14": "D66",
            "v2": "D9",
        }
    },
    "sp": {
        "icon": "<:DDBSilver:948681049288867930>",
        "name": "Silver",
        "gSheet": {
            "v14": "D63",
            "v2": "D6",
        }
    },
    "cp": {
        "icon": "<:DDBCopper:948681049217597480>",
        "name": "Copper",
        "gSheet": {
            "v14": "D60",
            "v2": "D3",
        }
    }
}


class Coinpurse(HasIntegrationMixin):
    def __init__(self, pp=0, gp=0, ep=0, sp=0, cp=0):
        super().__init__()
        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

    def __str__(self):
        return "\n".join(self.str_styled(coin_type) for coin_type in CoinTypes)

    def str_styled(self, coin_type):
        if coin_type not in ("compact", "pp", "gp", "ep", "sp", "cp"):
            raise ValueError("coin_type must be in ('compact', 'pp', 'gp', 'ep', 'sp', 'cp')")

        if coin_type == 'compact':
            coin_value = self.total
            coin_type = 'gp'
            style = ",.2f"
        else:
            coin_value = getattr(self, coin_type)
            style = ","
        return f"{CoinTypes[coin_type]['icon']} {coin_type}: {coin_value:{style}}"

    @property
    def total(self):
        total = self.gp
        total += self.pp * 10
        total += self.ep * 0.5
        total += self.sp * 0.1
        total += self.cp * 0.01
        return total

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
            sp_change = ((cp_change + temp_cp) // 10)
            cp_change += (-1 * sp_change * 10)
        if temp_sp + sp_change < 0:
            ep_change = ((sp_change + temp_sp) // 5)
            sp_change += (-1 * ep_change * 5)
            temp_sp += (ep_change * 5)
        if temp_ep + ep_change < 0:
            gp_change = ((ep_change + temp_ep) // 2)
            ep_change += (-1 * gp_change * 2)
            temp_ep += (gp_change * 2)
        if temp_gp + gp_change < 0:
            pp_change = ((gp_change + temp_gp) // 10)
            gp_change += (-1 * pp_change * 10)
        if temp_pp + pp_change < 0:
            raise InvalidArgument("You do not have enough coins to cover this transaction.")
        print(pp_change, gp_change, ep_change, sp_change, cp_change)
        return pp_change, gp_change, ep_change, sp_change, cp_change

    async def update_currency(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0,
                              explicit: bool = False, ctx=None):
        if not all((
            isinstance(pp, int),
            isinstance(gp, int),
            isinstance(ep, int),
            isinstance(sp, int),
            isinstance(cp, int)
        )):
            raise TypeError("All values must be numeric.")

        if not all((
            self.pp + pp >= 0,
            self.gp + gp >= 0,
            self.ep + ep >= 0,
            self.sp + sp >= 0,
            self.cp + cp >= 0
        )):
            if explicit and not await confirm(ctx, "You don't have enough of the chosen coins to complete this transaction. "
                                                   "Auto convert from larger coins? (Reply with yes/no)"):
                raise InvalidArgument("You cannot put a currency into negative numbers.")
            pp, gp, ep, sp, cp = self.auto_convert(pp, gp, ep, sp, cp)

        self.pp += pp
        self.gp += gp
        self.ep += ep
        self.sp += sp
        self.cp += cp

        if self._live_integration:
            self._live_integration.sync_coins()

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
