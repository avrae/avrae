class DDBException(Exception):
    """Base exception for all DDB-related exceptions"""
    pass


class ClientException(DDBException):
    """Something happened in a service client"""
    pass


class WaterdeepException(ClientException):
    """Some Waterdeep HTTP exception happened"""
    pass


class AuthException(ClientException):
    """Something happened during auth that shouldn't have"""
    pass


class CharacterServiceException(ClientException):
    """Some error happened during a call to the character service"""
    pass
