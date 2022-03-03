from .mixins import HasIntegrationMixin


class Coinpurse(HasIntegrationMixin):
    def __init__(self, pp=0, gp=0, ep=0, sp=0, cp=0):
        super().__init__()
        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

    def __str__(self):
        return (f"{self.cp:,} cp\n" 
                f"{self.sp:,} sp\n" 
                f"{self.ep:,} ep\n" 
                f"{self.gp:,} gp\n" 
                f"{self.pp:,} pp")

    def compact_str(self):
        total = self.gp
        total += self.pp * 10
        total += self.ep * 0.5
        total += self.sp * 0.1
        total += self.cp * 0.01
        return f"{total:,.2f} gp"

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

        self.pp = pp
        self.gp = gp
        self.ep = ep
        self.sp = sp
        self.cp = cp

        if self._live_integration:
            self._live_integration.sync_coins()
