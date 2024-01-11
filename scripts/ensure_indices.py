import os

from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient

INDICES = {
    # homebrew
    "packs": [IndexModel("owner")],
    "pack_subscriptions": [IndexModel([("type", ASCENDING), ("subscriber_id", ASCENDING)]), IndexModel("object_id")],
    "bestiaries": [IndexModel([("upstream", ASCENDING), ("sha256", ASCENDING)], unique=True)],
    "bestiary_subscriptions": [
        IndexModel("type"),
        IndexModel("subscriber_id"),
        IndexModel("object_id"),
        IndexModel("provider_id"),
    ],
    "tomes": [IndexModel("owner")],
    "tome_subscriptions": [IndexModel([("type", ASCENDING), ("subscriber_id", ASCENDING)]), IndexModel("object_id")],
    # analytics
    "analytics_user_activity": [IndexModel("user_id", unique=True), IndexModel([("last_command_time", DESCENDING)])],
    "analytics_guild_activity": [IndexModel("guild_id", unique=True), IndexModel([("last_command_time", DESCENDING)])],
    "analytics_command_activity": [IndexModel("name", unique=True)],
    "analytics_command_events": [
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel("command_name"),
        IndexModel("user_id"),
        IndexModel("guild_id"),
    ],
    "analytics_ddb_activity": [IndexModel("user_id", unique=True), IndexModel([("last_link_time", DESCENDING)])],
    "analytics_nsrd_lookup": [IndexModel("type")],
    "analytics_alias_events": [IndexModel("object_id"), IndexModel("type"), IndexModel([("timestamp", DESCENDING)])],
    "analytics_daily": [IndexModel([("timestamp", DESCENDING)])],
    "random_stats": [IndexModel("key", unique=True)],
    # aliases
    "aliases": [IndexModel([("owner", ASCENDING), ("name", ASCENDING)], unique=True)],
    "gvars": [IndexModel("key", unique=True)],
    "snippets": [IndexModel([("owner", ASCENDING), ("name", ASCENDING)], unique=True)],
    "servaliases": [IndexModel([("server", ASCENDING), ("name", ASCENDING)], unique=True)],
    "servsnippets": [IndexModel([("server", ASCENDING), ("name", ASCENDING)], unique=True)],
    "uvars": [IndexModel([("owner", ASCENDING), ("name", ASCENDING)], unique=True)],
    "svars": [IndexModel("owner"), IndexModel([("owner", ASCENDING), ("name", ASCENDING)], unique=True)],
    # core bot stuff
    "prefixes": [IndexModel("guild_id", unique=True)],
    "users": [IndexModel("id", unique=True), IndexModel([("username", ASCENDING), ("discriminator", ASCENDING)])],
    "characters": [
        IndexModel([("owner", ASCENDING), ("upstream", ASCENDING)], unique=True),
        IndexModel([("owner", ASCENDING), ("active", ASCENDING)], background=True),
        IndexModel([("owner", ASCENDING), ("active_guilds", ASCENDING)], background=True),
    ],
    "combats": [IndexModel("channel", unique=True), IndexModel("lastchanged", expireAfterSeconds=2592000)],
    "lookupsettings": [  # deprecated in feature/settings-menus branch, replaced by guild_settings
        IndexModel("server", unique=True)
    ],
    "static_data": [],
    "user_permissions": [IndexModel("id", unique=True)],
    "tutorial_map": [IndexModel("user_id", unique=True)],
    "guild_settings": [IndexModel("guild_id", unique=True)],
    # alias workshop
    "workshop_collections": [
        IndexModel("publish_state"),
        IndexModel("tags"),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("last_edited", DESCENDING)]),
        IndexModel([("num_guild_subscribers", DESCENDING)]),
        IndexModel("owner"),
    ],
    "workshop_aliases": [
        IndexModel("parent_id"),
        IndexModel([("parent_id", ASCENDING), ("name", ASCENDING)]),
        IndexModel("collection_id"),
    ],
    "workshop_snippets": [IndexModel("collection_id")],
    "workshop_subscriptions": [
        IndexModel("type"),
        IndexModel([("type", ASCENDING), ("subscriber_id", ASCENDING)]),
        IndexModel("object_id"),
    ],
    # game log linking
    "ddb_account_map": [IndexModel("ddb_id", unique=True), IndexModel("discord_id", unique=True)],
    "gamelog_campaigns": [IndexModel("campaign_id", unique=True), IndexModel("channel_id")],
}


def run(mdb):
    for coll_name, indices in INDICES.items():
        if not indices:
            continue
        print(f"\nCreating indices on {coll_name}...")
        coll = mdb[coll_name]
        try:
            result = coll.create_indexes(indices)
            print(result)
        except Exception as e:
            print(f"ERR! {e}")

    print("done.")


if __name__ == "__main__":
    mclient = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))


    mdb = mclient[os.getenv("MONGO_DB", "avrae")]

    input(f"Indexing on {mdb.name}. Press enter to continue.")
    run(mdb)
