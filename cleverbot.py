# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205
import cleverbotfree
import uuid
import threading
import functools
import logging
import time
import pika
import os
from pika.exchange_type import ExchangeType

LOG_FORMAT = "%(message)s"
LOGGER = logging.getLogger(__name__)


class PikaClient(object):
    """
    Defines the underlying connections to a AMQP server
    """

    def __init__(self, url, exchange, exchange_type, queue_name, routing_key):
        self.url = url
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.queue_name = queue_name
        self.routing_key = routing_key

        self._connection = None
        self._channel = None

    def connect(self):
        """
        Performs a connection
        """
        LOGGER.info("Connecting to %s", self.url)
        self._connection = pika.BlockingConnection(
            parameters=pika.URLParameters(self.url),
        )

    def declare_exchange(self):
        """
        Declaring an exchange with the specified exchange type
        """
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self.exchange,
            exchange_type=self.exchange_type,
        )

    def setup_consumer(self):
        """
        An additional step requiring for a consumer to bind a
        queue to an exchange, if the queue name is not specified
        the name will be chosen for you by the server

        *NOTE*
        For fanout exchanges to properly broadcast to every consumer
        one must not specify the name
        """
        result = self._channel.queue_declare(queue=self.queue_name)
        self._channel.queue_bind(
            result.method.queue,
            self.exchange,
            routing_key=self.routing_key,
        )
        self.queue_name = result.method.queue


class CleverbotChatThread(PikaClient, threading.Thread):
    """
    This is the cleverbot thread, which acts as a consumer and
    a producer, supports only one conversation at a time currently
    """

    def __init__(self, url, exchange, exchange_type, queue_name, identity):
        threading.Thread.__init__(self)
        PikaClient.__init__(self, url, exchange, exchange_type, queue_name, "#")
        self.identity = identity

    def run(self):
        # Playwright likes context based approaches
        with cleverbotfree.sync_playwright() as p_w:

            # Define your cleverbot logic
            self.cleverbot = cleverbotfree.Cleverbot(p_w)
            while True:
                try:
                    LOGGER.info("Connecting...")
                    self.connect()
                    self.declare_exchange()
                    self.setup_consumer()
                    self._channel.basic_consume(
                        self.queue_name, on_message_callback=self.on_message
                    )
                    self._channel.start_consuming()
                except KeyboardInterrupt:
                    break
                except pika.exceptions.AMQPConnectionError:
                    LOGGER.info("Connection error, retrying in 5s")
                time.sleep(5)

    def on_message(self, _unused_channel, basic_deliver, properties, body):
        """
        Callback whenever a message is received
        """
        if not str(basic_deliver.routing_key) == str(self.identity):
            message = body.decode()

            # Ignore system messages
            if message.startswith("System:"):
                return

            # Exchange words with cleverbot
            bot = self.cleverbot.single_exchange(message)

            # Respond to the user
            self._channel.basic_publish(
                self.exchange,
                self.identity,
                bot,
            )

        # Ack the previous message
        self._channel.basic_ack(basic_deliver.delivery_tag)


class ChatClient(threading.Thread):
    """
    Main thread will use this class to manage the cleverbot thread
    """

    EXCHANGE = "chat"
    EXCHANGE_TYPE = ExchangeType.topic  # Select a fanout exchange
    QUEUE = ""  # Do not declare a queue name, so the server does

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.identity = str(uuid.uuid4())
        self.cleverbot = CleverbotChatThread(
            self.url, self.EXCHANGE, self.EXCHANGE_TYPE, self.QUEUE, self.identity
        )

    def run(self):
        """
        Threading main entrypoint
        """
        self.cleverbot.start()
        self.cleverbot.join()


def main():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    # Available environment variables
    host = os.environ.get("RABBIT_HOST", "localhost")
    pasw = os.environ.get("RABBIT_PASW", "guest")
    user = os.environ.get("RABBIT_USER", "guest")
    port = os.environ.get("RABBIT_PORT", "5672")

    # Build the url based on these
    amqp_url = f"amqp://{user}:{pasw}@{host}:{port}/%2F"

    consumer = ChatClient(amqp_url)
    consumer.run()


if __name__ == "__main__":
    main()
