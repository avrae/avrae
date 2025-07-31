from confluent_kafka import Consumer


class KafkaConsumer:
    """
    Kafka consumer class to consume messages from a Kafka topic using Confluent Kafka Python client.

    Args:
        config (dict): Kafka consumer configuration.
        config['bootstrap.servers'] (str): Comma-separated list of Kafka brokers.
        config['sasl.username'] (str): Cluster API key.
        config['sasl.password'] (str): Cluster API secret.
        config['security.protocol'] (str): Security protocol. Default to SASL_SSL.
        config['sasl.mechanisms'] (str): SASL mechanism. Default to PLAIN.
        config['group.id'] (str): Consumer group ID.
        config['auto.offset.reset'] (str): Offset reset policy. Default to earliest.

    Attributes:
        consumer (Consumer): Confluent Kafka consumer object.

    Methods:
        consume: Consume messages from a Kafka topic.

    """

    def __init__(self, config):
        self.consumer = Consumer(config)

    def consume(self, topic):
        self.consumer.subscribe([topic])

        try:
            while True:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    print("Waiting...")
                    continue
                if msg.error():
                    print("Consumer error: {}".format(msg.error()))
                    continue
                print(
                    "Consumed event from topic {topic}: key = {key:12} value = {value:12}".format(
                        topic=msg.topic(), key=msg.key().decode("utf-8"), value=msg.value().decode("utf-8")
                    )
                )
                self.consumer.commit()
        except KeyboardInterrupt:
            pass
        finally:
            self.consumer.close()
