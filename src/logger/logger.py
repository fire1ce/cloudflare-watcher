import logging
import logging.config
import yaml


def createLogger(name="root"):
    logger = logging.getLogger(name)
    return logger


# logger = logging.getLogger(__name__)
try:
    with open("logging.yml", "r") as stream:
        config = yaml.load(stream, Loader=yaml.FullLoader)
    logging.config.dictConfig(config)
except FileNotFoundError as error:
    print("Error: " + str(error))
    exit(1)
