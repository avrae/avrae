from .shared import Sourced


class Feat(Sourced):
    def __init__(self, name, desc, prerequisite=None, ability=None, **kwargs):
        """
        :type name: str
        :type desc: str
        :type prerequisite: str or None
        :type ability: list[str]
        """
        if ability is None:
            ability = []

        super().__init__('feat', False, **kwargs)
        self.name = name
        self.desc = desc
        self.prerequisite = prerequisite
        self.ability = ability

    @classmethod
    def from_data(cls, d):
        return cls(d['name'], d['description'],
                   d.get('prerequisite'), d.get('ability'),
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
