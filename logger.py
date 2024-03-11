import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os

from colorama import Fore, Style


class mylogger:
    def __init__(self) -> None:
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        logging.getLogger('urllib3').setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        if not os.path.exists('log'):
            os.mkdir('log')
        fh = TimedRotatingFileHandler(
            filename='log/vtb_dynamic.log', encoding='utf-8', when="midnight", interval=1, backupCount=7)
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def info(self, msg, prefix="", color=""):
        msg = prefix+msg
        if color:
            msg = color+msg+Style.RESET_ALL
        self.logger.info(msg, stacklevel=2)

    def debug(self, msg, prefix="", color=""):
        msg = prefix+msg
        if color:
            msg = color+msg+Style.RESET_ALL
        self.logger.debug(msg, stacklevel=2)

    def warning(self, msg, prefix="", color=Fore.YELLOW):
        msg = prefix+msg
        if color:
            msg = color+msg+Style.RESET_ALL
        self.logger.warning(msg, stacklevel=2)

    def error(self, msg, prefix="", color=Fore.RED):
        msg = prefix+msg
        if color:
            msg = color+msg+Style.RESET_ALL
        self.logger.error(msg, stacklevel=2)


logger = mylogger()
