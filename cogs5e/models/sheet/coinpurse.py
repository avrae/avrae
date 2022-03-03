from cogs5e.models.errors import InvalidArgument
from .mixins import HasIntegrationMixin

CoinTypes = {
    "pp": {
        "icon": "<:DDBPlatinum:948681049326624849>",
        "name": "Platinum"
    },
    "gp": {
        "icon": "<:DDBGold:948681049221775370>",
        "name": "Gold"
    },
    "ep": {
        "icon": "<:DDBElectrum:948681048932364401>",
        "name": "Electrum"
    },
    "sp": {
        "icon": "<:DDBSilver:948681049288867930>",
        "name": "Silver"
    },
    "cp": {
        "icon": "<:DDBCopper:948681049217597480>",
        "name": "Copper"
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
        return (f"{self.pp:,} pp\n"
                f"{self.gp:,} gp\n"
                f"{self.ep:,} ep\n"
                f"{self.sp:,} sp\n"
                f"{self.cp:,} cp")

    @property
    def str_styled(self):
        return (f"{CoinTypes['pp']['icon']} pp: {self.pp:,}\n"
                f"{CoinTypes['gp']['icon']} gp: {self.gp:,}\n"
                f"{CoinTypes['ep']['icon']} ep: {self.ep:,}\n"
                f"{CoinTypes['sp']['icon']} sp: {self.sp:,}\n"
                f"{CoinTypes['cp']['icon']} cp: {self.cp:,}\n")

    def compact_str(self):
        return f"{self.total:,.2f} gp"

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

    def update_currency(self, pp: int = 0, gp: int = 0, ep: int = 0, sp: int = 0, cp: int = 0):
        if not all((
            isinstance(pp, int),
            isinstance(gp, int),
            isinstance(ep, int),
            isinstance(sp, int),
            isinstance(cp, int)
        )):
            raise TypeError("All values must be numeric.")

        if not all((
            True if (self.pp + pp ) >= 0 else False,
            True if (self.gp + gp ) >= 0 else False,
            True if (self.ep + ep ) >= 0 else False,
            True if (self.sp + sp ) >= 0 else False,
            True if (self.cp + cp ) >= 0 else False
        )):
            raise InvalidArgument("You cannot put a currency into negative numbers.")

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
            True if pp >= 0 else False,
            True if gp >= 0 else False,
            True if ep >= 0 else False,
            True if sp >= 0 else False,
            True if cp >= 0 else False
        )):
            raise InvalidArgument("You cannot put a currency into negative numbers.")

        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

        if self._live_integration:
            self._live_integration.sync_coins()
