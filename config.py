import configparser
import os
from colorama import Fore, Style
from logger import logger
from time import sleep
import threading


def update_config(config):
    while True:
        config.update()
        sleep(30)


class Config(object):
    def __init__(self, config_file='config.ini'):
        self._path = os.path.join(os.getcwd(), config_file)
        self._config = configparser.ConfigParser()
        self._configRaw = configparser.RawConfigParser()
        if not os.path.exists(self._path):
            logger.error('配置文件不存在: config.ini', '【Config】')
        thread = threading.Thread(target=update_config, args=[self])
        thread.start()

    def get(self, section, name):
        logger.debug(
            Fore.GREEN+f'【Config】加载配置{section}下的{name}'+Style.RESET_ALL)
        try:
            return self._config.get(section, name)
        except:
            return None

    def get_raw(self, section, name):
        logger.debug(
            Fore.GREEN+f'【Config】加载配置{section}下的{name}'+Style.RESET_ALL)
        try:
            return self._configRaw.get(section, name)
        except:
            return None

    def update(self):
        logger.debug('更新Config', '【Config】', Fore.GREEN)
        self._config.read(self._path, encoding='utf-8-sig')
        self._configRaw.read(self._path, encoding='utf-8-sig')


global_config = Config()
