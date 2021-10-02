from .mixins import DescribableMixin, LimitedUseGrantorMixin
from .shared import Sourced


class Class(Sourced):
    entity_type = 'class'
    type_id = 789467139

    def __init__(self, name, hit_points, proficiencies, equipment, table, levels, subclasses, subclass_title,
                 subclass_feature_levels, optional_features,
                 **kwargs):
        """
        :type name: str
        :type hit_points: str
        :type proficiencies: str
        :type equipment: str
        :type table: ClassTable
        :type levels: list[list[ClassFeature]]
        :type subclasses: list[Subclass]
        :type subclass_title: str
        :type subclass_feature_levels: list[int]
        :type optional_features: list[ClassFeature]
        """
        super().__init__(False, **kwargs)
        self.name = name
        self.hit_points = hit_points
        self.proficiencies = proficiencies
        self.equipment = equipment
        self.table = table
        self.levels = levels
        self.subclasses = subclasses
        self.subclass_title = subclass_title
        self.subclass_feature_levels = subclass_feature_levels
        self.optional_features = optional_features

    @classmethod
    def from_data(cls, d):
        levels = [[] for _ in d['levels']]
        inst = cls(
            d['name'], d['hit_points'], d['proficiencies'], d['equipment'],
            ClassTable.from_data(d['table']), levels, subclasses=[], subclass_title=d['subclass_title'],
            subclass_feature_levels=d['subclass_feature_levels'], optional_features=[],
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree']
        )
        inst.subclasses = [Subclass.from_data(s, inst) for s in d['subclasses']]
        inst.levels = [[ClassFeature.from_data(cf, inst) for cf in lvl] for lvl in d['levels']]
        inst.optional_features = [ClassFeature.from_data(ocf, inst) for ocf in d['optional_features']]
        return inst


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
    entity_type = 'class'
    type_id = 789467139

    def __init__(self, name, levels, optional_features, parent=None, **kwargs):
        """
        :type name: str
        :type levels: list[list[ClassFeature]]
        :type optional_features: list[ClassFeature]
        :type parent: Class
        """
        super().__init__(False, **kwargs)
        self.name = name
        self.levels = levels
        self.optional_features = optional_features
        self.parent = parent

    @classmethod
    def from_data(cls, d, parent_class):
        levels = [[] for _ in d['levels']]
        inst = cls(
            d['name'], levels, [],
            source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'],
            parent=parent_class
        )
        inst.levels = [[ClassFeature.from_data(cf, source_class=inst) for cf in lvl] for lvl in d['levels']]
        inst.optional_features = [ClassFeature.from_data(ocf, source_class=inst) for ocf in d['optional_features']]
        return inst


class ClassFeature(LimitedUseGrantorMixin, DescribableMixin, Sourced):
    entity_type = 'class-feature'
    type_id = 12168134

    def __init__(self, name, text, options, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name
        self.text = text
        self.options = options

    @classmethod
    def from_data(cls, d, source_class, **kwargs):
        # priority: data, kwarg, source class
        entitlement_entity_id = d.get(
            'entitlementEntityId',
            kwargs.pop('entitlement_entity_id', source_class.entity_id)
        )
        entitlement_entity_type = d.get(
            'entitlementEntityType',
            kwargs.pop('entitlement_entity_type', 'class')
        )

        inst = cls(
            d['name'], d['text'], [],
            entity_id=d['id'], page=d['page'],
            source=d.get('source', source_class.source), is_free=d.get('isFree', source_class.is_free),
            url=d.get('url', source_class.raw_url),
            entitlement_entity_id=entitlement_entity_id,
            entitlement_entity_type=entitlement_entity_type,
            **kwargs
        )
        if 'options' in d:
            inst.options = [ClassFeatureOption.from_data(o, source_class, inst) for o in d['options']]
        inst.initialize_limited_use(d)
        return inst

    @property
    def description(self):
        return self.text


class ClassFeatureOption(ClassFeature):
    entity_type = 'class-feature-option'
    type_id = 258900837

    @classmethod
    def from_data(cls, d, source_class, class_feature=None, **kwargs):
        return super().from_data(
            d, source_class,
            parent=class_feature,
            entitlement_entity_id=d.get('entitlementEntityId', class_feature.entitlement_entity_id),
            entitlement_entity_type=d.get('entitlementEntityType', class_feature.entitlement_entity_type),
            **kwargs
        )
