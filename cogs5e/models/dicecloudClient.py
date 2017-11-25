import logging
import time

from MeteorClient import MeteorClient

import credentials
from cogs5e.models.errors import LoginFailure

UNAME = 'avrae'
PWD = credentials.dicecloud_pass.encode()

log = logging.getLogger(__name__)


class DicecloudClient(MeteorClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logged_in = False
        self.user_id = None

    def initialize(self):
        self.connect()
        while not self.connected:
            time.sleep(0.1)
        log.info("Connected")

        def on_login(error, data):
            if data:
                self.user_id = data.get('id')
                self.logged_in = True
            else:
                raise LoginFailure()

        self.login(UNAME, PWD, callback=on_login)
        while not self.logged_in:
            time.sleep(0.1)
        log.info(f"Logged in as {self.user_id}")


dicecloud_client = DicecloudClient('ws://dicecloud.com/websocket', debug=False) # turn debug off later
dicecloud_client.initialize()
