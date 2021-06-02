from . import Effect
from ..results import TextResult


class Text(Effect):
    def __init__(self, text: str, **kwargs):
        super(Text, self).__init__("text", **kwargs)
        self.text = text
        self.added = False

    def to_dict(self):
        out = super(Text, self).to_dict()
        out.update({"text": self.text})
        return out

    def run(self, autoctx):
        super(Text, self).run(autoctx)
        hide = autoctx.args.last('h', type_=bool)

        if self.text:
            text = autoctx.parse_annostr(self.text)
            if len(text) > 1020:
                text = f"{text[:1020]}..."
            if not hide:
                autoctx.effect_queue(text)
            else:
                autoctx.add_pm(str(autoctx.ctx.author.id), text)

            return TextResult(text=text)

    def build_str(self, caster, evaluator):
        super(Text, self).build_str(caster, evaluator)
        return ""
