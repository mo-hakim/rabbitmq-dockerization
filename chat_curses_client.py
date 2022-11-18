# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205
import os

import curses
import uuid
import threading
import functools
import logging
import time
import pika
import curses
import sys
from io import StringIO
from pika.exchange_type import ExchangeType
from queue import Queue
from time import sleep
from curses.textpad import rectangle, Textbox


LOG_FORMAT = "%(message)s"
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

stream = StringIO()
stream_handler = logging.StreamHandler(stream=stream)
stream_handler.setLevel(logging.INFO)

LOGGER.addHandler(stream_handler)


# Memory is shared amongst threads
outgoing_queue = Queue()
incoming_queue = Queue()


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


class ChatConsumerThread(PikaClient, threading.Thread):
    """
    This thread will take care of consuming messages and placing them into
    a local queue
    """

    def __init__(self, url, exchange, exchange_type, queue_name, identity):
        threading.Thread.__init__(self)
        PikaClient.__init__(self, url, exchange, exchange_type, queue_name, "#")
        self.identity = identity

    def run(self):
        while True:
            try:
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
        On message send it to the incoming queue to be printed by cureses
        """
        incoming_queue.put(f"[{basic_deliver.routing_key}] {body.decode()}")
        self._channel.basic_ack(basic_deliver.delivery_tag)


class ChatProducerThread(PikaClient, threading.Thread):
    """
    Producing thread, this one is in charge of sending input from
    the user into the exchange
    """

    def __init__(self, url, exchange, exchange_type, queue_name, identity):
        threading.Thread.__init__(self)
        PikaClient.__init__(self, url, exchange, exchange_type, queue_name, identity)
        self.identity = identity

    def run(self):
        while True:
            try:
                self.connect()
                self.declare_exchange()
                self._channel.basic_publish(
                    self.exchange,
                    self.routing_key,
                    f"System: User [{self.routing_key}] connected",
                )
                self.user_input_loop()
                if self.should_reconnect:
                    time.sleep(5)
            except KeyboardInterrupt:
                break

    def user_input_loop(self):
        """
        While there is input, send the messages to the exchange
        """
        while True:
            message = outgoing_queue.get(block=True)
            if message:
                self._channel.basic_publish(self.exchange, self.routing_key, message)


class ChatClient(threading.Thread):
    """
    Main thread holding the configuration of the exchange,
    spawning the consumer and producer and thus managing
    the exchange menssages
    """

    EXCHANGE = "chat"
    EXCHANGE_TYPE = ExchangeType.topic  # Select a fanout exchange
    QUEUE = ""  # Do not declare a queue name, so the server does

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.identity = str(uuid.uuid4())
        self.consumer = ChatConsumerThread(
            self.url, self.EXCHANGE, self.EXCHANGE_TYPE, self.QUEUE, self.identity
        )
        self.producer = ChatProducerThread(
            self.url, self.EXCHANGE, self.EXCHANGE_TYPE, self.QUEUE, self.identity
        )

    def run(self):
        """
        Threading main entrypoint
        """
        LOGGER.info("Starting consumer and producer")
        for handler in LOGGER.handlers:
            handler.flush()
        self.consumer.start()
        self.producer.start()
        self.consumer.join()
        self.producer.join()


class Screen(threading.Thread):
    """
    This manges the screen input and output for curses, it
    is required to share a queue for simplicity, otherwise
    a consumer and producer thread would need to be passed onto
    this class
    """

    def __init__(self):
        super().__init__()
        self.log_window = None
        self.log_messages = []
        self.message_window = None
        self.messages = []
        self.input_window = None
        self.stdscr = None
        self.input_message = []
        self.input_message_x = 1

    def redraw_log_window(self):
        """
        Log output redraw
        """
        self.log_window.refresh()
        self.write_out_logs()

    def redraw_messages_window(self):
        """
        Redraw message window
        """
        self.message_window.refresh()
        self.write_out_messages()

    def write_out_logs(self):
        """
        Write out logs in the log window
        """
        x, y = self.log_window.getyx()
        maxy, maxx = self.log_window.getmaxyx()
        stream.seek(0)
        self.log_messages.extend(stream.readlines())
        for i, message in enumerate(self.log_messages[maxy:]):
            self.log_window.addstr(min(i + 1, maxy - 3), 1, message[: maxx - 3])
            if i >= maxy:
                break
        self.log_window.refresh()

    def write_out_messages(self):
        """
        Write out messages in the messages window
        """
        x, y = self.message_window.getyx()
        maxy, maxx = self.message_window.getmaxyx()
        if not incoming_queue.empty():
            item = incoming_queue.get_nowait()
            self.messages.append(item)

        for i, message in enumerate(self.messages[:maxy]):
            self.message_window.addstr(min(i + 1, maxy - 3), 1, message[: maxx - 3])
            if i >= maxy:
                break
        self.message_window.refresh()

    def redraw_screen_windows(self):
        """
        Redraw output screens, not thread safe
        """
        self.redraw_log_window()
        self.redraw_messages_window()

    def initialize_windows(self):
        """
        Initialize the windows
        """
        maxh, maxw = self.stdscr.getmaxyx()
        messaging_section = maxh // 3
        self.log_window = curses.newwin(messaging_section, maxw - 2, 0, 0)
        logmaxh, logmaxw = self.log_window.getmaxyx()
        self.log_window.border(0, 0, 0, 0, 0, 0, 0, 0)
        self.log_window.refresh()

        self.message_window = curses.newwin(
            maxh - messaging_section - 3, maxw - 2, messaging_section, 0
        )
        self.message_window.border(0, 0, 0, 0, 0, 0, 0, 0)
        mesmaxh, mesmaxw = self.message_window.getmaxyx()

        self.input_window = curses.newwin(3, maxw - 2, maxh - 3, 0)
        self.input_window.border(0, 0, 0, 0, 0, 0, 0, 0)
        inpmaxh, inpmaxw = self.message_window.getmaxyx()
        self.input_window.refresh()

    def run(self):
        """
        Run with a wrapper, to not care about settting defaults
        and not mess up with terminal settings
        """
        curses.wrapper(self.main)

    def main(self, *args, **kwargs):
        """
        Main entrypoint
        """
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        self.initialize_windows()
        threading.Thread(target=self.input).start()

        while True:
            self.redraw_screen_windows()
            sleep(0.1)

    def input(self):
        """
        Curses input window management
        """
        _, maxx = self.input_window.getmaxyx()
        while True:
            ch = sys.stdin.read(1)
            if ord(ch) == 13:
                self.input_message_x = 1
                outgoing_queue.put("".join(self.input_message))
                self.input_message = []
                self.input_window.clear()
                self.input_window.border(0, 0, 0, 0, 0, 0, 0, 0)
                self.input_window.refresh()
            else:
                self.input_message.append(ch)

            self.input_window.addch(1, self.input_message_x, ch)
            self.input_message_x += 1
            self.input_window.refresh()


def main():
    logging.basicConfig(level=logging.INFO)

    # Available environment variables
    host = os.environ.get("RABBIT_HOST", "localhost")
    pasw = os.environ.get("RABBIT_PASW", "guest")
    user = os.environ.get("RABBIT_USER", "guest")
    port = os.environ.get("RABBIT_PORT", "5672")

    # Build the url based on these
    amqp_url = f"amqp://{user}:{pasw}@{host}:{port}/%2F"
    consumer = ChatClient(amqp_url)

    consumer.start()
    screen = Screen()
    screen.start()

    screen.join()
    consumer.join()


if __name__ == "__main__":
    main()
