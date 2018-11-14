class Background:
    def __init__(self, name, traits, proficiencies, source, page, srd):
        self.name = name
        self.traits = traits
        self.proficiencies = proficiencies
        self.source = source
        self.page = page
        self.srd = srd

    @classmethod
    def from_data(cls, raw):
        return cls(**raw)
