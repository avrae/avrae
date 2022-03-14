from .mixins import DescribableMixin
from .shared import Sourced


class Item(DescribableMixin, Sourced):
    # not necessarily true for nonmagical items...
    entity_type = "magic-item"
    type_id = 112130694

    def __init__(self, name, desc, attunement, meta=None, image=None, **kwargs):
        """
        :type name: str
        :type desc: str
        :type attunement: bool or str
        :type meta: str or None
        :type image: str or None
        """
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
        )

    @classmethod
    def from_homebrew(cls, d, source):
        return cls(d["name"], d["desc"], False, d.get("meta"), d.get("image"), source=source, homebrew=True)

    @property
    def description(self):
        return self.desc
