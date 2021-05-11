from .shared import LimitedUse, Sourced


class Feat(Sourced):
    entity_type = 'feat'
    type_id = 1088085227

    def __init__(self, name, desc, prerequisite=None, ability=None, limited_use=None, **kwargs):
        """
        :type name: str
        :type desc: str
        :type prerequisite: str or None
        :type ability: list[str]
        :type limited_use: list[LimitedUse]
        """
        if ability is None:
            ability = []
        if limited_use is None:
            limited_use = []

        super().__init__(False, **kwargs)
        self.name = name
        self.desc = desc
        self.prerequisite = prerequisite
        self.ability = ability
        self.limited_use = limited_use

    @classmethod
    def from_data(cls, d):
        inst = cls(d['name'], d['description'],
                   d.get('prerequisite'), d.get('ability'), [],
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
        inst.limited_use = [LimitedUse.from_dict(lu, inst) for lu in d.get('grantedLimitedUse', [])]
        return inst


class FeatOption(Sourced):
    entity_type = 'feat-option'
    type_id = 400581042
    # feat options give no limited use features right now, so this is only here for parity
