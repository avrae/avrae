from .shared import LimitedUse


class LimitedUseGrantorMixin:
    """This entity grants some limited use features, and should be considered in the limited use discovery tree"""

    def __init__(self, limited_use=None, parent=None, *args, **kwargs):
        """
        :type limited_use: list[LimitedUse]
        :type parent: LimitedUseGrantorMixin or None
        """
        super().__init__(*args, **kwargs)
        if limited_use is None:
            limited_use = []
        self.limited_use = limited_use
        self.parent = parent

    def initialize_limited_use(self, data):
        """
        Given an instance that is in the process of being constructed, set up the LimitedUses and return the instance
        (for initialization chaining).
        """
        self.limited_use = [LimitedUse.from_dict(lu, self) for lu in data.get('grantedLimitedUse', [])]
        return self


class AutomatibleMixin:
    """This entity has some attached automation"""

    def __init__(self, automation=None, *args, **kwargs):
        """
        :type automation: Automation or None
        """
        super().__init__(*args, **kwargs)
        self.automation = automation

    def initialize_automation(self, data):
        """
        Given an instance that is in the process of being constructed, set up the Automation and return the instance
        (for initialization chaining).
        """
        from cogs5e.models.automation import Automation
        self.automation = Automation.from_data(data['automation'])
        return self


class DescribableMixin:
    """This entity has a singular description that can be displayed in a single field"""
    description: str = ...
