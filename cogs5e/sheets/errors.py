"""
Created on May 6, 2017

@author: mommo
"""

from cogs5e.models.errors import ExternalImportError


class MissingAttribute(ExternalImportError):
    def __init__(self, attribute, cell, sheet):
        self.attribute = attribute
        self.cell = cell
        self.sheet = sheet
        super().__init__(f"Missing character attribute: {attribute} in cell {cell} on sheet '{sheet}'")


class AttackSyntaxError(ExternalImportError):
    def __init__(self, attack_name, cell, sheet, error):
        self.attack_name = attack_name
        self.cell = cell
        self.sheet = sheet
        self.error = error
        super().__init__(
            f"Attack syntax issue for attack '{attack_name}' in cell {cell} on sheet '{sheet}':\n> {error}"
        )


class InvalidImageURL(ExternalImportError):
    def __init__(self, sheet, error):
        self.sheet = sheet
        self.error = error
        super().__init__(f"Issue with portrait URL on cell C176 on sheet '{sheet}':\n> {error}")


class InvalidCoin(ExternalImportError):
    def __init__(self, cell, sheet, coin_type, error):
        self.cell = cell
        self.sheet = sheet
        self.coin_type = coin_type
        self.error = error
        super().__init__(f"Invalid value for {coin_type} in cell {cell} on sheet '{sheet}:\n> {error}")
