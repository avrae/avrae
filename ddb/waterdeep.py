import logging

from ddb import campaign
from ddb.baseclient import BaseClient
from ddb.errors import WaterdeepException
from utils.config import DDB_WATERDEEP_URL

log = logging.getLogger(__name__)


class WaterdeepClient(BaseClient):
    SERVICE_BASE = DDB_WATERDEEP_URL
    logger = log

    async def get_active_campaigns(self, user):
        """
        Gets a list of campaigns the given user is in.

        GET /api/campaign/stt/active-campaigns

        :param user: The DDB user.
        :type user: auth.BeyondUser
        :rtype: list[campaign.ActiveCampaign]
        """
        data = await self.get(user, '/api/campaign/stt/active-campaigns')
        if not data.get('status') == 'success':
            log.warning(f"Bad Waterdeep response (data):\n{data}")
            raise WaterdeepException(f"D&D Beyond returned an error: {data}")
        return [campaign.ActiveCampaign.from_json(j) for j in data['data']]
