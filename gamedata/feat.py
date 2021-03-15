from .shared import Sourced


class Feat(Sourced):
    entity_type = 'feat'
    type_id = 1088085227

    def __init__(self, name, desc, prerequisite=None, ability=None, **kwargs):
        """
        :type name: str
        :type desc: str
        :type prerequisite: str or None
        :type ability: list[str]
        """
        if ability is None:
            ability = []

        super().__init__(False, **kwargs)
        self.name = name
        self.desc = desc
        self.prerequisite = prerequisite
        self.ability = ability

    @classmethod
    def from_data(cls, d):
        return cls(d['name'], d['description'],
                   d.get('prerequisite'), d.get('ability'),
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])


class FeatOption(Sourced):
    entity_type = 'feat-option'
    type_id = 400581042
    # feat options give no limited use features right now, so this is only here for parity
