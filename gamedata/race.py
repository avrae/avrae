from .shared import LimitedUse, Sourced


class Race(Sourced):
    entity_type = 'race'
    type_id = 1743923279

    def __init__(self, name, size, speed, traits, **kwargs):
        """
        :type name: str
        :type size: str
        :type speed: str
        :type traits: list[RaceFeature]
        """
        super().__init__(False, **kwargs)
        self.name = name
        self.size = size
        self.speed = speed
        self.traits = traits

    @classmethod
    def from_data(cls, d):
        inst = cls(d['name'], d['size'], d['speed'], traits=[],
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
        inst.traits = [RaceFeature.from_data(t, inst) for t in d['traits']]
        return inst


class SubRace(Race):
    entity_type = 'subrace'
    type_id = 1228963568


class RaceFeature(Sourced):
    entity_type = 'race-feature'
    type_id = 1960452172

    def __init__(self, name, text, options, limited_use, inherited=False, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name
        self.text = text
        self.options = options
        self.limited_use = limited_use
        self.inherited = inherited

    @classmethod
    def from_data(cls, d, source_race, **kwargs):
        inst = cls(
            d['name'], d['text'], options=[], limited_use=[], inherited=d.get('inherited', False),
            entity_id=d['id'], page=d['page'],
            source=d.get('source', source_race.source), is_free=d.get('isFree', source_race.is_free),
            url=d.get('url', source_race.raw_url),
            entitlement_entity_id=d.get('entitlementEntityId', source_race.entity_id),
            entitlement_entity_type=d.get('entitlementEntityType', source_race.entity_type),
            **kwargs
        )
        inst.options = [RaceFeatureOption.from_race_feature(o, inst) for o in d['options']]
        if 'grantedLimitedUse' in d:
            inst.limited_use = [LimitedUse.from_dict(lu, inst) for lu in d['grantedLimitedUse']]
        return inst


class RaceFeatureOption(Sourced):
    entity_type = 'race-feature-option'
    type_id = 306912077

    def __init__(self, name, limited_use, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name
        self.limited_use = limited_use

    @classmethod
    def from_race_feature(cls, d, race_feature: RaceFeature, **kwargs):
        inst = cls(
            f"{race_feature.name} ({d['name']})", [],
            entity_id=d['id'],
            page=race_feature.page, source=race_feature.source, is_free=race_feature.is_free,
            url=race_feature.raw_url, entitlement_entity_id=race_feature.entitlement_entity_id,
            entitlement_entity_type=race_feature.entitlement_entity_type, parent=race_feature,
            **kwargs
        )
        if 'grantedLimitedUse' in d:
            inst.limited_use = [LimitedUse.from_dict(lu, inst) for lu in d['grantedLimitedUse']]
        return inst
