import uuid


def create_combatant_id():
    """Creates a unique string ID for each combatant. Might be changed to ObjectId later."""
    return str(uuid.uuid4())


def create_effect_id():
    """Creates a unique string ID for each effect. Might be changed to ObjectId later."""
    return str(uuid.uuid4())


def create_nlp_record_session_id():
    return str(uuid.uuid4())


async def nlp_feature_flag_enabled(bot):
    return await bot.ldclient.variation(
        "cog.initiative.upenn_nlp.enabled",
        # since NLP recording is keyed on the server ID, we just use a throwaway key
        {"key": "anonymous", "anonymous": True},
        default=False
    )
