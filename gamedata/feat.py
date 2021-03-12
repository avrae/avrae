from .shared import Sourced


class Feat(Sourced):
    entity_type = 'feat'
    type_id = 1088085227

    def __init__(self, name, desc, prerequisite=None, ability=None, **kwargs):
        """
        :type name: str
        :type desc: str
        :type prerequisite: str or None
        :type ability: list[str]
        """
        if ability is None:
            ability = []

        super().__init__(False, **kwargs)
        self.name = name
        self.desc = desc
        self.prerequisite = prerequisite
        self.ability = ability

    @classmethod
    def from_data(cls, d):
        return cls(d['name'], d['description'],
                   d.get('prerequisite'), d.get('ability'),
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])


class FeatOption(Sourced):
    entity_type = 'feat-option'
    type_id = 400581042

    def __init__(self, name, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name

    @classmethod
    def from_feat(cls, feat: Feat, option_id: int, **kwargs):
        # noinspection PyProtectedMember
        return cls(
            feat.name, entity_id=option_id,
            page=feat.page, source=feat.source, is_free=feat.is_free,
            url=feat._url, entitlement_entity_id=feat.entitlement_entity_id,
            entitlement_entity_type=feat.entitlement_entity_type, parent=feat,
            **kwargs
        )
