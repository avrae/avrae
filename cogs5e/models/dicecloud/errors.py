from cogs5e.models.errors import AvraeException


class DicecloudException(AvraeException):
    """A base exception for exceptions relating to the Dicecloud Meteor client to stem from."""
    pass


class LoginFailure(DicecloudException):
    """Raised when a login fails."""

    def __init__(self):
        super().__init__("Failed to login.")


class InsertFailure(DicecloudException):
    """Raised when an insertion fails."""

    def __init__(self, error):
        super().__init__(f"Failed to insert: {error}")


class HTTPException(DicecloudException):
    """Generic HTTP exception (status code [400, 599])
    On a 400 we get some additional error message under err"""

    def __init__(self, status, msg):
        super(HTTPException, self).__init__(msg)
        self.status = status


class Forbidden(HTTPException):
    """403"""

    def __init__(self, msg):
        super(Forbidden, self).__init__(403, msg)


class NotFound(HTTPException):
    """404"""

    def __init__(self, msg):
        super(NotFound, self).__init__(404, msg)


class Timeout(HTTPException):
    """10x 429"""

    def __init__(self, msg):
        super(Timeout, self).__init__(429, msg)
