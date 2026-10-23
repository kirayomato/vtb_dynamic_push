import json
from dataclasses import dataclass
from os import environ
from os.path import realpath, isfile
import re
import time
import requests
from requests.exceptions import RequestException
from logger import logger
from push import notify
from pathlib import Path

#: 显式空代理，绕过系统代理（写 None 会回落到环境变量里的代理）
proxies = {
    "http": "",
    "https": "",
}
environ["NO_PROXY"] = "*"


def format_re(text):
    """把连续空行转成引用块（两个换行后加 '> '）。"""
    return re.sub(r"(\n{2,})", r"\n\n> ", text)


def get_active(dynamics, uid, days=30):
    """权重：1 + 最近 days 天内的动态条数。"""
    threshold = time.time() - days * 24 * 3600
    return 1 + sum(1 for item in dynamics[uid].values() if item[2] > threshold)


class CookieSuspend:
    """Cookie 连续失效后暂停查询，Cookie 更新后自动恢复。

    每个平台一个实例：失效判据、退避时长由各平台自己决定，这里只收敛
    "连续失败计数 -> 挂起 -> Cookie 变化后恢复"这套状态流转。
    """

    #: 挂起期间重复提醒的最短间隔。挂起时每个用户每轮都会调 suspended，
    #: 不节流会变成按用户数刷屏。
    REMIND_INTERVAL = 3600

    def __init__(self, name, on_click="http://127.0.0.1:5000/", limit=3):
        self.name = name
        self.on_click = on_click
        self.limit = limit
        self._streak = 0
        self._snapshot = None
        self._alerted_at = 0.0

    def suspended(self, cookie, prefix):
        """Cookie 未更新时保持挂起，检测到变化则恢复查询。

        挂起期间调用方不应发起任何请求：Cookie 失效只能由用户修复，
        继续请求只会把同一故障按用户数放大。
        """
        if self._snapshot is None:
            return False
        if cookie != self._snapshot:
            self._snapshot = None
            self._streak = 0
            self._alerted_at = 0.0
            logger.info(f"{self.name}Cookie已更新, 恢复查询", prefix)
            return False
        now = time.time()
        if now - self._alerted_at >= self.REMIND_INTERVAL:
            self._alerted_at = now
            logger.warning(f"{self.name}Cookie仍未更新, 查询保持挂起", prefix)
            notify(
                f"{self.name}查询已暂停",
                "Cookie仍未更新, 更新后自动恢复",
                on_click=self.on_click,
            )
        return True

    def count_failure(self, cookie, prefix):
        """累计连续失效次数，达到上限后挂起查询。

        返回本次是否刚进入挂起，调用方据此跳过一次退避。
        """
        self._streak += 1
        if self._streak < self.limit:
            return False
        self._streak = 0
        self._snapshot = dict(cookie or {})
        self._alerted_at = time.time()
        logger.warning(
            f"{self.name}Cookie连续失效{self.limit}次, 暂停查询, 等待Cookie更新", prefix
        )
        notify(
            f"{self.name}查询已暂停",
            f"Cookie连续失效{self.limit}次, 更新Cookie后自动恢复",
            on_click=self.on_click,
        )
        return True

    def reset(self):
        self._streak = 0


#: 抓取失败的环节，见 Fetch.kind
NETWORK = "network"
STATUS = "status"
PARSE = "parse"


@dataclass
class Fetch:
    """一次请求 + JSON 解析的结果。

    ok 为真时 data 是解析后的对象；否则 kind 指出失败环节：
    NETWORK（连接/超时）、STATUS（非 200）、PARSE（JSON 解析失败）。
    失败的日志文案与退避时长因平台而异，由调用方自行处理。
    """

    kind: str = ""
    data: object = None
    content: str = ""
    status: int = 0
    reason: str = ""
    error: object = None

    @property
    def ok(self):
        return not self.kind


def fetch_json(url, headers, cookie=None, data=None, timeout=10):
    """请求 url 并解析 JSON，只负责传输与解析，不含日志与退避。

    带 data 时走 POST，否则 GET。
    """
    kwargs = dict(headers=headers, cookies=cookie, proxies=proxies, timeout=timeout)
    try:
        if data is None:
            response = requests.get(url, **kwargs)
        else:
            response = requests.post(url, data=data, **kwargs)
    except RequestException as e:
        return Fetch(kind=NETWORK, error=e)
    content = response.content.decode("utf-8", errors="replace")
    if response.status_code != 200:
        return Fetch(
            kind=STATUS,
            content=content,
            status=response.status_code,
            reason=response.reason,
        )
    try:
        return Fetch(data=json.loads(response.text), content=content)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return Fetch(kind=PARSE, content=content, error=e)


#: 图片后缀白名单。URL 尾段命中其一才算"已带后缀"——
#: 不能只判"有没有点"：B 站图片 URL 带 `@` 尺寸后缀（如 `abc.jpg@1052w_1052h`），
#: 其 `Path(name).suffix` 是 `.jpg@1052w_1052h` 这种假后缀。
_IMAGE_EXTS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".svg"}
)


def get_icon(headers, image_url, prefix, platform, uname, _type):
    if not isinstance(image_url, str) or not image_url.strip():
        logger.debug(f"图片地址为空, 跳过下载, uname: {uname}, type: {_type}", prefix)
        return None
    url = image_url.split("?")[0].split("#")[0]
    name = url.split("/")[-1] or "image"
    if Path(name).suffix.lower() not in _IMAGE_EXTS:
        name += ".jpg"
    dir_path = Path("image") / platform / uname / _type
    dir_path.mkdir(parents=True, exist_ok=True)
    icon = str(dir_path / name)
    # 用 is_file 而非 exists：目录也满足 exists，URL 尾斜杠时会把目录当图片返回
    if isfile(icon):
        return realpath(icon)
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
    except RequestException as e:
        logger.warning(f"网络错误 error:{e}, url: {url} ", prefix)
        return None
    if r.status_code != 200:
        return None
    with open(icon, "wb") as f:
        f.write(r.content)
    return realpath(icon)


def check_diff(
    ori,
    _dict,
    info_name,
    uid,
    uname,
    prefix,
    color,
    on_click,
    icon_path,
    pic=None,
    image=None,
):
    if ori != _dict[uid]:
        msg = f"【{uname}】更改了{info_name}"
        if pic:
            content = ""
        else:
            content = f"【{_dict[uid]}】 -> 【{ori}】"
            msg += ": " + content

        logger.info(msg, prefix, color)

        notify(
            f"【{uname}】更改了{info_name}",
            content,
            icon=icon_path,
            on_click=on_click,
            pic_url=pic,
            image=image,
        )
        _dict[uid] = ori


def fmt_pics(pic_url):
    """把图片地址格式化成单行日志字段。

    None/空 -> "-"；列表/元组 -> 空格分隔；其它 -> 原样 str。
    用于统一各平台动态日志里的 url/pics 字段写法（避免 None 与列表 repr 噪声）。
    """
    if not pic_url:
        return "-"
    if isinstance(pic_url, (list, tuple)):
        return " ".join(str(i) for i in pic_url) or "-"
    return str(pic_url)


def get_image(pic_url, headers, prefix, platform, uname, _type):
    image = None
    opus_path = None
    if pic_url:
        if isinstance(pic_url, list):
            for url in reversed(pic_url):
                _path = get_icon(headers, url, prefix, platform, uname, _type)
                if _path:
                    opus_path = _path
        else:
            opus_path = get_icon(headers, pic_url, prefix, platform, uname, _type)
        if opus_path is None:
            logger.warning(f"图片下载失败, url: {pic_url}", prefix)
        else:
            image = {"src": opus_path, "placement": "hero"}
    return image
