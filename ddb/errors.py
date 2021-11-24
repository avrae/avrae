import aiohttp


class DDBException(Exception):
    """Base exception for all DDB-related exceptions"""
    pass


class ClientException(DDBException, aiohttp.ClientError):
    """Something happened in a service client"""
    pass


class ClientResponseError(ClientException):
    """The response is an error status code"""
    pass


class ClientValueError(ClientException):
    """We cannot deserialize the client's response"""
    pass


class ClientTimeoutError(ClientException, aiohttp.ServerTimeoutError):
    """We timed out connecting to the server"""
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
