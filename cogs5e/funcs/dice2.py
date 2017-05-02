'''
Created on Dec 25, 2016

@author: andrew
'''

# # Dice Roller
def roll(rollStr, adv:int=0, rollFor='', inline=False, double=False, show_blurbs=True):
    # split roll string into XdYoptsSel [comment] or Op
    # set remainder to comment
    # parse each, returning a SingleDiceResult
    # return final solution
    pass


class DiceResult:
    """Class to hold the output of a dice roll."""
    def __init__(self, result:int=0, verbose_result:str='', crit:int=0, rolled:str='', skeleton:str='', raw_dice:list=[]):
        self.plain = result
        self.total = result
        self.result = verbose_result
        self.crit = crit
        self.rolled = rolled
        self.skeleton = skeleton if skeleton is not '' else verbose_result
        self.raw_dice = raw_dice
        
    def __str__(self):
        return self.result
    
    def __repr__(self):
        return '<DiceResult object: total={}>'.format(self.total)
