from confluent_kafka import Producer
from utils import config

class KafkaProducer:
    '''
    Kafka producer class to produce messages to a Kafka topic using Confluent Kafka Python client.
        
    Attributes:
        producer (Producer): Confluent Kafka producer object.
        
    Methods:
        delivery_callback: Callback function to handle message delivery status.
        produce: Produce a message to a Kafka topic.
        
    '''
    
    config = {
        'bootstrap.servers': config.KAFKA_BOOTSTRAP_SERVER,
        'sasl.username': config.KAFKA_API_KEY,
        'sasl.password': config.KAFKA_API_SECRET,
        'security.protocol': config.KAFKA_SECURITY_PROTOCOL,
        'sasl.mechanisms': config.KAFKA_SASL_MECHANISM,
        'acks': config.KAFKA_ACKS
    }
    
    def __init__(self, config):
        self.producer = Producer(config)
        
    def delivery_callback(self, err, msg):
        if err:
            print('ERROR: Message failed delivery: {}'.format(err))
        else:
            print("Produced event to topic {topic}: key = {key:12} value = {value:12}".format(
                topic=msg.topic(), key=msg.key().decode('utf-8'), value=msg.value().decode('utf-8')))
            
    def produce(self, topic, user, command):
        '''
        Produce a message to a Kafka topic.
        
        Args:
            topic (str): Kafka topic to produce the message.
            user (str): User ID.
            command (dict): Dictionary the command data to stream:
        '''
        self.producer.produce(topic, user, command, callback=self.delivery_callback)
        self.producer.poll(10000)
        self.producer.flush()