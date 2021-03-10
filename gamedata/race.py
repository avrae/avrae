from .shared import Sourced


class Race(Sourced):
    def __init__(self, name, size, speed, traits, is_subrace, **kwargs):
        """
        :type name: str
        :type size: str
        :type speed: str
        :type traits: list[RaceFeature]
        """
        entity_type = 'race' if not is_subrace else 'subrace'
        super().__init__(entity_type, False, **kwargs)
        self.name = name
        self.size = size
        self.speed = speed
        self.traits = traits
        self.is_subrace = is_subrace

    @classmethod
    def from_data(cls, d, is_subrace=False):
        inst = cls(d['name'], d['size'], d['speed'], traits=[], is_subrace=is_subrace,
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
        inst.traits = [RaceFeature.from_data(t, inst) for t in d['traits']]
        return inst


class RaceFeature(Sourced):
    def __init__(self, name, text, option_ids, is_subrace_feature=False, **kwargs):
        entity_type = 'race-feature' if not is_subrace_feature else 'subrace-feature'
        super().__init__(entity_type, homebrew=False, **kwargs)
        self.name = name
        self.text = text
        self.option_ids = option_ids

    @classmethod
    def from_data(cls, d, source_race, **kwargs):
        # noinspection PyProtectedMember
        return cls(
            d['name'], d['text'], d['option_ids'],
            is_subrace_feature=source_race.is_subrace and not d.get('inherited'),
            entity_id=d['id'], page=d['page'],
            source=d.get('source', source_race.source), is_free=d.get('isFree', source_race.is_free),
            url=d.get('url', source_race._url),
            entitlement_entity_id=d.get('entitlementEntityId', source_race.entity_id),
            entitlement_entity_type=d.get('entitlementEntityType', 'race' if not source_race.is_subrace else 'subrace'),
            **kwargs
        )
