import configparser
import os
from colorama import Fore, Style
from logger import logger
from time import sleep
import threading
import json
from copy import deepcopy


def update_config(config):
    while True:
        config.update()
        sleep(30)


def load_cookie(path, ck, name, prefix):
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write('[]')
    try:
        with open(path, 'r') as f:
            temp = json.load(f)
        cookies = {}
        for cookie in temp:
            cookies[cookie.get('name')] = cookie.get('value')
        logger.debug(f'读取{path}', '【Cookies】', Fore.GREEN)
        if ck != cookies:
            ck = cookies
            logger.info(f'{name}Cookies更新', prefix, Fore.GREEN)
    except BaseException as e:
        logger.error(f'{name}Cookies读取错误: {e}', prefix)
    return ck


class Config(object):
    def __init__(self, config_file='config.ini'):
        self._path = os.path.join(os.getcwd(), config_file)
        self._config = configparser.ConfigParser()
        self._configRaw = configparser.RawConfigParser()
        self.WeiboCookies = {}
        self.BiliCookies = {}
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
        self.WeiboCookies = load_cookie(
            'WeiboCookies.json', self.WeiboCookies, '微博', '【查询微博状态】')
        self.BiliCookies = load_cookie(
            'BiliCookies.json', self.BiliCookies, 'B站', '【查询B站状态】')


global_config = Config()
