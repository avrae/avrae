from utils.enums import ActivationType
from .mixins import AutomatibleMixin


class Action(AutomatibleMixin):
    def __init__(self, name, uid, id, type_id, activation_type, list_display_override=None, **kwargs):
        """
        :type name: str
        :type uid: str
        :type id: int
        :type type_id: int
        :type activation_type: ActivationType
        :type list_display_override: str or None
        """
        super().__init__(**kwargs)
        self.name = name
        self.uid = uid
        self.id = id
        self.type_id = type_id
        self.activation_type = activation_type
        self.list_display_override = list_display_override

    @classmethod
    def from_data(cls, d):
        return cls(
            name=d['name'], uid=d['uid'], id=d['id'], type_id=d['type_id'],
            activation_type=ActivationType(d['activation_type']), list_display_override=d.get('list_display_override')
        ).initialize_automation(d)

    def __repr__(self):
        return f"<Action name={self.name!r} uid={self.uid!r} id={self.id!r} type_id={self.type_id!r} " \
               f"activation_type={self.activation_type!r} automation={self.automation!r}>"
