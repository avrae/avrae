from confluent_kafka import Producer
from utils import config as bot_config
import logging
import time
import json
import asyncio

log = logging.getLogger(__name__)


class KafkaProducer:
    """
    Kafka producer class to produce messages to a Kafka topic using Confluent Kafka Python client.

    Attributes:
        producer (Producer): Confluent Kafka producer object.

    Methods:
        delivery_callback: Callback function to handle message delivery status.
        produce: Produce a message to a Kafka topic.

    """

    config = {
        "bootstrap.servers": bot_config.KAFKA_BOOTSTRAP_SERVER,
        "sasl.username": bot_config.KAFKA_API_KEY,
        "sasl.password": bot_config.KAFKA_API_SECRET,
        "security.protocol": bot_config.KAFKA_SECURITY_PROTOCOL,
        "sasl.mechanisms": bot_config.KAFKA_SASL_MECHANISM,
        "acks": bot_config.KAFKA_ACKS,
    }

    def __init__(self, config):
        if not config["bootstrap.servers"] or not config["sasl.username"] or not config["sasl.password"]:
            self.is_ready = False
            log.warning("Kafka not initialized. Missing configuration.")
            return None
        log.info("Kafka Initialized")
        self.is_ready = True
        self.producer = Producer(config)
        self.topic = "dnddev_avraebot" if bot_config.TESTING else "dndprod_avraebot"

    def delivery_callback(self, err, msg):
        if err:
            log.error("ERROR: Message failed delivery: {}".format(err))
        else:
            log.info(
                "Produced event to topic {topic}: key = {key:12} value = {value:12}".format(
                    topic=msg.topic(), key=msg.key().decode("utf-8"), value=msg.value().decode("utf-8")
                )
            )

    async def produce(self, ctx):
        """
        Produce a message to a Kafka topic.

        Args:
            ctx (Context): Context object containing message information.
        """
        if not self.is_ready:
            log.warning("Kafka not initialized. Missing configuration.")
            return None
        if self.topic is None:
            log.warning("Kafka topic not specified.")
            return None

        avrae_command = {
            "EVENT_TIME": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "PLATFORM": "discord",
            "MESSAGE_ID": ctx.message.id,
            "MESSAGE_NAME": "AVRAE_COMMAND",
            "DISCORD_ID": ctx.message.author.id,
            "DDB_USER_ID": ctx.message.author.name,
            "DISCORD_SERVER_ID": ctx.message.guild.id if ctx.message.guild else None,  # Guild ID is empty on a DM
            "COUNTRY_CODE": None,
            "IP_ADDRESS": None,
            "COMMAND_ID": ctx.command.qualified_name if ctx.command else ctx.message.content,
            "COMMAND_CATEGORY": ctx.command.cog_name if ctx.command else None,
            "SUBCOMMAND_ID": None,
            "ARGS": ctx.message.content.split(" ")[1:],
        }

        # Wrap the synchronous Kafka producer logic in a run_in_executor
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,  # Use the default executor
            self._produce_sync,  # Call the synchronous method
            avrae_command,  # Pass the command data
            ctx.message.id,  # Pass the message ID as the key
        )

    def _produce_sync(self, avrae_command, message_id):
        """
        Synchronous method to produce a message to Kafka.
        """
        self.producer.produce(self.topic, json.dumps(avrae_command), str(message_id), callback=self.delivery_callback)
        self.producer.poll(0.1)
