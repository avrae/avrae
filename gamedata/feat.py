from .mixins import DescribableMixin, LimitedUseGrantorMixin
from .shared import Sourced


class Feat(LimitedUseGrantorMixin, DescribableMixin, Sourced):
    entity_type = "feat"
    type_id = 1088085227

    def __init__(self, name, desc, prerequisite=None, hidden=False, **kwargs):
        """
        :type name: str
        :type desc: str
        :type prerequisite: str or None
        :type hidden: bool
        """

        super().__init__(homebrew=False, **kwargs)
        self.name = name
        self.desc = desc
        self.prerequisite = prerequisite
        self.hidden = hidden

    @classmethod
    def from_data(cls, d):
        return cls(
            d["name"],
            d["description"],
            d.get("prerequisite"),
            d.get("hidden", False),
            source=d["source"],
            entity_id=d["id"],
            page=d["page"],
            url=d["url"],
            is_free=d["isFree"],
        ).initialize_limited_use(d)

    @property
    def description(self):
        return self.desc


class FeatOption(Sourced):
    entity_type = "feat-option"
    type_id = 400581042
    # feat options give no limited use features right now, so this is only here for parity
