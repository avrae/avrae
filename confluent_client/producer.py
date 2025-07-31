from confluent_kafka import Producer
from utils import config as bot_config, context
from ddb.auth import BeyondUser
import disnake
from typing import Optional
import logging
import time
import json

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

    def __init__(self, config=None):
        producer_config = self._build_producer_config(config)
        if not producer_config["bootstrap.servers"]:
            self.is_ready = False
            log.warning("Kafka not initialized. Missing configuration.")
            return None

        log.info("Kafka Initialized")
        self.is_ready = True
        self.producer = Producer(producer_config)
        self.topic = "dndprod_avraebot" if bot_config.ENVIRONMENT == "production" else "dnddev_avraebot"

    def _build_producer_config(self, override_config=None):
        """
        Build producer configuration from environment variables and optional overrides.
        """
        base_config = {
            "bootstrap.servers": bot_config.KAFKA_BOOTSTRAP_SERVER,
            "acks": bot_config.KAFKA_ACKS,
            "linger.ms": bot_config.KAFKA_LINGER_MS,
            "compression.type": bot_config.KAFKA_COMPRESSION_TYPE,
        }

        sals_fields = {
            "sasl.username": bot_config.KAFKA_API_KEY,
            "sasl.password": bot_config.KAFKA_API_SECRET,
            "security.protocol": bot_config.KAFKA_SECURITY_PROTOCOL,
            "sasl.mechanisms": bot_config.KAFKA_SASL_MECHANISM,
        }

        if all(sals_fields.values()):
            log.warning("SASL authentication configured for Kafka.")
            base_config.update(sals_fields)
        else:
            log.warning("SASL authentication not configured for Kafka. Using plaintext connection.")

        # Override with any additional configuration provided
        if override_config:
            base_config.update(override_config)

        return base_config

    def _validate_producer_ready(self):
        """Check if producer is ready and return early if not."""
        if not self.is_ready:
            log.warning("Kafka not initialized. Missing configuration.")
            return False
        if self.topic is None:
            log.warning("Kafka topic not specified.")
            return False
        return True

    def _delivery_callback(self, err, msg):
        """Callback function to handle message delivery status."""
        if err is not None:
            log.error(f"Kafka Message delivery failed: {err}")
        else:
            log.debug(f"Kafka Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")

    def _send_message(self, message_data: dict, message_id: int):
        """Send message to Kafka topic."""
        try:
            self.producer.produce(
                topic=self.topic,
                value=json.dumps(message_data),
                key=str(message_id),
                on_delivery=self._delivery_callback,
            )
        except Exception as e:
            log.error(f"Exception while producing message to Kafka: {e}")
            return None

        # Poll the producer to handle delivery reports. Setting the timeout to 0 avoids blocking
        # but will call the deliver callback for any messages that have been sent.
        self.producer.poll(0)

    async def produce_command(self, ctx: context.AvraeContext):
        """
        Produce a message to a Kafka topic.

        Args:
            ctx (Context): Context object containing message information.
        """
        if not self._validate_producer_ready():
            return None

        ddb_user: Optional[BeyondUser] = await ctx.bot.ddb.get_ddb_user(ctx, ctx.message.author.id)

        avrae_command = {
            "EVENT_TIME": time.strftime("%Y-%m-%dT%H:%M:%SZ", ctx.message.created_at.timetuple()),
            "PLATFORM": "discord",
            "MESSAGE_ID": ctx.message.id,
            "MESSAGE_NAME": "AVRAE_COMMAND",
            "DISCORD_ID": ctx.message.author.id,
            "DDB_USER_ID": ddb_user.user_id if ddb_user else None,
            "DISCORD_SERVER_ID": ctx.message.guild.id if ctx.message.guild else None,  # Guild ID is empty on a DM
            "COMMAND_ID": ctx.command.qualified_name if ctx.command else None,
            "COMMAND_CATEGORY": ctx.command.cog_name if ctx.command else None,
            "SUBCOMMAND_ID": ctx.invoked_subcommand.qualified_name if ctx.invoked_subcommand else None,
        }

        self._send_message(avrae_command, ctx.message.id)

    async def produce_slash_command(self, interaction: disnake.ApplicationCommandInteraction):
        """
        Produce a slash command interaction message to a Kafka topic.
        """
        if not self._validate_producer_ready():
            return None

        ddb_user: Optional[BeyondUser] = await interaction.bot.ddb.get_ddb_user(interaction, interaction.author.id)

        avrae_command = {
            "EVENT_TIME": time.strftime("%Y-%m-%dT%H:%M:%SZ", interaction.created_at.timetuple()),
            "PLATFORM": "discord",
            "MESSAGE_ID": interaction.id,
            "MESSAGE_NAME": "AVRAE_SLASH_COMMAND",
            "DISCORD_ID": interaction.author.id,
            "DDB_USER_ID": ddb_user.user_id if ddb_user else None,
            "DISCORD_SERVER_ID": interaction.guild.id if interaction.guild else None,  # Guild ID is empty on a DM
            "COMMAND_ID": interaction.data.name,
            "COMMAND_CATEGORY": interaction.data.type.name if interaction.data.type else None,
            "SUBCOMMAND_ID": interaction.data.options[0].name if interaction.data.options else None,
        }

        self._send_message(avrae_command, interaction.id)
