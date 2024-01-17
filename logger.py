import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os
logger = logging.getLogger()


def set_logger():
    logger.setLevel(logging.DEBUG)
    logging.getLogger('urllib3').setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if not os.path.exists('log'):
        os.mkdir('log')
    fh = TimedRotatingFileHandler(
        filename='log/vtb_dynamic.log', encoding='utf-8', when="midnight", interval=1, backupCount=7)
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)


set_logger()
