class Spell:
    def __init__(self, name: str, level: int, school: str, casttime: str, range_: str, components: str, duration: str,
                 description: str, classes: list = None, subclasses: list = None, ritual: bool = False,
                 higherlevels: str = None, source: str = "homebrew", page: int = None, concentration: bool = False,
                 automation: list = None):
        if classes is None:
            classes = []
        if subclasses is None:
            subclasses = []
        self.name = name
        self.level = level
        self.school = school
        self.classes = classes
        self.subclasses = subclasses
        self.time = casttime
        self.range = range_
        self.components = components
        self.duration = duration
        self.ritual = ritual
        self.description = description
        self.higherlevels = higherlevels
        self.source = source
        self.page = page
        self.concentration = concentration
        self.automation = automation
