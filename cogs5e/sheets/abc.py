class SheetLoaderABC:
    def __init__(self, url):
        self.url = url
        self.character_data = None

    async def load_character(self, owner_id: str, args):
        raise NotImplemented

# gsheet
# v3: added stat cvars
# v4: consumables
# v5: spellbook
# v6: v2.0 support (level vars, resistances, extra spells/attacks)
# v7: race/background (experimental)
# v8: skill/save effects
# v15: version fix

# dicecloud
# v6: added stat cvars
# v7: added check effects (adv/dis)
# v8: consumables
# v9: spellbook
# v10: live tracking
# v11: save effects (adv/dis)
# v12: add cached dicecloud spell list id
# v13: added nonstrict spells
# v14: added race, background (for experimental purposes only)
# v15: migrated to new sheet system

# beyond
# v1: initial implementation
# v2: added race/background for research purposes
# v15: standardize sheet import versions

# all
# v16: explicit spellcasting mod import
# v17: refactor to use StatBlock, AttackList
SHEET_VERSION = 17
