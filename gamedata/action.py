from utils.enums import ActivationType
from .mixins import AutomatibleMixin


class Action(AutomatibleMixin):
    def __init__(
        self,
        name,
        uid,
        id,
        type_id,
        activation_type,
        source_feature_id,
        source_feature_type_id,
        list_display_override=None,
        **kwargs,
    ):
        """
        :type name: str
        :type uid: str
        :type id: int
        :type type_id: int
        :type source_feature_id: int
        :type source_feature_type_id: int
        :type activation_type: ActivationType
        :type list_display_override: str or None
        """
        super().__init__(**kwargs)
        self.name = name
        self.uid = uid
        self.id = id
        self.type_id = type_id
        self.activation_type = activation_type
        self.source_feature_id = source_feature_id
        self.source_feature_type_id = source_feature_type_id
        self.list_display_override = list_display_override

    @classmethod
    def from_data(cls, d):
        return cls(
            name=d["name"],
            uid=d["uid"],
            id=d["id"],
            type_id=d["type_id"],
            activation_type=ActivationType(d["activation_type"]),
            source_feature_id=d["source_feature_id"],
            source_feature_type_id=d["source_feature_type_id"],
            list_display_override=d.get("list_display_override"),
        ).initialize_automation(d)

    @property
    def grantor(self):
        """
        Returns the entity directly granting this action.
        Usually this is a LimitedUse but can be the same as the source_feature.
        """
        from . import compendium

        return compendium.lookup_entity(self.type_id, self.id)

    @property
    def source_feature(self):
        """
        Returns the root feature granting this action. Usually this is a class/race/feat feature.

        :rtype: gamedata.shared.Sourced
        """
        from . import compendium

        return compendium.lookup_entity(
            self.source_feature_type_id, self.source_feature_id
        )

    def __repr__(self):
        return (
            f"<Action name={self.name!r} uid={self.uid!r} id={self.id!r} type_id={self.type_id!r} "
            f"activation_type={self.activation_type!r} automation={self.automation!r}>"
        )
