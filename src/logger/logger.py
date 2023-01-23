import logging
import logging.config
import yaml


##################
### logger Use ###
##################

# from logger import createLogger
# logger.debug("debug message")
# logger.info("info message")
# logger.warning("warn message")
# logger.error("error message")
# logger.critical("critical message")

# log file loadtion is defined in logging.yml as:
#    filename: path_to/name.log

config_file = "src/logger/logging.yml"


def createLogger(name="root"):
    logger = logging.getLogger(name)
    return logger


try:
    with open(config_file, "r") as stream:
        config = yaml.load(stream, Loader=yaml.FullLoader)
    logging.config.dictConfig(config)
except FileNotFoundError as error:
    print("Error: " + str(error))
    exit(1)


def main():
    print("You are running logger.py directly. It should be imported.")


if __name__ == "__main__":
    main()
