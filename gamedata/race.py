from .shared import Sourced


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

    def __init__(self, name, text, option_ids, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name
        self.text = text
        self.option_ids = option_ids

    @classmethod
    def from_data(cls, d, source_race, **kwargs):
        # noinspection PyProtectedMember
        return cls(
            d['name'], d['text'], d['option_ids'],
            entity_id=d['id'], page=d['page'],
            source=d.get('source', source_race.source), is_free=d.get('isFree', source_race.is_free),
            url=d.get('url', source_race._url),
            entitlement_entity_id=d.get('entitlementEntityId', source_race.entity_id),
            entitlement_entity_type=d.get('entitlementEntityType', source_race.entity_type),
            parent=source_race,
            **kwargs
        )


class RaceFeatureOption(Sourced):
    entity_type = 'race-feature-option'
    type_id = 306912077

    def __init__(self, name, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name

    @classmethod
    def from_race_feature(cls, race_feature: RaceFeature, option_id: int, **kwargs):
        # noinspection PyProtectedMember
        return cls(
            race_feature.name, entity_id=option_id,
            page=race_feature.page, source=race_feature.source, is_free=race_feature.is_free,
            url=race_feature._url, entitlement_entity_id=race_feature.entitlement_entity_id,
            entitlement_entity_type=race_feature.entitlement_entity_type, parent=race_feature,
            **kwargs
        )
