# ==== useful constants ====
RESIST_TYPES = ('resist', 'immune', 'vuln', 'neutral')
DAMAGE_TYPES = ('acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning', 'necrotic', 'piercing', 'poison',
                'psychic', 'radiant', 'slashing', 'thunder')

STAT_NAMES = ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')

STAT_ABBREVIATIONS = ('str', 'dex', 'con', 'int', 'wis', 'cha')

STAT_ABBR_MAP = {'str': 'Strength', 'dex': 'Dexterity', 'con': 'Constitution',
                 'int': 'Intelligence', 'wis': 'Wisdom', 'cha': 'Charisma'}

SKILL_NAMES = ('acrobatics', 'animalHandling', 'arcana', 'athletics', 'deception', 'history', 'initiative', 'insight',
               'intimidation', 'investigation', 'medicine', 'nature', 'perception', 'performance', 'persuasion',
               'religion', 'sleightOfHand', 'stealth', 'survival', 'strength', 'dexterity', 'constitution',
               'intelligence', 'wisdom', 'charisma')

SAVE_NAMES = ('strengthSave', 'dexteritySave', 'constitutionSave', 'intelligenceSave', 'wisdomSave', 'charismaSave')

SKILL_MAP = {'acrobatics': 'dexterity', 'animalHandling': 'wisdom', 'arcana': 'intelligence', 'athletics': 'strength',
             'deception': 'charisma', 'history': 'intelligence', 'initiative': 'dexterity', 'insight': 'wisdom',
             'intimidation': 'charisma', 'investigation': 'intelligence', 'medicine': 'wisdom',
             'nature': 'intelligence', 'perception': 'wisdom', 'performance': 'charisma',
             'persuasion': 'charisma', 'religion': 'intelligence', 'sleightOfHand': 'dexterity', 'stealth': 'dexterity',
             'survival': 'wisdom', 'strengthSave': 'strength', 'dexteritySave': 'dexterity',
             'constitutionSave': 'constitution', 'intelligenceSave': 'intelligence', 'wisdomSave': 'wisdom',
             'charismaSave': 'charisma',
             'strength': 'strength', 'dexterity': 'dexterity', 'constitution': 'constitution',
             'intelligence': 'intelligence', 'wisdom': 'wisdom', 'charisma': 'charisma'}

# ---- emojis, icons, other discord things ----
DDB_LOGO_EMOJI = '<:beyond:783780183559372890>'
DDB_LOGO_ICON = 'https://cdn.discordapp.com/emojis/783780183559372890.png?v=1'
