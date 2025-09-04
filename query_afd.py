from datetime import datetime
from functools import partial
import json
from random import random
import time
from push import notify
from logger import logger
import requests
from requests.exceptions import RequestException
from config import general_headers
from utils import check_diff

# from PIL import Image
from colorama import Fore, Style
from os import environ


environ["NO_PROXY"] = "*"
DYNAMIC_DICT = {}
PLAN_DICT = {}
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


def query_afddynamic(uid, cookie, msg, intervals_second):
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
        if pic_url := card.get("pics"):
            return pic_url
        elif cover := card.get("cover"):
            return cover
        return None

    def get_content(mblog):
        action = "爱发电更新"
        pic_url = get_pic(mblog)
        content = mblog["title"]
        dynamic_time = mblog["publish_time"]
        return content, pic_url, action, dynamic_time

    real_uid = get_realid(uid)
    if real_uid is None:
        sleep(60)
        return

    query_url = f"https://afdian.com/api/post/get-list?user_id={real_uid}&type=old&publish_sn=&per_page=10&group_id=&all=1&is_public=&plan_id=&title=&name="
    headers = get_headers(uid)
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
    except RequestException as e:
        logger.warning(f"网络错误 error:{e}, url: {query_url} ,休眠三分钟", prefix)
        sleep(180)
        return
    if response.status_code != 200:
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
            DYNAMIC_DICT[uid][mblog_id] = content, pic_url, dynamic_time

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

    icon_path = None

    chk_diff = partial(
        check_diff,
        uid=uid,
        uname=uname,
        prefix=prefix,
        color=Fore.LIGHTCYAN_EX,
        on_click=home_url,
        icon_path=icon_path,
    )
    chk_diff(face, USER_FACE_DICT, "爱发电头像", True, pic=face)
    chk_diff(sign, USER_SIGN_DICT, "爱发电签名", False)
    chk_diff(uname, AFD_NAME_DICT, "爱发电昵称", False)

    for card in reversed(cards):
        dynamic_id = card["post_id"]
        if dynamic_id in DYNAMIC_DICT[uid]:
            continue

        content, pic_url, action, dynamic_time = get_content(card)
        created_at = datetime.fromtimestamp(dynamic_time)
        display_time = created_at.strftime("%Y-%m-%d %H:%M:%S")

        image = None

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
        DYNAMIC_DICT[uid][dynamic_id] = content, pic_url, dynamic_time
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTCYAN_EX)

    # 检测删除动态
    st = set([card["post_id"] for card in cards])
    del_list = []
    last_time = min([card["publish_time"] for card in cards])
    for _id in DYNAMIC_DICT[uid]:
        if _id not in st and DYNAMIC_DICT[uid][_id][2] > last_time:
            del_list.append(_id)
            content, pic_url, dynamic_time = DYNAMIC_DICT[uid][_id]

            image = None

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
    sleep(max(1, intervals_second) * (1 + random() / 10))
    query_afdplan(sleep, headers, cookie, uid, uname, real_uid, home_url, icon_path)


def query_afdplan(sleep, headers, cookie, uid, uname, real_uid, home_url, icon_path):
    def get_plan_content(mblog):
        action = "爱发电计划更新"
        pic_url = mblog["pic"]
        content = f'【{mblog["name"]}】:{mblog["desc"]}'
        dynamic_time = mblog["update_time"]
        return content, pic_url, action, dynamic_time

    query_url = f"https://afdian.com/api/creator/get-plans?user_id={real_uid}&album_id=&unlock_plan_ids=&diy=&affiliate_code="
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
    except RequestException as e:
        logger.warning(f"网络错误 error:{e}, url: {query_url} ,休眠三分钟", prefix)
        sleep(180)
        return
    if response.status_code != 200:
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
        cards = [i for i in result["data"]["list"] + result["data"]["sale_list"]]
        if len(cards) == 0:
            if DYNAMIC_DICT.get(uid) is None:
                logger.debug(f"【{uid}】爱发电列表为空", prefix)
            return
    except KeyError:
        logger.error(
            f"【{uid}】返回数据不完整, url: {query_url} ,休眠一分钟\ndata:{result}",
            prefix,
        )
        sleep(60)
        return

    if PLAN_DICT.get(uid) is None:
        PLAN_DICT[uid] = {}
        for mblog in cards:
            mblog_id = mblog["plan_id"]
            content, pic_url, action, dynamic_time = get_plan_content(mblog)
            PLAN_DICT[uid][mblog_id] = content, pic_url

        logger.info(
            f"【{uname}】爱发电计划初始化, len={len(PLAN_DICT[uid])}",
            prefix,
            Fore.LIGHTCYAN_EX,
        )
        logger.debug(
            f"【{uname}】爱发电计划初始化 {PLAN_DICT[uid]}", prefix, Fore.LIGHTCYAN_EX
        )
        return

    for card in reversed(cards):
        plan_id = card["plan_id"]
        if plan_id in PLAN_DICT[uid]:
            continue

        content, pic_url, action, dynamic_time = get_plan_content(card)
        created_at = datetime.fromtimestamp(dynamic_time)
        display_time = created_at.strftime("%Y-%m-%d %H:%M:%S")

        image = None

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
        PLAN_DICT[uid][plan_id] = content, pic_url
        logger.debug(str(PLAN_DICT[uid]), prefix, Fore.LIGHTCYAN_EX)

    # 检测删除计划
    st = set([card["plan_id"] for card in cards])
    del_list = []
    for _id in PLAN_DICT[uid]:
        if _id not in st:
            del_list.append(_id)
            content, pic_url = PLAN_DICT[uid][_id]

            image = None

            logger.info(
                f"【{uname}】删除计划: {content}，url: {home_url}",
                prefix,
                Fore.LIGHTCYAN_EX,
            )
            notify(
                f"【{uname}】删除计划",
                content,
                on_click=home_url,
                image=image,
                icon=icon_path,
                pic_url=pic_url,
            )
    for _id in del_list:
        del PLAN_DICT[uid][_id]


def get_headers(uid):
    headers = general_headers.copy()
    headers["origin"] = "https://afdian.com/"
    headers["referer"] = f"https://afdian.com/a/{uid}"
    return headers
