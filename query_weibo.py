from datetime import datetime, date
import json
import re
import time
from push import notify
from logger import logger
import requests
from requests.exceptions import RequestException
from config import general_headers

# from PIL import Image
from os.path import realpath, exists
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

cookies_valid = False


def get_icon(uid, face, path=""):
    headers = get_headers(uid)
    face = face.split("?")[0]
    name = face.split("/")[-1]
    icon = f"icon/{path}{name}"
    if exists(icon):
        return realpath(icon)
    try:
        r = requests.get(face, headers=headers, proxies=proxies, timeout=10)
    except RequestException as e:
        logger.warning(f"网络错误 error:{e}, url:{face}", "【下载微博图片】")
        return None
    if r.status_code != 200:
        return None
    with open(icon, "wb") as f:
        f.write(r.content)
    # img = Image.open(icon)
    # img = img.resize((64, 64))
    # img.save(f'icon/{uid}.ico')
    return realpath(icon)


def query_valid(uid, cookie):
    query_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25"
    headers = get_headers(uid)
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
        result = json.loads(str(response.content, "utf-8"))
        cards = result["data"]["cards"]
        global cookies_valid
        for card in cards:
            if card["mblog"]["visible"]["type"] == 10:
                cookies_valid = True
                break
        return cookies_valid
    except:
        return True


def query_weibodynamic(uid, cookie, msg):
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
        pic_url = card.get("original_pic")
        if pic_url:
            return pic_url
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
        if mblog.get("action_info"):
            for act, val in mblog["action_info"].items():
                action = act
                val = mblog["action_info"][act]["list"][0]
                content = val["text"]
                break
        if "retweeted_status" in mblog:
            action = "转发微博"
            content += "\n转发微博：【"
            if not pic_url:
                pic_url = get_pic(mblog["retweeted_status"])
                content += re.sub(r"<[^>]+>", "", mblog["retweeted_status"]["text"])
            content += "】"
        return content, pic_url, action

    if uid is None:
        return
    query_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25"
    headers = get_headers(uid)
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
    except RequestException as e:
        logger.warning(f"网络错误 error:{e}, url: {query_url} ,休眠一分钟", prefix)
        sleep(60)
        return
    if response.status_code != 200:
        if response.status_code == 403:
            logger.warning(
                f'触发风控 status:{response.status_code}, msg:{response.reason}, url: {query_url} ,休眠五分钟\ncontent:{str(response.content, "utf-8")}',
                prefix,
            )
            sleep(300)
        else:
            logger.warning(
                f'请求错误 status:{response.status_code}, msg:{response.reason}, url: {query_url} ,休眠一分钟\ncontent:{str(response.content, "utf-8")}',
                prefix,
            )
            sleep(60)
        return
    try:
        result = json.loads(str(response.content, "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f'【{uid}】解析content出错:{e}, url: {query_url} ,休眠一分钟\ncontent:{str(response.content, "utf-8")}',
            prefix,
        )
        sleep(60)
        return
    if result["ok"] not in (0, 1):
        if result["ok"] == -100:
            logger.error(
                f'触发风控，请完成验证码校验: {result["url"]} , url: {query_url} ,休眠五分钟\ndata:{result}',
                prefix,
            )
            notify("触发微博风控", "请完成验证码校验", on_click=result["url"])
        else:
            logger.error(
                f'【{uid}】请求返回数据code错误:{result["ok"]}, msg:{result["msg"]}, url: {query_url} ,休眠五分钟\ndata:{result}',
                prefix,
            )
        sleep(300)
        return
    try:
        cards = [i for i in result["data"]["cards"] if i["card_type"] == 9]
        if len(cards) == 0:
            if DYNAMIC_DICT.get(uid) is None:
                logger.debug(f"【{uid}】微博列表为空", prefix)
            return
        card = cards[0]
        mblog = card["mblog"]
        user = mblog["user"]
        uname = user["screen_name"]
        face = user["profile_image_url"]
        face = face[: face.find("?")]
        sign = user["description"]
        total = result["data"]["cardlistInfo"]["total"]
    except KeyError:
        logger.error(
            f"【{uid}】返回数据不完整, url: {query_url} ,休眠一分钟\ndata:{result}",
            prefix,
        )
        sleep(60)
        return
    msg[1] = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + " - "
        + Fore.LIGHTYELLOW_EX
        + f"查询{uname}微博"
        + Style.RESET_ALL
    )
    if DYNAMIC_DICT.get(uid) is None:
        DYNAMIC_DICT[uid] = {}
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        USER_NAME_DICT[uid] = uname
        USER_COUNT_DICT[uid] = total
        LAST_ID = cards[-1]["mblog"]["id"]
        for card in cards:
            mblog = card["mblog"]
            mblog_id = mblog["id"]
            url = card["scheme"]
            if mblog_id >= LAST_ID:
                content, pic_url, action = get_content(mblog)
                DYNAMIC_DICT[uid][mblog_id] = content, pic_url, url

        created_at = datetime.strptime(
            cards[-1]["mblog"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
        )
        dynamic_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            f"【{uname}】微博初始化, len={len(DYNAMIC_DICT[uid])}, last: {dynamic_time}",
            prefix,
            Fore.LIGHTYELLOW_EX,
        )
        logger.debug(
            f"【{uname}】微博初始化 {DYNAMIC_DICT[uid]}", prefix, Fore.LIGHTYELLOW_EX
        )
        return

    icon_path = get_icon(uid, face)
    if face != USER_FACE_DICT[uid]:
        logger.info(f"【{uname}】更改了微博头像", prefix, Fore.LIGHTYELLOW_EX)
        notify(
            f"【{uname}】更改了微博头像",
            "",
            icon=icon_path,
            on_click=f"https://m.weibo.cn/profile/{uid}",
        )
        USER_FACE_DICT[uid] = face
    if sign != USER_SIGN_DICT[uid]:
        logger.info(
            f"【{uname}】更改了微博签名：【{USER_SIGN_DICT[uid]}】 -> 【{sign}】",
            prefix,
            Fore.LIGHTYELLOW_EX,
        )
        notify(
            f"【{uname}】更改了微博签名",
            f"【{USER_SIGN_DICT[uid]}】 -> 【{sign}】",
            icon=icon_path,
            on_click=f"https://m.weibo.cn/profile/{uid}",
        )
        USER_SIGN_DICT[uid] = sign

    cnt = 0
    for card in reversed(cards):
        mblog = card["mblog"]
        mblog_id = mblog["id"]

        if mblog_id in DYNAMIC_DICT[uid] or mblog_id < min(DYNAMIC_DICT[uid]):
            continue

        created_at = datetime.strptime(
            mblog["created_at"], "%a %b %d %H:%M:%S +0800 %Y"
        )
        dynamic_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.combine(date.today(), datetime.min.time())
        content, pic_url, action = get_content(mblog)
        url = card["scheme"]

        if mblog_id < max(DYNAMIC_DICT[uid]) or created_at < today:
            DYNAMIC_DICT[uid][mblog_id] = content, pic_url, url
            logger.debug(
                f"【{uname}】历史微博，不进行推送 {dynamic_time}: {content}，url: {url}",
                prefix,
                Fore.LIGHTYELLOW_EX,
            )
            return
        if action in ["微博更新", "转发微博"]:
            cnt += 1

        image = None
        if pic_url:
            opus_path = get_icon(uid, pic_url, "opus/")
            if opus_path is None:
                logger.warning(f"【{uname}】图片下载失败，url:{pic_url}", prefix)
            else:
                image = {"src": opus_path, "placement": "hero"}
        logger.info(
            f"【{uname}】{action}({total}) {dynamic_time}: {content}，url: {url}",
            prefix,
            Fore.LIGHTYELLOW_EX,
        )
        notify(
            f"【{uname}】{action}", content, on_click=url, image=image, icon=icon_path
        )
        DYNAMIC_DICT[uid][mblog_id] = content, pic_url, url
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTYELLOW_EX)

    _total = USER_COUNT_DICT[uid]
    USER_COUNT_DICT[uid] = total
    if total == _total + cnt:
        return

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
                    content, pic_url, url = DYNAMIC_DICT[uid][_id]
                    image = None
                    if pic_url:
                        opus_path = get_icon(uid, pic_url, "opus/")
                        if opus_path:
                            image = {"src": opus_path, "placement": "hero"}
                    logger.info(
                        f"【{uname}】删除微博：{content}，url: {url}",
                        prefix,
                        Fore.LIGHTYELLOW_EX,
                    )
                    notify(
                        f"【{uname}】删除微博",
                        content,
                        on_click=url,
                        image=image,
                        icon=icon_path,
                    )
            for _id in del_list:
                del DYNAMIC_DICT[uid][_id]
        if total == _total + cnt:
            return
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


def get_headers(uid):
    headers = general_headers.copy()
    headers["origin"] = "https://m.weibo.cn/"
    headers["referer"] = f"https://m.weibo.cn/u/{uid}"
    headers["mweibo-pwa"] = "1"
    headers["x-requested-with"] = "XMLHttpRequest"
    headers["Sec-Ch-Ua-Mobile"] = "?1"
    headers["Sec-Ch-Ua-Platform"] = "Android"
    return headers
