from .shared import Sourced, Trait


class Race(Sourced):
    def __init__(self, name, size, speed, traits, **kwargs):
        """
        :type name: str
        :type size: str
        :type speed: str
        :type traits: list[gamedata.shared.Trait]
        """
        super().__init__('race', False, **kwargs)
        self.name = name
        self.size = size
        self.speed = speed
        self.traits = traits

    @classmethod
    def from_data(cls, d):
        return cls(d['name'], d['size'], d['speed'],
                   [Trait.from_dict(t) for t in d['traits']],
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
