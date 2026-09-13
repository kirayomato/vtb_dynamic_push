from datetime import datetime
from functools import partial
import json
import re
import time
from push import notify
from logger import logger
import requests
from requests.exceptions import RequestException
from config import general_headers
from utils import check_diff, get_icon, get_image
from storage import dyn_del, dyn_load, dyn_set, dyn_set_many, kv_load, kv_set

# from PIL import Image
from colorama import Fore, Style
from os import environ

environ["NO_PROXY"] = "*"
DYNAMIC_DICT = {}
USER_FACE_DICT = {}
USER_SIGN_DICT = {}
USER_NAME_DICT = {}
USER_COUNT_DICT = {}
proxies = {
    "http": "",
    "https": "",
}
prefix = "【查询微博状态】"

_prefix = "【微博持久化】"

#: 本进程内已完成"特别关注图片兜底"的用户，避免每个轮询周期重复扫描。
#: 进程重启后自动清空，从而重新兜底（与持久化前"每次启动都重新拉取"的语义一致）。
_SPECIAL_BACKFILLED = set()


def init_state():
    """从本地数据库恢复上次运行的状态，避免重新初始化。

    由 main.py 在启动查询线程前显式调用，不在 import 期执行，
    避免导入本模块就产生建库、连库等副作用。
    """
    try:
        loaded = dyn_load("weibo")
        for uid, items in loaded.items():
            DYNAMIC_DICT[uid] = items
        for store, target in (
            ("weibo.name", USER_NAME_DICT),
            ("weibo.face", USER_FACE_DICT),
            ("weibo.sign", USER_SIGN_DICT),
            ("weibo.count", USER_COUNT_DICT),
        ):
            target.update(kv_load(store))
        logger.info(
            f"已从本地数据库恢复微博状态: 用户{len(DYNAMIC_DICT)}个/"
            f"{sum(len(v) for v in DYNAMIC_DICT.values())}条微博",
            _prefix,
            Fore.LIGHTYELLOW_EX,
        )
    except Exception as e:
        logger.error(f"恢复微博持久化状态失败: {e}", _prefix)


def _save_user_info(uid):
    kv_set("weibo.name", uid, USER_NAME_DICT.get(uid))
    kv_set("weibo.face", uid, USER_FACE_DICT.get(uid))
    kv_set("weibo.sign", uid, USER_SIGN_DICT.get(uid))


cookies_valid = False


def get_active(uid):
    time_threshold = time.time() - 30 * 24 * 3600
    return 1 + sum(1 for i in DYNAMIC_DICT[uid].values() if i[2] > time_threshold)


def format_re(text):
    # 匹配两个及以上连续换行符的位置
    # 用两个换行符加 '> ' 来替换
    result = re.sub(r"(\n{2,})", r"\n\n> ", text)
    return result


def query_valid(uid, cookie):
    query_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25"
    headers = get_headers(uid)
    global cookies_valid
    cookies_valid = False
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
        result = json.loads(response.text)
        cards = result["data"]["cards"]
        for card in cards:
            if card["mblog"]["visible"]["type"] == 10:
                cookies_valid = True
                break
        return cookies_valid
    except:
        return True


def query_weibodynamic(uid, cookie, msg, special) -> bool:
    def sleep(t):
        msg[1] = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " - "
            + Fore.LIGHTYELLOW_EX
            + "休眠中"
            + Style.RESET_ALL
        )
        time.sleep(t)

    def get_pic(card):
        pic_url = card.get("pics")
        if pic_url:
            return [i["large"]["url"] for i in pic_url]
        elif "page_info" in card:
            return card["page_info"]["page_pic"]["url"]
        return None

    def get_content(mblog):
        action = "微博更新"
        pic_url = get_pic(mblog)
        if mblog.get("raw_text"):
            content = mblog["raw_text"]
        else:
            content = re.sub(r"<[^>]+>", "", mblog["text"])

        if "retweeted_status" in mblog:
            action = "转发微博"
            if mblog["retweeted_status"].get("user"):
                origin_user = mblog["retweeted_status"]["user"]["screen_name"]
                content += f"\n\n转发**{origin_user}**的微博：\n> "
            else:
                content += "\n\n转发微博：\n> "
            if not pic_url:
                pic_url = get_pic(mblog["retweeted_status"])
            content += format_re(
                re.sub(r"<[^>]+>", "", mblog["retweeted_status"]["text"])
            )
        return content, pic_url, action

    if uid is None:
        return False
    query_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25"
    headers = get_headers(uid)
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
    except RequestException as e:
        logger.warning(f"网络错误, error:{e}, 休眠一分钟, url: {query_url} ", prefix)
        sleep(60)
        return False
    content = response.content.decode("utf-8", errors="replace")
    if response.status_code != 200:
        error_text = (
            f"status:{response.status_code}, {response.reason} url: {query_url}"
        )
        if response.status_code == 403:
            logger.error(f"触发风控, 休眠五分钟, {error_text}", prefix)
            sleep(300)
        elif response.status_code == 432:
            global cookies_valid
            cookies_valid = False
            logger.warning("微博Cookie无效", prefix)
            notify("微博Cookie无效", "", on_click="https://m.weibo.cn/")
            sleep(600)
        else:
            logger.warning(f"请求错误, 休眠一分钟, {error_text}", prefix)
            sleep(60)
        return False
    try:
        result = json.loads(response.text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f"【{uid}】解析content出错:{e}, 休眠一分钟, url: {query_url} \ncontent:{content}",
            prefix,
        )
        sleep(60)
        return False
    if result["ok"] not in (0, 1):
        if result["ok"] == -100:
            if "passport.weibo.com" in result["url"]:
                logger.warning("微博Cookie无效", prefix)
                notify("微博Cookie无效", "", on_click="https://m.weibo.cn/")
            else:
                logger.error(
                    f'触发风控，请完成验证码校验, 休眠五分钟\n{result["url"]} , url: {query_url} \ndata:{result}',
                    prefix,
                )
                notify("触发微博风控", "请完成验证码校验", on_click=result["url"])
        else:
            logger.error(
                f'【{uid}】请求返回数据code错误:{result["ok"]}, 休眠五分钟, msg:{result["msg"]}, url: {query_url} \ndata:{result}',
                prefix,
            )
        sleep(300)
        return False
    try:
        cards = [
            i
            for i in result["data"]["cards"]
            if i["card_type"] == 9 and i["mblog"]["user"]["id"] == int(uid)
        ]
        if len(cards) == 0:
            if DYNAMIC_DICT.get(uid):
                logger.warning("微博Cookie无效", prefix)
                notify("微博Cookie无效", "", on_click="https://m.weibo.cn/")
                sleep(300)
            else:
                logger.debug(f"【{uid}】微博列表为空", prefix)
                DYNAMIC_DICT[uid] = {}
            return 1
        card = cards[0]
        mblog = card["mblog"]
        user = mblog["user"]
        uname = user["screen_name"]
        face = user["profile_image_url"]
        face = face.split("?", 1)[0]
        sign = user["description"]
        total = result["data"]["cardlistInfo"]["total"]
        home_url = f"https://m.weibo.cn/profile/{uid}"
    except KeyError:
        logger.error(
            f"【{uid}】返回数据不完整, 休眠一分钟, url: {query_url} \ndata:{result}",
            prefix,
        )
        sleep(60)
        return False
    msg[1] = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + " - "
        + Fore.LIGHTYELLOW_EX
        + f"查询{uname}微博"
        + Style.RESET_ALL
    )
    # 特别关注图片兜底：持久化后 DYNAMIC_DICT 由数据库恢复，初始化分支
    # 不再每次启动都执行，导致"特别关注保存所有图片"只生效一次。此处在本进程
    # 首次查询该用户时统一兜底：把当前 feed 内全部图片落盘。get_icon 内部有
    # 文件存在性短路，重复执行只做廉价 stat，不会重复下载。
    if uid in special and uid not in _SPECIAL_BACKFILLED:
        _SPECIAL_BACKFILLED.add(uid)
        weibo_last = cards[-1]["mblog"]["id"]
        for card in cards:
            mblog = card["mblog"]
            if mblog["id"] >= weibo_last:
                _content, pic_url, _action = get_content(mblog)
                if pic_url:
                    get_image(pic_url, headers, prefix, "weibo", uname, "dynamic")
    if not DYNAMIC_DICT.get(uid):
        DYNAMIC_DICT[uid] = {}
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        USER_NAME_DICT[uid] = uname
        USER_COUNT_DICT[uid] = total
        kv_set("weibo.count", uid, total)
        LAST_ID = cards[-1]["mblog"]["id"]
        for card in cards:
            mblog = card["mblog"]
            mblog_id = mblog["id"]
            url = card["scheme"]
            if mblog_id >= LAST_ID:
                created_at = datetime.strptime(
                    mblog["created_at"], "%a %b %d %H:%M:%S +0800 %Y"
                ).timestamp()
                content, pic_url, action = get_content(mblog)
                # 存时间戳而非datetime对象，保证可持久化且get_active可比较
                DYNAMIC_DICT[uid][mblog_id] = content, pic_url, created_at

        _save_user_info(uid)
        dyn_set_many("weibo", uid, DYNAMIC_DICT[uid])
        created_at = datetime.strptime(
            cards[-1]["mblog"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
        )
        display_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            f"【{uname}】微博初始化, len={len(DYNAMIC_DICT[uid])}, last: {display_time}",
            prefix,
            Fore.LIGHTYELLOW_EX,
        )
        logger.debug(
            f"【{uname}】微博初始化 {DYNAMIC_DICT[uid]}", prefix, Fore.LIGHTYELLOW_EX
        )
        return get_active(uid)

    icon_path = get_icon(headers, face, prefix, "weibo", uname, "face")

    chk_diff = partial(
        check_diff,
        uid=uid,
        uname=uname,
        prefix=prefix,
        color=Fore.LIGHTYELLOW_EX,
        on_click=home_url,
        icon_path=icon_path,
    )
    chk_diff(face, USER_FACE_DICT, "微博头像", pic=face)
    chk_diff(sign, USER_SIGN_DICT, "微博签名")
    chk_diff(uname, USER_NAME_DICT, "微博昵称")
    _save_user_info(uid)

    cnt = 0
    max_id = max(DYNAMIC_DICT[uid])
    min_id = min(DYNAMIC_DICT[uid])
    notified = False
    new_count = 0
    # cards 按时间倒序(最新在前)：扫描到每条新微博就地下载图片+打日志（与改动前一致），
    # 仅对第一条新微博(即最新)触发 notify，其余只入库不推送
    for card in cards:
        mblog = card["mblog"]
        mblog_id = mblog["id"]

        if mblog_id in DYNAMIC_DICT[uid] or mblog_id < min_id:
            continue

        created_at = datetime.strptime(
            mblog["created_at"], "%a %b %d %H:%M:%S +0800 %Y"
        )
        display_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        content, pic_url, action = get_content(mblog)
        url = card["scheme"]

        if mblog_id < max_id:
            # 比已记录的最新微博更旧，仅作为历史入库，不推送也不计入 cnt
            DYNAMIC_DICT[uid][mblog_id] = content, pic_url, created_at.timestamp()
            dyn_set("weibo", uid, mblog_id, content, pic_url, created_at.timestamp())
            logger.info(
                f"【{uname}】历史微博，不进行推送({total}) {display_time}: \n{content}，url: {url}",
                prefix,
                Fore.LIGHTYELLOW_EX,
            )
            continue
        if action in ["微博更新", "转发微博"]:
            cnt += 1
        image = get_image(pic_url, headers, prefix, "weibo", uname, "dynamic")
        logger.info(
            f"【{uname}】{action}({total}) {display_time}: \n{content}，url: {url}",
            prefix,
            Fore.LIGHTYELLOW_EX,
        )
        if not notified:
            notify(
                f"【{uname}】{action}",
                content,
                on_click=url,
                image=image,
                icon=icon_path,
                pic_url=pic_url,
            )
            notified = True
        new_count += 1
        DYNAMIC_DICT[uid][mblog_id] = content, pic_url, created_at.timestamp()
        dyn_set("weibo", uid, mblog_id, content, pic_url, created_at.timestamp())
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTYELLOW_EX)
    if new_count > 1:
        logger.info(
            f"【{uname}】本次共新增 {new_count} 条微博，仅推送最新一条",
            prefix,
            Fore.LIGHTYELLOW_EX,
        )

    _total = USER_COUNT_DICT[uid]
    USER_COUNT_DICT[uid] = total
    kv_set("weibo.count", uid, total)
    if total == _total + cnt:
        return get_active(uid)

    if total < _total + cnt:
        action = "删除了微博，但未能找到"
        # 尝试检测被删除的微博
        st = [card["mblog"]["id"] for card in cards]
        last_id = st[-1]
        st = set(st)
        del_list = []
        # cookies失效时不进行检测
        if cookies_valid:
            for _id in DYNAMIC_DICT[uid]:
                if _id >= last_id and _id not in st:
                    cnt -= 1
                    del_list.append(_id)
                    content, pic_url, timestamp = DYNAMIC_DICT[uid][_id]
                    url = f"https://m.weibo.cn/detail/{_id}"

                    image = get_image(
                        pic_url, headers, prefix, "weibo", uname, "dynamic"
                    )

                    logger.info(
                        f"【{uname}】删除微博：\n{content}，url: {url}\nimage list:{pic_url}",
                        prefix,
                        Fore.LIGHTYELLOW_EX,
                    )
                    notify(
                        f"【{uname}】删除微博",
                        content,
                        on_click=url,
                        image=image,
                        icon=icon_path,
                        pic_url=pic_url,
                    )
            for _id in del_list:
                del DYNAMIC_DICT[uid][_id]
                dyn_del("weibo", uid, _id)
        if total == _total + cnt:
            return get_active(uid)
        elif total > _total + cnt:
            action = "检测到微博被隐藏"
    else:
        action = "发布了微博，但未能抓取"
    logger.info(
        f"【{uname}】{action}：{_total} -> {total}", prefix, Fore.LIGHTYELLOW_EX
    )
    notify(
        f"【{uname}】{action}",
        f"{_total} -> {total}",
        icon=icon_path,
        on_click=f"https://m.weibo.cn/profile/{uid}",
    )
    return get_active(uid)


def get_headers(uid):
    headers = general_headers.copy()
    headers["origin"] = "https://m.weibo.cn/"
    headers["referer"] = f"https://m.weibo.cn/u/{uid}"
    headers["mweibo-pwa"] = "1"
    headers["x-requested-with"] = "XMLHttpRequest"
    headers["Sec-Ch-Ua-Mobile"] = "?1"
    headers["Sec-Ch-Ua-Platform"] = "Android"
    headers["User-Agent"] = (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36 Edg/143.0.0.0"
    )
    return headers
