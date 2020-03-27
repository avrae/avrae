from .sourcing import Sourced


class Background(Sourced):
    def __init__(self, entity_id, name, traits, proficiencies, source, page):
        super().__init__('background', False, source, page=page, entity_id=entity_id)
        self.name = name
        self.traits = traits
        self.proficiencies = proficiencies

    @classmethod
    def from_data(cls, raw):
        return cls(**raw)
