from typing import Optional

from pydantic import conint
from pydantic.color import Color

from . import SettingsBaseModel


class CharacterSettings(SettingsBaseModel):
    # cosmetic
    color: Optional[Color] = None
    embed_image: bool = True

    # gameplay
    crit_on: conint(ge=1, le=20) = 20
    extra_crit_dice: int = 0
    ignore_crit: bool = False
    reroll: Optional[conint(ge=1, le=20)] = None
    talent: bool = False
    srslots: bool = False

    @classmethod
    def from_old_csettings(cls, d):
        """Returns a new CharacterSettings instance with all default options, updated by legacy csettings options."""
        # for each key, get it from old or fall back to class default
        return cls(
            color=d.get('color', cls.color),
            embed_image=d.get('embedimage', cls.embed_image),
            crit_on=d.get('criton', cls.crit_on),
            extra_crit_dice=d.get('critdice', cls.extra_crit_dice),
            ignore_crit=d.get('ignorecrit', cls.ignore_crit),
            reroll=d.get('reroll', cls.reroll),
            talent=d.get('talent', cls.talent),
            srslots=d.get('srslots', cls.srslots)
        )

    async def commit(self, mdb, character):
        """Commits the settings to the database for a given character."""
        await mdb.characters.update_one(
            {"owner": character.owner, "upstream": character.upstream},
            {
                "$set": {"options_v2": self.dict()},
                "$unset": {"options": True}  # delete any old options - they should have been converted by now
            }
        )
