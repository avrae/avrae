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
    'BR': 'Basic Rules', 'PHB': "Player's Handbook", 'DMG': "Dungeon Master's Guide",
    'EE': "Elemental Evil Player's Companion", 'MM': 'Monster Manual', 'CoS': 'Curse of Strahd',
    'HotDQ': 'Hoard of the Dragon Queen', 'LMoP': 'Lost Mine of Phandelver', 'OotA': 'Out of the Abyss',
    'PotA': 'Princes of the Apocalypse', 'RoT': 'Rise of Tiamat', 'SKT': "Storm King's Thunder",
    'SCAG': "Sword Coast Adventurer's Guide", 'TftYP': 'Tales from the Yawning Portal',
    'VGtM': "Volo's Guide to Monsters", 'TSC': 'The Sunless Citadel', 'TFoF': 'The Forge of Fury',
    'THSoT': 'The Hidden Shrine of Tamoachan', 'WPM': 'White Plume Mountain', 'DiT': 'Dead in Thay',
    'AtG': 'Against the Giants', 'ToH': 'Tomb of Horrors', 'ToA': 'Tomb of Annihilation',
    'CoSCO': 'Curse of Strahd: Character Options', 'XGtE': "Xanathar's Guide to Everything",
    'TTP': 'The Tortle Package', 'UA': 'Unearthed Arcana', 'DDB': 'D&D Beyond', 'CR': 'Critical Role',
    'TCS': "Tal'Dorei Campaign Setting", 'MToF': 'Mordenkainen’s Tome of Foes', 'DDIA-MORD': 'Rrakkma',
    'WDH': 'Waterdeep: Dragon Heist', 'WDotMM': 'Waterdeep: Dungeon of the Mad Mage',
    'WGtE': "Wayfinder's Guide to Eberron", 'GGtR': "Guildmasters' Guide to Ravnica", '_APT': 'Archived Playtest',
    'LLoK': 'Lost Laboratory of Kwalish', 'DoIP': 'Dragon of Icespire Peak', 'TMR': 'Tactical Maps Reincarnated',
    'GoS': 'Ghosts of Saltmarsh', 'AI': 'Acquisitions Incorporated', 'HftT': 'Hunt for the Thessalhydra',
    'BGDiA': "Baldur's Gate: Descent into Avernus", 'ERftLW': 'Eberron: Rising from the Last War',
    'SLW': 'Storm Lord’s Wrath', 'SDW': 'Sleeping Dragon’s Wake', 'DC': 'Divine Contention',
    'SAC': 'Sage Advice Compendium', 'DDvRaM': 'Dungeons & Dragons vs. Rick and Morty', 'LR': 'Locathah Rising',
    'IMR': 'Infernal Machine Rebuild', 'MFFV1': "Mordenkainen's Fiendish Folio Volume 1", 'SD': 'Sapphire Dragon',
    'EGtW': "Explorer's Guide to Wildemount", 'OGA': 'One Grung Above', 'MOoT': 'Mythic Odysseys of Theros',
    'WA': 'Frozen Sick', 'TSCF': 'The Sunless Citadel (Free)', 'TFoFF': 'The Forge of Fury (Free)',
    'LRDToB': 'Legends of Runeterra: Dark Tides of Bilgewater', 'IDRotF': 'Icewind Dale: Rime of the Frostmaiden',
    'TCoE': 'Tasha’s Cauldron of Everything'
}


