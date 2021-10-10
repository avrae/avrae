from .shared import Sourced, Trait


class Background(Sourced):
    entity_type = 'background'
    type_id = 1669830167

    def __init__(self, name, traits, **kwargs):
        """
        :type name: str
        :type traits: list[gamedata.shared.Trait]
        """
        super().__init__(False, **kwargs)
        self.name = name
        self.traits = traits

    @classmethod
    def from_data(cls, d):
        return cls(d['name'],
                   [Trait.from_dict(t) for t in d['traits']],
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
