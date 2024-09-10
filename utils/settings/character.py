import logging
from typing import Optional

from pydantic import ValidationError, conint
from pydantic.color import Color

from utils.functions import get_positivity
from . import SettingsBaseModel
from utils.enums import CoinsAutoConvert

log = logging.getLogger(__name__)


class CharacterSettings(SettingsBaseModel):
    # cosmetic
    color: Optional[conint(ge=0, le=0xFFFFFF)] = None
    embed_image: bool = True
    compact_coins: bool = False

    # gameplay
    crit_on: conint(ge=1, le=20) = 20
    extra_crit_dice: int = 0
    ignore_crit: bool = False
    reroll: Optional[conint(ge=1, le=20)] = None
    talent: bool = False
    srslots: bool = False
    autoconvert_coins: CoinsAutoConvert = CoinsAutoConvert.ASK
    version: str = "2024"  # Versions: 2024(Free Rules/PHB 2024) or 2014(BR/PHB 2014)

    # character sync
    sync_outbound: bool = True  # avrae to upstream
    sync_inbound: bool = True  # upstream to avrae

    @classmethod
    def from_old_csettings(cls, d):
        """Returns a new CharacterSettings instance with all default options, updated by legacy csettings options."""
        # for each key, get it from old or fall back to class default
        old_settings = d.get("options", {})
        return cls(
            color=old_settings.get("color", None),
            embed_image=old_settings.get("embedimage") or True,
            crit_on=old_settings.get("criton") or 20,
            extra_crit_dice=old_settings.get("critdice") or 0,
            ignore_crit=old_settings.get("ignorecrit") or False,
            reroll=old_settings.get("reroll", None),
            talent=old_settings.get("talent") or False,
            srslots=old_settings.get("srslots") or False,
        )

    async def commit(self, mdb, character):
        """Commits the settings to the database for a given character."""
        await mdb.characters.update_one(
            {"owner": character.owner, "upstream": character.upstream},
            {
                "$set": {"options_v2": self.dict()},
                "$unset": {"options": True},  # delete any old options - they should have been converted by now
            },
        )


# ==== legacy csettings ====
# this code lives here to keep the legacy CLI interface working, because I'm not rewriting that
class CSetting:  # character settings
    def __init__(self, setting_key, type_, description=None, default=None, display_func=None):
        self.character = None
        self.ctx = None
        if type_ not in ("color", "number", "boolean"):
            raise ValueError("Setting type must be color, number, or boolean")
        if description is None:
            description = setting_key
        if display_func is None:
            display_func = lambda val: val
        self.setting_key = setting_key
        self.type = type_
        self.description = description
        self.default = default
        self.display_func = display_func

    def run(self, ctx, char, arg):
        self.character = char
        self.ctx = ctx
        if arg is None:
            return self.info()
        elif arg in ("reset", self.default):
            return self.reset()
        else:
            return self.set(arg)

    def info(self):
        old_val = getattr(self.character.options, self.setting_key)
        if old_val is not None:
            return (
                f"\u2139 Your character's current {self.description} is {self.display_func(old_val)}. "
                f'Use "{self.ctx.prefix}csettings {self.setting_key} reset" to reset it to {self.default}.'
            )
        return f"\u2139 Your character's current {self.description} is {self.default}."

    def reset(self):
        setattr(self.character.options, self.setting_key, CharacterSettings.__fields__[self.setting_key].default)
        return f"\u2705 {self.description.capitalize()} reset to {self.default}."

    def set(self, new_value):
        if self.type == "color":
            try:
                color_val = Color(new_value)
                r, g, b = color_val.as_rgb_tuple(alpha=False)
                val = (r << 16) + (g << 8) + b
            except (ValueError, TypeError):
                return (
                    f"\u274c Invalid {self.description}. "
                    f"Use `{self.ctx.prefix}csettings {self.setting_key} reset` to reset it to {self.default}."
                )
        elif self.type == "number":
            try:
                val = int(new_value)
            except (ValueError, TypeError):
                return (
                    f"\u274c Invalid {self.description}. "
                    f"Use `{self.ctx.prefix}csettings {self.setting_key} reset` to reset it to {self.default}."
                )
        elif self.type == "boolean":
            try:
                val = get_positivity(new_value)
            except AttributeError:
                return (
                    f"\u274c Invalid {self.description}."
                    f"Use `{self.ctx.prefix}csettings {self.setting_key} false` to reset it."
                )
        else:
            log.warning(f"No setting type for {self.type} found")
            return
        try:
            setattr(self.character.options, self.setting_key, val)
        except ValidationError as e:
            return (
                f"\u274c Invalid {self.description}: {e!s}.\n"
                f"Use `{self.ctx.prefix}csettings {self.setting_key} reset` to reset it to {self.default}."
            )
        return f"\u2705 {self.description.capitalize()} set to {self.display_func(val)}.\n"


CHARACTER_SETTINGS = {
    "color": CSetting("color", "color", default="random", display_func=lambda val: f"#{val:06X}"),
    "criton": CSetting("crit_on", "number", description="crit range", default=20, display_func=lambda val: f"{val}-20"),
    "reroll": CSetting("reroll", "number"),
    "srslots": CSetting(
        "srslots",
        "boolean",
        description="short rest slots",
        default="disabled",
        display_func=lambda val: "enabled" if val else "disabled",
    ),
    "embedimage": CSetting(
        "embed_image",
        "boolean",
        description="embed image",
        default="disabled",
        display_func=lambda val: "enabled" if val else "disabled",
    ),
    "critdice": CSetting("extra_crit_dice", "number", description="extra crit dice", default=0),
    "talent": CSetting(
        "talent",
        "boolean",
        description="reliable talent",
        default="disabled",
        display_func=lambda val: "enabled" if val else "disabled",
    ),
    "ignorecrit": CSetting(
        "ignore_crit",
        "boolean",
        description="ignore crits",
        default="disabled",
        display_func=lambda val: "enabled" if val else "disabled",
    ),
    "compactcoins": CSetting(
        "compact_coins",
        "boolean",
        description="compact coin display",
        default="disabled",
        display_func=lambda val: "enabled" if val else "disabled",
    ),
    "autoconvertcoins": CSetting(
        "autoconvert_coins",
        "number",
        description=(
            f"auto convert coins mode, {CoinsAutoConvert.ASK.value} for ask everytime, "
            f"{CoinsAutoConvert.ALWAYS.value} for always convert, "
            f"{CoinsAutoConvert.NEVER.value} for never convert"
        ),
        default="ask everytime",
        display_func=lambda val: "ask everytime" if val == 0 else "always convert" if val == 1 else "never convert",
    ),
    "version": CSetting(
        "version",
        "number",
        description="version of the ruleset to use",
        default="2024",
        display_func=lambda val: "2024" if val == 2024 else "2014",
    ),
}
