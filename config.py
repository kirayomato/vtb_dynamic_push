import configparser
import os
from colorama import Fore, Style
from logger import logger
from time import sleep
import threading
import json


def update_config(config):
    while True:
        config.update()
        sleep(30)


def load_cookie(path, ck, name, prefix):
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("[]")
    try:
        with open(path, "r") as f:
            temp = json.load(f)
        cookies = {}
        for cookie in temp:
            cookies[cookie.get("name")] = cookie.get("value")
        logger.debug(f"读取{path}", "【Cookies】", Fore.GREEN)
        if ck != cookies:
            ck = cookies
            logger.info(f"{name}Cookies更新", prefix, Fore.GREEN)
    except BaseException as e:
        logger.error(f"{name}Cookies读取错误: {e}", prefix)
    return ck


class Config(object):
    def __init__(self, config_file="config.ini"):
        self._path = os.path.join(os.getcwd(), config_file)
        self._config = configparser.ConfigParser()
        self.WeiboCookies = {}
        self.BiliCookies = {}
        if not os.path.exists(self._path):
            logger.error("配置文件不存在: config.ini", "【Config】")
            return
        self.update()
        thread = threading.Thread(target=update_config, args=[self], daemon=True)
        thread.start()

    def get(self, section, name):
        logger.debug(
            Fore.GREEN + f"【Config】加载配置{section}下的{name}" + Style.RESET_ALL
        )
        try:
            return self._config.get(section, name)
        except:
            return None

    def update(self):
        logger.debug("更新Config", "【Config】", Fore.GREEN)
        self._config.read(self._path, encoding="utf-8-sig")
        self.WeiboCookies = load_cookie(
            "WeiboCookies.json", self.WeiboCookies, "微博", "【查询微博状态】"
        )
        self.BiliCookies = load_cookie(
            "BiliCookies.json", self.BiliCookies, "B站", "【查询B站状态】"
        )


general_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "accept": "*/*",
    "accept-encoding": "utf-8, gzip, deflate, zstd",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "connection": "close",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
