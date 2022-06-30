"""
entity types and ids

RPGAdventuringGear    adventuring-gear   2103445194
RPGArmor              armor              701257905
RPGMagicItem          magic-item         112130694
RPGWeapon             weapon             1782728300
"""

import abc

from .mixins import DescribableMixin
from .shared import Sourced


class Item(DescribableMixin, Sourced, abc.ABC):
    def __init__(
        self, name: str, desc: str, attunement: bool | str, meta: str | None = None, image: str | None = None, **kwargs
    ):
        super().__init__(**kwargs)
        self.name = name
        self.desc = desc
        self.attunement = attunement
        self.meta = meta
        self.image = image

    @classmethod
    def from_data(cls, d):
        return cls(
            d["name"],
            d["desc"],
            d["attunement"],
            d.get("meta"),
            d.get("image"),
            homebrew=False,
            source=d["source"],
            entity_id=d["id"],
            page=d["page"],
            url=d["url"],
            is_free=d["isFree"],
            is_legacy=d.get("isLegacy", False),
        )

    @classmethod
    def from_homebrew(cls, d, source):
        return cls(d["name"], d["desc"], False, d.get("meta"), d.get("image"), source=source, homebrew=True)

    @property
    def description(self):
        return self.desc


class AdventuringGear(Item):
    entity_type = "adventuring-gear"
    type_id = 2103445194


class Armor(Item):
    entity_type = "armor"
    type_id = 701257905


class MagicItem(Item):
    entity_type = "magic-item"
    type_id = 112130694


class Weapon(Item):
    entity_type = "weapon"
    type_id = 1782728300


class HomebrewItem(MagicItem):
    """
    Avrae homebrew items don't really care about their item type - we just call them all magic items but give them their
    own class to separate them
    """

    pass
