# Deploying a Containerised Web Application

The following structure depicts the structure of this repository

```
├── chat_curses_client.py
├── cleverbot.py
├── docker
│   └── rabbitmq
│       ├── conf.d
│       │   └── 10-defaults.conf
│       └── enabled_plugins
├── README.md
└── requirements.txt

```

We can find at the top level `chat_curses_client.py`, this is the Python Pika client with an curses interface that allows to communicate with the bot, then `cleverbot.py`, which is a [project hosted on Github](https://github.com/plasticuproject/cleverbotfree) to be able to talk with [Cleverbot](https://www.cleverbot.com/), a warning when using Cleverbot, taken from their site


```
may not be suitable for children - must be agreed by parent or guardian

it learns and imitates, is social content and aims to pass the Turing Test

can seem rude or inappropriate - talk with caution and at your own risk

the bot pretends to be human - don't give personal info even if it 'asks'

cleverbot does not understand you, and cannot mean anything it 'says'
```

Now, the `requirements.txt` is the dependencies that the client and cleverbot require to be run. Within the `docker` folder we will place everything container related. It currently contains a RabbitMQ configuration folder.


### Client usage section

To use the client you will require Python3 installed either in a [virtual environment](https://docs.python.org/3/library/venv.html) or simply by installing it system-wide. [pip](https://pip.pypa.io/en/stable/) is the package manager used by Python, the test has been designed to run under Python 3.9.5, and all the dependecies are in `requirements.txt`. To run the chat curses client, first install the dependencies using the following command

```
python3.9 -m pip install -r requirements.txt
```

To run it 

```
python3.9 chat_curses_client.py
```

To exit the program, use `Ctrl-C` several times to kill the program.


### Chat application structure

The chat server is implemented using [RabbitMQ queues](https://www.rabbitmq.com/), the developers have chosen to use an [exchange](https://www.rabbitmq.com/tutorials/tutorial-three-python.html) with [topics](https://www.rabbitmq.com/tutorials/tutorial-five-python.html) to route the messages.


### Cleverbot

Cleverbot will connect to the rabbit exchange and will consume and produce messaages by interacting with him through the curses client.


## Excersise

This will guide you on what needs to be done

### Part one - RabbitMQ

First we need to bring up the RabbitMQ server, to achieve this we will be using [docker-compose](https://docs.docker.com/compose/). Install Docker and docker-compose if not already done.
Create the `docker/docker-compose.yml` file. For this first part you will need to bring up a RabbitMQ server, this server:

- Must expose port 5672
- Must bind the `docker/rabbitmq/` onto `/etc/rabbitmq/` within the server
- Must use the image `rabbitmq:3.10-management`
- Place the container on `10.100.0.10`, to achieve this 
	- The stack must define a network named `protected` with subnet range `10.100.0.0/24` * If this subnet interferes with your system, change it to a similar `/24` network
- Change the default username of RabbitMQ to `admin` and password `toor`


Once you have defined all of the above you can run the stack, from the repository root as follows

```
docker-compose -f docker/docker-compose.yml up
```

Now that we have a RabbitMQ server running we can proceed to connect Cleverbot

### Part two - Cleverbot

Both `chat_curses_client.py` and `cleverbot.py` fetch 4 variables that define where RabbitMQ is located. These are

```
RABBIT_HOST # Host
RABBIT_PORT # Port on the host
RABBIT_USER # Username to use when authenticating
RABBIT_PASW # Password to use when authenticating
```

For part two, create the following file `docker/cleverbot.Dockerfile`, using the instruction of the [original github repository](https://github.com/plasticuproject/cleverbotfree), the `cleverbot.py` application needs to be dockerized.

- The image must use `python:3.10-bullseye`
- The application must be placed in `/app/`
- The docker-compose stack must define the build, taking care the context is set relatively from the file to the root of the repository
- The enviroment variables must point to the RabbitMQ server with the right credentials
- Identify the right dependencies and install them into the container
- Place the container on `10.100.0.20`

Once complete, you can `up` the stack using

```
docker-compose -f docker/docker-compose.yml up
```

And you should see the container building, ultimately connecting to the RabbitMQ server previously deployed

### Checking!

Now we have everything running, we can define the abovementioned variables accordingly, and run

```
python3.9 chat_curses_client.py
```

This should appear as 3 windows, Log window at the top, Message window in the middle, Input box at the bottom, type `Hi!` and if everything is working, you should get a response from Cleverbot.



## Useful resources

- [Docker Compose documentation](https://docs.docker.com/compose/compose-file/compose-file-v3/)
- [Docker Hub RabbitMQ image page](https://hub.docker.com/_/rabbitmq)
- [RabbitMQ configuration file reference ](https://hub.docker.com/_/rabbitmq)

- [Virtual environments in python](https://docs.python.org/3/library/venv.html)
- [pip](https://pip.pypa.io/en/stable/)
- [cleverbot](https://www.cleverbot.com/)
- [cleverbotfree github repository](https://github.com/plasticuproject/cleverbotfree)
