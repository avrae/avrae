"""
Clustering coordination utilities - for multiple clusters to decide which shards to launch.

On start:
get my task ID
if the task coordinator exists:
    get the canonical number of shards
else:
    figure out how many shards discord wants
    create the task coordinator

if my ID is already registered in the task coordinator:
    run my shards
elif the number of clusters is below what it should be:
    claim unclaimed shards
else:
    get the list of running tasks
    figure out which task died, and take over for it
"""

import asyncio
import datetime
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from math import ceil

import aiohttp
import disnake.http

from utils import config

log = logging.getLogger(__name__)


async def coordinate_shards(bot):
    if bot.shard_ids is not None:  # we're already set up
        return
    elif config.NUM_CLUSTERS is None:  # we aren't running in clustered mode, let d.py do its thing
        return
    elif config.ECS_METADATA_ENDPT is None:  # we aren't running on ECS
        return

    await _coordinate_shards(bot)


async def _coordinate_shards(bot):
    """
    Determines the appropriate shards for this cluster, based on the clusters.GIT_COMMIT_SHA redis key.
    Key structure:
    {
        "num_shards": int,
        task_id: [int, int]
    }
    """
    cluster_coordination_key = f"clusters.{config.GIT_COMMIT_SHA}:{config.NUM_CLUSTERS}"
    coordinator_exists = await bot.rdb.exists(cluster_coordination_key)
    my_task_arn, my_family, my_ecs_cluster_name = await _get_ecs_metadata()

    # poll discord - how many shards, max concurrency?
    try:
        data = await bot.http.request(disnake.http.Route("GET", "/gateway/bot"))
    except disnake.HTTPException as e:
        raise disnake.GatewayNotFound() from e
    recommended_shards = data["shards"]
    session_start_limit = data["session_start_limit"]
    bot.launch_max_concurrency = session_start_limit["max_concurrency"]

    # alert if remaining starts < 25% total
    if session_start_limit["remaining"] < (session_start_limit["total"] * 0.25):
        log.critical(f"Remaining IDENTIFY quota low! Remaining: {session_start_limit['remaining']}")
        reset_at = datetime.datetime.now() + datetime.timedelta(milliseconds=session_start_limit["reset_after"])
        log.info(f"Resets at: {reset_at}")

    # get the total number of shards running on this acct
    if coordinator_exists:
        # get the canonical number of shards
        bot.shard_count = int(await bot.rdb.hget(cluster_coordination_key, "num_shards"))
    else:
        if config.NUM_SHARDS is not None:
            recommended_shards = config.NUM_SHARDS
        # create the task coordinator
        await bot.rdb.hset(cluster_coordination_key, "num_shards", recommended_shards)
        bot.shard_count = recommended_shards
        log.info(f"Created task coordinator {cluster_coordination_key} with num_shards={bot.shard_count}!")
    log.info(f"Session start limits: {session_start_limit}")
    log.debug(f"SHARD_COUNT={bot.shard_count}; MAX_CONCURRENCY={bot.launch_max_concurrency}")

    # claim unclaimed shards, or take over a dead task
    num_existing_clusters = await bot.rdb.hlen(cluster_coordination_key) - 1
    my_id_exists = await bot.rdb.hexists(cluster_coordination_key, my_task_arn)
    if my_id_exists:
        await _claim_existing_cluster(bot, my_task_arn, cluster_coordination_key)
    elif num_existing_clusters < config.NUM_CLUSTERS:
        await _claim_new_cluster_shards(bot, my_task_arn, cluster_coordination_key, num_existing_clusters)
    else:
        await _take_over_dead_cluster(bot, my_task_arn, cluster_coordination_key, my_family, my_ecs_cluster_name)


async def _get_ecs_metadata():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{config.ECS_METADATA_ENDPT}/task") as resp:
            data = await resp.json()

    return data["TaskARN"], data["Family"], data["Cluster"]


async def _claim_existing_cluster(bot, my_task_arn, cluster_coordination_key):
    shards_per_cluster = ceil(bot.shard_count / config.NUM_CLUSTERS)
    # I know what shards I'm supposed to be running
    my_shards = await bot.rdb.jhget(cluster_coordination_key, my_task_arn)
    bot.shard_ids = range(*my_shards)
    bot.cluster_id = my_shards[0] // shards_per_cluster
    log.info(f"Found existing task in coordinator")


async def _claim_new_cluster_shards(bot, my_task_arn, cluster_coordination_key, num_existing_clusters):
    shards_per_cluster = ceil(bot.shard_count / config.NUM_CLUSTERS)
    # I am the Nth cluster to run
    start = num_existing_clusters * shards_per_cluster
    end = min(start + shards_per_cluster, bot.shard_count)

    # I hereby claim shards [start..end)
    await bot.rdb.jhset(cluster_coordination_key, my_task_arn, [start, end])
    bot.shard_ids = range(start, end)
    bot.cluster_id = num_existing_clusters
    log.info(f"Claiming shards [{start}..{end})")


async def _take_over_dead_cluster(bot, my_task_arn, cluster_coordination_key, my_family, my_ecs_cluster_name):
    shards_per_cluster = ceil(bot.shard_count / config.NUM_CLUSTERS)
    # oh no. my ARN isn't in a claimed list and the number of claimed clusters is how many should be running
    # which means someone died.
    import boto3

    client = boto3.client("ecs")
    response = client.list_tasks(cluster=my_ecs_cluster_name, family=my_family, desiredStatus="RUNNING")
    tasks = set(response["taskArns"])

    # who's supposed to be alive?
    clusters = await bot.rdb.get_whole_dict(cluster_coordination_key)
    del clusters["num_shards"]  # you're not a cluster

    for task_arn, shard_range in clusters.items():
        if task_arn not in tasks:
            break
    else:  # ...what? all the clusters are alive!
        raise RuntimeError("Tried to replace dead cluster but all clusters are OK!")

    # the king is dead, long live the king!
    await bot.rdb.hdel(cluster_coordination_key, task_arn)

    # I hereby claim shards [start..end)
    shard_range = json.loads(shard_range)
    await bot.rdb.jhset(cluster_coordination_key, my_task_arn, shard_range)
    bot.shard_ids = range(*shard_range)
    bot.cluster_id = shard_range[0] // shards_per_cluster
    log.warning(f"Task {task_arn} is dead! Taking over...")
    log.info(f"Claiming shards [{shard_range[0]}..{shard_range[1]})")


# lock: don't race when coordinating clusters
@asynccontextmanager
async def coordination_lock(rdb):
    cluster_lock_key = f"clusters.{config.GIT_COMMIT_SHA}.lock:{config.NUM_CLUSTERS}"
    lock_value = str(uuid.uuid4())
    i = 0
    while not await rdb.setnx(cluster_lock_key, lock_value):
        await asyncio.sleep(1)
        i += 1
        log.debug(f"Waiting for lock... ({i}s)")

    log.info(f"Acquired lock with value {lock_value!r}, coordinating shards!")
    try:
        yield
    finally:
        log.info("Coordination complete, releasing lock.")
        locking_val = await rdb.get(cluster_lock_key)
        if locking_val == lock_value:
            await rdb.delete(cluster_lock_key)
        else:
            log.warning(f"Lock value is not what we set (ours was {lock_value!r}, is {locking_val!r}), ignoring value!")


# lock: each shard reserves the bucket for 5s by doing a SET NX EX with the currently launching shard id
async def wait_bucket_available(shard_id, bucket_id, rdb, *, pre_lock_hook=None):
    """
    Waits until the given shard bucket is available. Calls ``pre_lock_hook`` exactly once before each attempt
    to lock the appropriate bucket, with a kwarg ``first=True`` for the first attempt.
    """
    if pre_lock_hook is None:

        async def pre_lock_hook(first=False):
            if not first:
                await asyncio.sleep(0.2)

    # this might be improved by using a semaphore instead of a lock for each bucket - unclear how the Discord
    # concurrency ratelimit operates, but this could mitigate the grocery store checkout problem
    cluster_lock_key = f"shards.{config.GIT_COMMIT_SHA}.lock:{bucket_id}"
    start = time.monotonic()
    await pre_lock_hook(first=True)
    while not await rdb.set(cluster_lock_key, shard_id, ex=5, nx=True):
        await pre_lock_hook()
        log.debug(f"Waiting for shard lock... ({time.monotonic() - start:.2}s)")

    log.info(f"Bucket {bucket_id} is available, launching shard ID {shard_id}")
