import logging

from utils.functions import get_positivity

log = logging.getLogger(__name__)


class CSetting:  # character settings
    def __init__(self, setting_key, type_, description=None, default=None, min_=None, max_=None,
                 display_func=None):
        self.character = None
        self.ctx = None
        if type_ not in ("hex", "number", "boolean"):
            raise ValueError("Setting type must be hex, number, or boolean")
        if description is None:
            description = setting_key
        if display_func is None:
            display_func = lambda val: val
        self.setting_key = setting_key
        self.type = type_
        self.description = description
        self.default = default
        self.min = min_
        self.max = max_
        self.display_func = display_func

    def run(self, ctx, char, arg):
        self.character = char
        self.ctx = ctx
        if arg is None:
            return self.info()
        elif arg in ('reset', self.default):
            return self.reset()
        else:
            return self.set(arg)

    def info(self):
        old_val = self.character.get_setting(self.setting_key)
        if old_val is not None:
            return f'\u2139 Your character\'s current {self.description} is {self.display_func(old_val)}. ' \
                f'Use "{self.ctx.prefix}csettings {self.setting_key} reset" to reset it to {self.default}.'
        return f'\u2139 Your character\'s current {self.description} is {self.default}.'

    def reset(self):
        self.character.delete_setting(self.setting_key)
        return f"\u2705 {self.description.capitalize()} reset to {self.default}."

    def set(self, new_value):
        if self.type == 'hex':
            try:
                val = int(new_value, base=16)
            except (ValueError, TypeError):
                return f'\u274c Invalid {self.description}. ' \
                    f'Use "{self.ctx.prefix}csettings {self.setting_key} reset" to reset it to {self.default}.'
            if not self.min <= val <= self.max:
                return f'\u274c Invalid {self.description}.\n'
        elif self.type == 'number':
            try:
                val = int(new_value)
            except (ValueError, TypeError):
                return f'\u274c Invalid {self.description}. ' \
                    f'Use "{self.ctx.prefix}csettings {self.setting_key} reset" to reset it to {self.default}.'
            if self.max is not None and self.min is not None and not self.min <= val <= self.max:
                return f'\u274c {self.description.capitalize()} must be between {self.min} and {self.max}.'
            elif val == self.default:
                return self.reset()
        elif self.type == 'boolean':
            try:
                val = get_positivity(new_value)
            except AttributeError:
                return f'\u274c Invalid {self.description}.' \
                    f'Use "{self.ctx.prefix}csettings {self.setting_key} false" to reset it.'
        else:
            log.warning(f"No setting type for {self.type} found")
            return
        self.character.set_setting(self.setting_key, val)
        return f"\u2705 {self.description.capitalize()} set to {self.display_func(val)}.\n"
