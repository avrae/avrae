"""
Created on May 6, 2017

@author: mommo
"""

class MissingAttribute(Exception):
    
    def __init__(self, attribute):
        self.attribute = attribute
        super().__init__("Missing character attribute: {}".format(attribute))