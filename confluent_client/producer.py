from confluent_kafka import Producer

class kafka_producer:
    '''
    Kafka producer class to produce messages to a Kafka topic using Confluent Kafka Python client.
    
    Args:
        config (dict): Kafka producer configuration.
        config['bootstrap.servers'] (str): Comma-separated list of Kafka brokers.
        config['sasl.username'] (str): Cluster API key.
        config['sasl.password'] (str): Cluster API secret.
        config['security.protocol'] (str): Security protocol. Default to SASL_SSL.
        config['sasl.mechanisms'] (str): SASL mechanism. Default to PLAIN.
        config['acks'] (str): Acknowledgement level. Default to all.
        
    Attributes:
        producer (Producer): Confluent Kafka producer object.
        
    Methods:
        delivery_callback: Callback function to handle message delivery status.
        produce: Produce a message to a Kafka topic.
        
    '''
    def __init__(self, config):
        self.producer = Producer(config)
        
    def delivery_callback(self, err, msg):
        if err:
            print('ERROR: Message failed delivery: {}'.format(err))
        else:
            print("Produced event to topic {topic}: key = {key:12} value = {value:12}".format(
                topic=msg.topic(), key=msg.key().decode('utf-8'), value=msg.value().decode('utf-8')))
            
    def produce(self, topic, user, command):
        self.producer.produce(topic, user, command, callback=self.delivery_callback)
        self.producer.poll(10000)
        self.producer.flush()
