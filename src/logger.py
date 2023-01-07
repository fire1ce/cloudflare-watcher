import logging
import logging.config
import yaml

try:
    with open("logging.yml", "r") as stream:
        config = yaml.load(stream, Loader=yaml.FullLoader)
    logging.config.dictConfig(config)
except FileNotFoundError as error:
    print("Error: " + str(error))
    exit(1)


# create logger
logger = logging.getLogger()

# 'application' code
logger.debug("debug message")
logger.info("info message")
logger.warning("warn message")
logger.error("error message")
logger.critical("critical message")
