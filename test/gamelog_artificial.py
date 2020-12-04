"""
Used to test sending events to the game log pubsub.
"""
import os

from redis import Redis

GAME_LOG_PUBSUB_CHANNEL = "game-log"
REDIS_URL = os.getenv('REDIS_URL')
REDIS_PASS = os.getenv('REDIS_PASS')


def main(redis):
    # setup
    p = redis.pubsub()
    p.subscribe(**{GAME_LOG_PUBSUB_CHANNEL: handle_event})
    p.run_in_thread(daemon=True)

    print("Connected, ready for events!")

    while True:
        redis.publish(GAME_LOG_PUBSUB_CHANNEL, input())


def handle_event(event):
    print(event)


if __name__ == '__main__':
    r = Redis(host=REDIS_URL, port=6379, password=REDIS_PASS, decode_responses=True)
    main(r)
