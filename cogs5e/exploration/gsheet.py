import asyncio
import datetime
import json
import logging
import re
from contextlib import contextmanager

import google.oauth2.service_account
import gspread
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from gspread import SpreadsheetNotFound
from gspread.exceptions import APIError, WorksheetNotFound
from gspread.utils import a1_to_rowcol, fill_gaps

from cogs5e.models.errors import ExternalImportError
from cogs5e.sheets.abc import SheetLoaderABC
from .errors import MissingValues
from .encounter import Encounter
from utils import config

log = logging.getLogger(__name__)

POS_RE = re.compile(r"([A-Z]+)(\d+)")

SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

URL_KEY_V1_RE = re.compile(r"key=([^&#]+)")
URL_KEY_V2_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def extract_gsheet_id_from_url(url):
    m2 = URL_KEY_V2_RE.search(url)
    if m2:
        return m2.group(1)
    m1 = URL_KEY_V1_RE.search(url)
    if m1:
        return m1.group(1)
    raise ExternalImportError("This is not a valid Google Sheets link.")


def letter2num(letters, zbase=True):
    """A = 1, C = 3 and so on. Convert spreadsheet style column
    enumeration to a number.
    """

    letters = letters.upper()
    res = 0
    weight = len(letters) - 1
    for i, ch in enumerate(letters):
        res += (ord(ch) - 64) * 26 ** (weight - i)
    if not zbase:
        return res
    return res - 1


class Temp:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.values = worksheet.get_all_values()
        self.unformatted_values = self._get_all_unformatted_values()

    def _get_all_unformatted_values(self):
        data = self.worksheet.spreadsheet.values_get(
            self.worksheet.title, params={"valueRenderOption": "UNFORMATTED_VALUE"}
        )
        try:
            return fill_gaps(data["values"])
        except KeyError:
            return []

    @staticmethod
    def _get_value(source, pos):
        _pos = POS_RE.match(pos)
        if _pos is None:
            raise ValueError("No A1-style position found.")
        col = letter2num(_pos.group(1))
        row = int(_pos.group(2)) - 1
        if row > len(source) or col > len(source[row]):
            raise IndexError("Cell out of bounds.")
        value = source[row][col]
        log.debug(f"Cell {pos}: {value}")
        return value

    def value(self, pos):
        return self._get_value(self.values, pos)

    def unformatted_value(self, pos):
        return self._get_value(self.unformatted_values, pos)

    def value_range(self, rng):
        """Returns a list of values in a range."""
        start, end = rng.split(":")
        (row_offset, column_offset) = a1_to_rowcol(start)
        (last_row, last_column) = a1_to_rowcol(end)

        out = []
        for col in self.values[row_offset - 1 : last_row]:
            out.extend(col[column_offset - 1 : last_column])
        return out


class GoogleSheet(SheetLoaderABC):
    g_client = None
    _client_initializing = False
    _token_expiry = None

    def __init__(self, url):
        super(GoogleSheet, self).__init__(url)
        self.args = None
        self.version = (1, 0)  # major, minor

        # cache

    # google api stuff
    @staticmethod
    @contextmanager
    def _client_lock():
        if GoogleSheet._client_initializing:
            raise ExternalImportError("I am still connecting to google. Try again in a few seconds.")
        GoogleSheet._client_initializing = True
        yield
        GoogleSheet._client_initializing = False

    @staticmethod
    async def _init_gsheet_client():
        with GoogleSheet._client_lock():

            def _():
                if config.GOOGLE_SERVICE_ACCOUNT is not None:
                    credentials = Credentials.from_service_account_info(
                        json.loads(config.GOOGLE_SERVICE_ACCOUNT), scopes=SCOPES
                    )
                else:
                    credentials = Credentials.from_service_account_file("avrae-google.json", scopes=SCOPES)
                return gspread.authorize(credentials)

            try:
                GoogleSheet.g_client = await asyncio.get_event_loop().run_in_executor(None, _)
            except:
                GoogleSheet._client_initializing = False
                raise
        # noinspection PyProtectedMember
        GoogleSheet._token_expiry = datetime.datetime.now() + datetime.timedelta(
            seconds=google.oauth2.service_account._DEFAULT_TOKEN_LIFETIME_SECS
        )
        log.info("Logged in to google")

    @staticmethod
    async def _refresh_google_token():
        with GoogleSheet._client_lock():

            def _():
                GoogleSheet.g_client.auth.refresh(request=Request())
                GoogleSheet.g_client.session.headers.update(
                    {"Authorization": "Bearer %s" % GoogleSheet.g_client.auth.token}
                )

            try:
                await asyncio.get_event_loop().run_in_executor(None, _)
            except:
                GoogleSheet._client_initializing = False
                raise
        log.info("Refreshed google token")

    @staticmethod
    def _is_expired():
        return datetime.datetime.now() > GoogleSheet._token_expiry

    # load encounter data
    def _genc(self):
        doc = GoogleSheet.g_client.open_by_key(self.url)
        self.encounter_data = Temp(doc.sheet1)
        self.version = (1, 0)

    # main loading methods
    async def load_encounter(self, ctx):
        """
        Downloads and parses the encounter data, returning a fully-formed Encounter object.
        :raises ExternalImportError if something went wrong during the import that we can expect
        :raises Exception if something weirder happened
        """
        owner_id = str(ctx.author.id)
        try:
            await self.get_encounter()
        except (KeyError, SpreadsheetNotFound, APIError):
            raise ExternalImportError(
                "Invalid encounter sheet. Make sure you've shared it with me at "
                f"`{GoogleSheet.g_client.auth.signer_email}`, or made the sheet viewable to 'Anyone with the link'!"
            )
        except Exception:
            raise
        return await asyncio.get_event_loop().run_in_executor(None, self._load_encounter, owner_id)

    def _load_encounter(self, owner_id: str):
        active = False
        upstream = f"google-{self.url}"
        name = self.encounter_data.value("E3").strip() or "Unnamed"
        numappear = self.get_numberappearing()
        encountervalues = self.get_randomencountervalues()
        dice_expression = self.get_dice_expression()

        encounter = Encounter(
            owner_id,
            upstream,
            active,
            name,
            numappear,
            encountervalues,
            dice_expression
        )
        return encounter

    async def get_encounter(self):
        if GoogleSheet.g_client is None:
            await self._init_gsheet_client()
        elif GoogleSheet._is_expired():
            await self._refresh_google_token()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._genc)

    def get_numberappearing(self):
        """Returns a list of strings containing dice expressions used when rolling number of monsters"""
        if self.encounter_data is None:
            raise Exception("You must call get_encounter() first.")
        numappear = self.encounter_data.value_range("F8:F27")
        return numappear

    def get_randomencountervalues(self):
        """Returns a list of strings containing names of monsters/other encounters from the table"""
        if self.encounter_data is None:
            raise Exception("You must call get_encounter() first.")
        values = self.encounter_data.value_range("E8:E27")
        i = 8
        for v in values:
            cell = "E"+str(i)
            if v is None or v == "":
                raise MissingValues(cell, self.encounter_data.worksheet.title)
            i += 1
        return values

    def get_dice_expression(self):
        """Returns a string containing dice expression to use when rolling on the table"""
        if self.encounter_data is None:
            raise Exception("You must call get_encounter() first.")
        d_exp = self.encounter_data.value("E5")
        return d_exp
