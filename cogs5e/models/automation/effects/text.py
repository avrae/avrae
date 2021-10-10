import gamedata
import gamedata.lookuputils
from cogs5e.models.errors import RequiresLicense
from . import Effect
from ..errors import AutomationException
from ..results import TextResult


class Text(Effect):
    def __init__(self, text, **kwargs):
        """
        :type text: str or EntityReference
        """
        super().__init__("text", **kwargs)
        self.text = text

    @classmethod
    def from_data(cls, data):
        data['text'] = deserialize_text_target(data['text'])
        return super().from_data(data)

    def to_dict(self):
        out = super().to_dict()
        text = self.text if isinstance(self.text, str) else self.text.to_dict()
        out.update({"text": text})
        return out

    async def preflight(self, autoctx):
        """Checks that the user has entitlement access to the referenced entity, if applicable."""
        await super().preflight(autoctx)
        if not isinstance(self.text, EntityReference):
            return
        entity = self.text.entity
        if entity is None:
            return
        type_e10s = await autoctx.ctx.bot.ddb.get_accessible_entities(
            ctx=autoctx.ctx, user_id=autoctx.ctx.author.id, entity_type=entity.entitlement_entity_type
        )
        if not gamedata.lookuputils.can_access(entity, type_e10s):
            raise RequiresLicense(entity, type_e10s is not None)

    def run(self, autoctx):
        super().run(autoctx)
        hide = autoctx.args.last('h', type_=bool)
        text = ''

        if isinstance(self.text, EntityReference):
            entity = self.text.entity
            if entity is None:
                text = "**Error**: Invalid entity specified in text."
            elif not isinstance(entity, gamedata.mixins.DescribableMixin):
                text = f"**Error**: The supplied {entity.entity_type} does not have a description."
            else:
                text = entity.description
        elif self.text:
            text = autoctx.parse_annostr(self.text)

        if len(text) > 1020:
            text = f"{text[:1020]}..."

        if not hide:
            autoctx.effect_queue(text)
        else:
            autoctx.add_pm(str(autoctx.ctx.author.id), text)

        return TextResult(text=text)

    def build_str(self, caster, evaluator):
        super().build_str(caster, evaluator)
        return ""


# ===== helpers =====
class EntityReference:
    def __init__(self, id: int, type_id: int, **kwargs):
        super().__init__(**kwargs)
        self.id = id
        self.type_id = type_id

    @property
    def entity(self):
        return gamedata.compendium.lookup_entity(self.type_id, self.id)

    @classmethod
    def from_data(cls, data):
        return cls(id=data['id'], type_id=data['typeId'])

    def to_dict(self):
        return {'id': self.id, 'typeId': self.type_id}

    def __repr__(self):
        return f"<EntityReference id={self.id!r} type_id={self.type_id!r} entity={self.entity!r}>"


def deserialize_text_target(target):
    """
    :rtype: str or EntityReference
    """
    if isinstance(target, str):
        return target
    elif 'id' in target:
        return EntityReference.from_data(target)
    raise ValueError(f"Unknown text target: {target!r}")
