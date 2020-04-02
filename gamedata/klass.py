from .shared import Sourced, Trait


class Class(Sourced):
    def __init__(self, name, hit_die, saves, proficiencies, equipment, table, levels, subclasses, **kwargs):
        """
        :type name: str
        :type hit_die: str
        :type saves: list[str]
        :type proficiencies: ClassProficiencies
        :type equipment: str
        :type table: ClassTable
        :type levels: list[list[Trait]]
        :type subclasses: list[Subclass]
        """
        super().__init__('class', False, **kwargs)
        self.name = name
        self.hit_die = hit_die
        self.saves = saves
        self.proficiencies = proficiencies
        self.equipment = equipment
        self.table = table
        self.levels = levels
        self.subclasses = subclasses

    @classmethod
    def from_data(cls, d):
        levels = [[Trait.from_dict(cf) for cf in lvl] for lvl in d['levels']]
        subclasses = [Subclass.from_data(s) for s in d['subclasses']]
        return cls(
            d['name'], d['hit_die'], d['saves'], ClassProficiencies.from_data(d['proficiencies']), d['equipment'],
            ClassTable.from_data(d['table']), levels, subclasses,
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree']
        )


class ClassProficiencies:
    def __init__(self, armor, weapons, tools, skills, num_skills):
        """
        :type armor: list[str]
        :type weapons: list[str]
        :type tools: list[str]
        :type skills: list[str]
        :type num_skills: int
        """
        self.armor = armor
        self.weapons = weapons
        self.tools = tools
        self.skills = skills
        self.num_skills = num_skills

    @classmethod
    def from_data(cls, d):
        return cls(
            d['armor'], d['weapons'], d['tools'], d['skills'], d['num_skills']
        )


class ClassTable:
    def __init__(self, headers, levels):
        """
        :type headers: list[str]
        :type levels: list[list[str]]
        """
        if not len(levels) == 20:
            raise ValueError("Class Table must have 20 levels")
        if not all(len(lvl) == len(headers) for lvl in levels):
            raise ValueError("Number of entries in each level must equal header size")

        self.headers = headers
        self.levels = levels

    @classmethod
    def from_data(cls, d):
        return cls(
            d['headers'], d['levels']
        )


class Subclass(Sourced):
    def __init__(self, name, levels, **kwargs):
        """
        :type name: str
        :type levels: list[list[Trait]]
        """
        super().__init__('subclass', False, **kwargs)
        self.name = name
        self.levels = levels

    @classmethod
    def from_data(cls, d):
        levels = [[Trait.from_dict(cf) for cf in lvl] for lvl in d['levels']]
        return cls(
            d['name'], levels,
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree']
        )
