from .shared import Sourced, SourcedTrait, Trait


class Class(Sourced):
    def __init__(self, name, hit_points, proficiencies, equipment, table, levels, subclasses, optional_features,
                 **kwargs):
        """
        :type name: str
        :type hit_points: str
        :type proficiencies: str
        :type equipment: str
        :type table: ClassTable
        :type levels: list[list[Trait]]
        :type subclasses: list[Subclass]
        :type optional_features: list[SourcedTrait]
        """
        super().__init__('class', False, **kwargs)
        self.name = name
        self.hit_points = hit_points
        self.proficiencies = proficiencies
        self.equipment = equipment
        self.table = table
        self.levels = levels
        self.subclasses = subclasses
        self.optional_features = optional_features

    @classmethod
    def from_data(cls, d):
        levels = [[Trait.from_dict(cf) for cf in lvl] for lvl in d['levels']]
        subclasses = [Subclass.from_data(s) for s in d['subclasses']]
        optional_features = [SourcedTrait.from_trait_and_sourced_dicts(ocf, d, 'class-feature')
                             for ocf in d['optional_features']]
        return cls(
            d['name'], d['hit_points'], d['proficiencies'], d['equipment'],
            ClassTable.from_data(d['table']), levels, subclasses, optional_features,
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree']
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
    def __init__(self, name, levels, optional_features, **kwargs):
        """
        :type name: str
        :type levels: list[list[Trait]]
        :type optional_features: list[SourcedTrait]
        """
        super().__init__('class', False, **kwargs)
        self.name = name
        self.levels = levels
        self.optional_features = optional_features

    @classmethod
    def from_data(cls, d):
        levels = [[Trait.from_dict(cf) for cf in lvl] for lvl in d['levels']]
        optional_features = [SourcedTrait.from_trait_and_sourced_dicts(ocf, d, 'class-feature')
                             for ocf in d['optional_features']]
        return cls(
            d['name'], levels, optional_features,
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree']
        )
