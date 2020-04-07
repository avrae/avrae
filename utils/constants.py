# ==== useful constants ====
RESIST_TYPES = ('resist', 'immune', 'vuln', 'neutral')
DAMAGE_TYPES = ('acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning', 'necrotic', 'piercing', 'poison',
                'psychic', 'radiant', 'slashing', 'thunder')

STAT_NAMES = ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')

STAT_ABBREVIATIONS = ('str', 'dex', 'con', 'int', 'wis', 'cha')

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

SOURCE_MAP = {
    # sourcebooks
    'BR': 'Basic Rules', 'PHB': "Player's Handbook", 'DMG': "Dungeon Master's Guide", 'MM': "Monster Manual",
    'SCAG': "Sword Coast Adventurer's Guide", 'VGtM': "Volo's Guide to Monsters",
    'XGtE': "Xanathar's Guide to Everything", 'TTP': "The Tortle Package", 'MToF': "Mordenkainen's Tome of Foes",
    'WGtE': "Wayfarer's Guide to Ebberon", 'GGtR': "Guildmasters' Guide to Ravnica", 'AI': "Acquisitions Incorporated",
    'ERftLW': "Ebberon: Rising from the Last War", 'SAC': "Sage Advice Compendium",
    'MFFv1': "Mordenkainen's Fiendish Folio Volume 1", 'EGtW': "Explorer's Guide to Wildemount",
    # adventures
    'CoS': "Curse of Strahd", 'HotDQ': "Hoard of the Dragon Queen", 'LMoP': "Lost Mine of Phandelver",
    'OotA': "Out of the Abyss", 'PotA': "Princes of the Apocalypse", 'RoT': "Rise of Tiamat",
    'SKT': "Storm King's Thunder", 'TftYP': "Tales from the Yawning Portal", 'ToA': "Tomb of Annihilation",
    'R': "Rrakkma", 'WDH': "Waterdeep Dragon Heist", 'WDotMM': "Waterdeep Dungeon of the Mad Mage",
    'LLoK': "Lost Laboratory of Kwalish", 'DoIP': "Dragon of Icespire Peak", 'GoS': "Ghosts of Saltmarsh",
    'HftT': "Hunt for the Thessalhydra", 'BGDiA': "Baldur's Gate: Descent into Avernus", 'SLW': "Storm Lord's Wrath",
    'SDW': "Sleeping Dragon's Wake", 'DC': "Divine Contention", 'DDvRaM': "Dungeons & Dragons vs. Rick and Morty",
    'LR': "Locathah Rising", 'IMR': "Infernal Machine Rebuild", 'FS': "Frozen Sick",
    # other
    'CR': "Critical Role", 'UA': "Unearthed Arcana", 'EE': "Elemental Evil", 'CoSCO': "Curse of Strahd"
}
