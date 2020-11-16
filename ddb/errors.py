class DDBException(Exception):
    """Base exception for all DDB-related exceptions"""
    pass


class AuthException(DDBException):
    """Something happened during auth that shouldn't have"""
    pass
