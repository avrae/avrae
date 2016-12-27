import random


def getJoinMessage():
    joinArray = ["**Result:** 76. Ragnarok's here!",
                 "Ragnarok has been summoned by the great god Bahamut.",
                 "All hail Tiamat!",
                 "I just woke up, whaddaya want?",
                 "Is this thing on?",
                 "Beep boop, I'm a bot.",
                 "Roll a DEX save, I sneezed.",
                 "Deal with it.",
                 "*yawn*"]
    return ''

def getCritMessage():
    critArray = ["",
                 "Maybe you'll be able to hit, for once.",
                 "**fistbump**",
                 "Maybe they were just distracted?",
                 "Enemy off balance! If in combat, DC 15 DEX save or be knocked prone.",
                 "Do a barrel roll!",
                 "For science!",
                 "Do an aileron roll! Even though dragons don't have ailerons!",
                 "Ryuu ga waga teki wo kurau!"]
    return ''

def getFailMessage():
    failArray = ["",
                 "(╯°□°）╯︵ ┻━┻",
                 "You failed!",
                 "playerpls",
                 "Your attack swings straight and true, missing the enemy with calculated precision.",
                 "You're off balance! If applicable, DC 15 DEX save or fall prone.",
                 "You're overextended! -2 to your AC next turn!",
                 "http://vignette3.wikia.nocookie.net/sims/images/b/bb/There_was_an_attempt.png/revision/latest?cb=20140923153317",
                 "I can't watch."]
    return ''

def getAllSpellMessage():
    allSpellArray = ["...No.",
                 "Really?",
                 "A-L-L. All.",
                 "All, 10th-level Magic.\n**Casting Time:** Instantaneous\n**Range:** Infinity\n**Components:** V, S, M\n**Material Requirement:** Your character sheet.\n**Duration:** Until dispelled\n**Concentration:** no\n\nRagnarok gains control of your character for the duration of this spell."]
    return random.choice(allSpellArray) #allSpellArray[random.randint(0, len(allSpellArray) - 1)]

def getGameName():
    gameNameArray = ["D&D 5e",
                     "Barrel Roll Simulator 2016",
                     "Dungeons and Dragons",
                     "The Game"]
    return gameNameArray[0]
