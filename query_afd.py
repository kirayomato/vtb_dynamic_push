from datetime import datetime
import json
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
AFD_NAME_DICT = {}
REAL_ID_DICR = {}
USER_COUNT_DICT = {}
DEL_COUNT_DICT = {}
proxies = {
    "http": "",
    "https": "",
}
prefix = "【查询爱发电】"


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
        logger.warning(f"网络错误 error:{e}, url:{face}", "【下载爱发电图片】")
        return None
    if r.status_code != 200:
        return None
    with open(icon, "wb") as f:
        f.write(r.content)
    # img = Image.open(icon)
    # img = img.resize((64, 64))
    # img.save(f'icon/{uid}.ico')
    return realpath(icon)


def get_realid(uid):
    if uid is None:
        return
    if REAL_ID_DICR.get(uid) is not None:
        return REAL_ID_DICR[uid]
    try:
        query_url = f"https://afdian.com/api/user/get-profile-by-slug?url_slug={uid}"
        headers = get_headers(uid)
        response = requests.get(query_url, headers=headers, proxies=proxies, timeout=10)
        result = json.loads(str(response.content, "utf-8"))
        REAL_ID_DICR[uid] = result["data"]["user"]["user_id"]
        return REAL_ID_DICR[uid]
    except BaseException as e:
        logger.warning(f"获取真实UID失败:{e}, url: {query_url} ,休眠一分钟", prefix)
        return None


def query_afddynamic(uid, cookie, msg):
    def sleep(t):
        msg[3] = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " - "
            + Fore.LIGHTCYAN_EX
            + "休眠中"
            + Style.RESET_ALL
        )
        time.sleep(t)

    def get_pic(card):
        pic_url = card["pics"]
        if len(pic_url):
            return pic_url[0]
        return None

    def get_content(mblog):
        action = "爱发电更新"
        pic_url = get_pic(mblog)
        content = mblog["title"]
        dynamic_time = mblog["publish_time"]
        return content, pic_url, action, dynamic_time

    real_uid = get_realid(uid)
    if uid is None:
        return

    query_url = f"https://afdian.com/api/post/get-list?user_id={real_uid}&type=old&publish_sn=&per_page=10&group_id=&all=1&is_public=&plan_id=&title=&name="
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
    if result["ec"] != 200:
        logger.error(
            f'【{uid}】请求返回数据code错误:{result["ec"]}, msg:{result["em"]}, url: {query_url} ,休眠五分钟\ndata:{result}',
            prefix,
        )
        sleep(300)
        return
    try:
        cards = [i for i in result["data"]["list"]]
        if len(cards) == 0:
            if DYNAMIC_DICT.get(uid) is None:
                logger.debug(f"【{uid}】爱发电列表为空", prefix)
            return
        mblog = cards[0]
        user = mblog["user"]
        uname = user["name"]
        face = user["avatar"]
        sign = user["creator"]["doing"]
        home_url = f"https://afdian.com/a/{user['url_slug']}"
    except KeyError:
        logger.error(
            f"【{uid}】返回数据不完整, url: {query_url} ,休眠一分钟\ndata:{result}",
            prefix,
        )
        sleep(60)
        return
    msg[3] = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + " - "
        + Fore.LIGHTCYAN_EX
        + f"查询{uname}爱发电"
        + Style.RESET_ALL
    )
    if DYNAMIC_DICT.get(uid) is None:
        DYNAMIC_DICT[uid] = {}
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        AFD_NAME_DICT[uid] = uname
        for mblog in cards:
            mblog_id = mblog["post_id"]
            content, pic_url, action, dynamic_time = get_content(mblog)
            DYNAMIC_DICT[uid][mblog_id] = content, pic_url, home_url, dynamic_time

        created_at = datetime.fromtimestamp(cards[-1]["publish_time"])
        dynamic_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            f"【{uname}】爱发电初始化, len={len(DYNAMIC_DICT[uid])}, last: {dynamic_time}",
            prefix,
            Fore.LIGHTCYAN_EX,
        )
        logger.debug(
            f"【{uname}】爱发电初始化 {DYNAMIC_DICT[uid]}", prefix, Fore.LIGHTCYAN_EX
        )
        return

    icon_path = get_icon(uid, face)
    if face != USER_FACE_DICT[uid]:
        logger.info(f"【{uname}】更改了爱发电头像", prefix, Fore.LIGHTCYAN_EX)
        notify(
            f"【{uname}】更改了爱发电头像",
            "",
            icon=icon_path,
            on_click=home_url,
        )
        USER_FACE_DICT[uid] = face
    if sign != USER_SIGN_DICT[uid]:
        logger.info(
            f"【{uname}】更改了爱发电签名：【{USER_SIGN_DICT[uid]}】 -> 【{sign}】",
            prefix,
            Fore.LIGHTCYAN_EX,
        )
        notify(
            f"【{uname}】更改了爱发电签名",
            f"【{USER_SIGN_DICT[uid]}】 -> 【{sign}】",
            icon=icon_path,
            on_click=home_url,
        )
        USER_SIGN_DICT[uid] = sign

    for card in reversed(cards):
        dynamic_id = card["post_id"]
        if dynamic_id in DYNAMIC_DICT[uid]:
            continue

        content, pic_url, action, dynamic_time = get_content(card)
        created_at = datetime.fromtimestamp(dynamic_time)
        display_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        image = None
        if pic_url:
            opus_path = get_icon(uid, pic_url, "opus/")
            if opus_path is None:
                logger.warning(f"【{uname}】图片下载失败, url: {pic_url}", prefix)
            else:
                image = {"src": opus_path, "placement": "hero"}
        logger.info(
            f"【{uname}】{action} {display_time}：{content}, url: {home_url}",
            prefix,
            Fore.LIGHTCYAN_EX,
        )
        notify(
            f"【{uname}】{action}",
            content,
            on_click=home_url,
            image=image,
            icon=icon_path,
            pic_url=pic_url,
        )
        DYNAMIC_DICT[uid][dynamic_id] = content, pic_url, action, dynamic_time
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTCYAN_EX)

    # 检测删除动态
    st = set([card["post_id"] for card in cards])
    del_list = []
    last_time = min([card["publish_time"] for card in cards])
    for _id in DYNAMIC_DICT[uid]:
        if _id not in st and DYNAMIC_DICT[uid][_id][3] > last_time:
            del_list.append(_id)
            content, pic_url, action = DYNAMIC_DICT[uid][_id]
            image = None
            if pic_url:
                opus_path = get_icon(uid, pic_url, "opus/")
                if opus_path:
                    image = {"src": opus_path, "placement": "hero"}
            logger.info(
                f"【{uname}】删除动态: {content}，url: {home_url}",
                prefix,
                Fore.LIGHTCYAN_EX,
            )
            notify(
                f"【{uname}】删除动态",
                content,
                on_click=home_url,
                image=image,
                icon=icon_path,
                pic_url=pic_url,
            )
    for _id in del_list:
        del DYNAMIC_DICT[uid][_id]


def get_headers(uid):
    headers = general_headers.copy()
    headers["origin"] = "https://afdian.com/"
    headers["referer"] = f"https://afdian.com/a/{uid}"
    return headers
