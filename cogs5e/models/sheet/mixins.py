class HasIntegrationMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._live_integration = None
