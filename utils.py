import json
import os
from dataclasses import dataclass
from os import environ
from os.path import realpath, isfile
import re
import time
import requests
from requests.exceptions import RequestException
from urllib.parse import parse_qs, unquote, urlsplit
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

#: 图片文件头。只判状态码不够：200 也可能是风控/错误页，一旦落盘就会被
#: isfile 当成已下载而永远不再重试。本地 1.3w 张样本只有 jpeg/png/gif/webp，
#: 后缀白名单里其余格式也一并认下（avif 的 ftyp 盒在偏移 4）。
_IMAGE_MAGIC = (
    b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"BM", b"RIFF",
    b"<svg", b"<?xml",
)


def _is_image_content(data):
    return data.startswith(_IMAGE_MAGIC) or data[4:8] == b"ftyp"


#: 媒体落盘根目录。图片与视频共用一棵树，按 平台/昵称/用途 分层；
#: 视频落在 用途 为 video 的叶子目录下（如 image/weibo/昵称/video）。
#: 以本文件为基准，换工作目录启动也不会把图片视频写到别处。
MEDIA_ROOT = Path(__file__).resolve().parent / "image"


def get_icon(headers, image_url, prefix, platform, uname, _type):
    if not isinstance(image_url, str) or not image_url.strip():
        logger.debug(f"图片地址为空, 跳过下载, uname: {uname}, type: {_type}", prefix)
        return None
    url = image_url.split("?")[0].split("#")[0]
    name = url.split("/")[-1] or "image"
    if Path(name).suffix.lower() not in _IMAGE_EXTS:
        name += ".jpg"
    dir_path = Path(MEDIA_ROOT) / platform / uname / _type
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
    data = r.content
    if r.status_code != 200 or not _is_image_content(data):
        logger.warning(
            f"图片下载失败 status:{r.status_code}, type:{r.headers.get('Content-Type', '')}, url: {url}",
            prefix,
        )
        return None
    with open(icon, "wb") as f:
        f.write(data)
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


#: 视频后缀白名单。与图片分开维护：视频不能靠后缀不存在就补 .jpg。
_VIDEO_EXTS = frozenset({".mp4", ".mov", ".m4v", ".flv", ".ts", ".webm"})

#: 视频 URL 分片下载的块大小
_CHUNK_SIZE = 1 << 16


def _media_ext(url, exts, default):
    """从 URL 推断媒体后缀，推断不出时返回 default。

    微博实况照片的地址形如
    `https://video.weibo.com/media/play?livephoto=https%3A%2F%2F...mov`，
    真实后缀藏在 query 里而不是路径上，直接取 Path(url).suffix 只会得到空串。
    所以先看 query 里的候选路径，再看 URL 自身路径。
    """
    parts = urlsplit(url)
    candidates = [unquote(v) for v in parse_qs(parts.query).get("livephoto", [])]
    candidates.append(parts.path)
    for candidate in candidates:
        ext = Path(urlsplit(candidate).path).suffix.lower()
        if ext in exts:
            return ext
    return default


def _safe_name(name):
    """把 URL/pid 里的文件名片段收敛成合法文件名，避免路径穿越。"""
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", str(name or "")).strip("._")
    return name or "video"


def is_video_file(url):
    """URL 的路径部分是否带可保存的视频后缀。

    m3u8 分片清单不算：它需要另外合并分片，不能当单个文件直接下载。
    """
    if not isinstance(url, str) or not url.strip():
        return False
    return Path(urlsplit(url).path).suffix.lower() in _VIDEO_EXTS


def _download_stream(url, path, headers, prefix, timeout=60):
    """流式下载到 `<path>.part`，完整落盘后再原子改名。

    视频动辄几十上百 MB，不能像图片那样整块塞进内存；同时必须避免中断时
    留下半截文件——get_video 用 isfile 做重复下载短路，半截文件会被误认成
    已下载完成，之后永远拿不到完整视频。
    """
    tmp = f"{path}.part"
    try:
        r = requests.get(
            url, headers=headers, proxies=proxies, timeout=timeout, stream=True
        )
        ctype = r.headers.get("Content-Type", "")
        # 200 也可能是风控/错误页，落盘后被 isfile 当成已下载就再也不会重试
        if r.status_code != 200 or ctype.startswith("text/"):
            logger.warning(
                f"视频下载失败 status:{r.status_code}, type:{ctype}, url: {url}", prefix
            )
            return None
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        os.replace(tmp, path)
        return realpath(path)
    except RequestException as e:
        logger.warning(f"网络错误 error:{e}, url: {url}", prefix)
        return None
    except OSError as e:
        logger.warning(f"写入视频失败 error:{e}, path: {path}", prefix)
        return None
    finally:
        if isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def get_video(
    video_url,
    headers,
    prefix,
    platform,
    uname,
    _type="video",
    name=None,
    timeout=60,
):
    """下载视频到 image/<platform>/<uname>/<_type>/，返回本地绝对路径。

    与图片共用同一棵树（MEDIA_ROOT），靠叶子目录 video 区分，方便按博主
    一处翻看图片和视频。已存在同名文件时直接复用（只做一次 stat），
    重复轮询不会重复下载。
    name 用于指定基础文件名：实况照片的地址路径固定是 /media/play，
    只能靠调用方传入 pid 之类的唯一标识。
    """
    if not isinstance(video_url, str) or not video_url.strip():
        logger.debug(f"视频地址为空, 跳过下载, uname: {uname}, type: {_type}", prefix)
        return None
    url = video_url.strip()
    suffix = _media_ext(url, _VIDEO_EXTS, ".mp4")
    base = _safe_name(name or Path(urlsplit(url).path).stem)
    dir_path = Path(MEDIA_ROOT) / platform / uname / _type
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"{base}{suffix}"
    if isfile(path):
        return realpath(str(path))
    return _download_stream(url, path, headers, prefix, timeout)
