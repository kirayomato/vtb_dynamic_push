import configparser
import os
import re
import traceback
from colorama import Fore, Style
from logger import logger
from time import sleep
import threading
import json

prefix = "【Config】"


def update_config(config):
    while True:
        config.update()
        sleep(30)


def parse_cookie(raw):
    """把 cookie 来源（文件内容/字符串）统一解析成 {name: value} 字典。

    支持三种写法，向后兼容旧的浏览器导出 JSON 数组：
      1. JSON 数组: [{"name": "...", "value": "..."}, ...]
      2. JSON 对象: {"name": "value", ...}
      3. 原始 Cookie 头字符串: "name1=val1; name2=val2"
         （可带可选的 "Cookie:" 前缀，如开发者工具复制到的完整请求头）
    无法解析时返回 {}。
    """
    if not raw or not raw.strip():
        return {}
    s = raw.strip()
    # 1) 先尝试 JSON（数组或对象）
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        data = None
    if isinstance(data, list):
        cookies = {}
        for c in data:
            if isinstance(c, dict) and "name" in c:
                cookies[c["name"]] = c.get("value")
        return cookies
    if isinstance(data, dict):
        # 纯对象写法直接当 {name: value}
        return {k: v for k, v in data.items()}
    # 2) 当作原始 Cookie 头字符串解析
    return _parse_cookie_string(s)


def _parse_cookie_string(s):
    """解析 `name=value; name=value` 形式的 Cookie 头字符串。

    兼容可选的 "Cookie:" 前缀（开发者工具复制到的完整请求头）。
    按分号切分，每个片段取第一个 '=' 左边为键、右边为值。
    """
    s = re.sub(r"^\s*cookie\s*:\s*", "", s, flags=re.IGNORECASE).strip()
    cookies = {}
    for part in s.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if name:
            cookies[name] = value.strip()
    return cookies


def load_cookie(path, ck, name, _prefix):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        cookies = parse_cookie(raw)
        if not cookies:
            logger.warning(f"{name}Cookie为空或无法解析: {path}", prefix)
            return ck
        logger.debug(f"读取{path}", prefix, Fore.GREEN)
        if ck != cookies:
            ck = cookies
            logger.info(f"{name}Cookie更新", _prefix, Fore.GREEN)
            if name == "微博":
                for key in ("SSOLoginState", "mweibo_short_token"):
                    if not ck.get(key):
                        logger.warning(f"微博Cookie缺少{key}", prefix)
    except BaseException as e:
        logger.error(f"{name}Cookie读取错误: {e}", _prefix)
    return ck


class Config(object):
    def __init__(self, config_file="config.ini"):
        self._path = os.path.join(os.getcwd(), config_file)
        self._config = configparser.ConfigParser(interpolation=None)
        self.WeiboCookies = {}
        self.BiliCookies = {}
        if not os.path.exists(self._path):
            logger.error("配置文件不存在: config.ini", prefix)
            return
        self._lock = threading.Lock()
        self.update()
        thread = threading.Thread(target=update_config, args=[self], daemon=True)
        thread.start()

    def get(self, section, name, default=None):
        logger.debug(f"加载配置{section}下的{name}", prefix)
        try:
            with self._lock:
                return self._config.get(section, name)
        except (configparser.NoSectionError, configparser.NoOptionError):
            logger.error(f"配置文件缺少: [{section}]:{name}", prefix)
            return default
        except BaseException as e:
            logger.error(
                f"加载配置{section}下的{name}时出错【{e}】：{traceback.format_exc()}",
                prefix,
            )
            return default

    def update(self):
        logger.debug("更新Config", prefix, Fore.GREEN)
        with self._lock:
            self._config.read(self._path, encoding="utf-8-sig")
        self.WeiboCookies = load_cookie(
            "WeiboCookies.json", self.WeiboCookies, "微博", "【查询微博状态】"
        )

        self.BiliCookies = load_cookie(
            "BiliCookies.json", self.BiliCookies, "B站", "【查询B站状态】"
        )


general_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "connection": "close",
    "sec-ch-ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
