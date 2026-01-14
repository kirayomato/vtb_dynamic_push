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

cookies_valid = False


def get_active(uid):
    time_threshold = time.time() - 7 * 24 * 3600
    return 1 + sum(1 for i in DYNAMIC_DICT[uid].values() if i[2] > time_threshold)


def format_re(text):
    # 匹配两个及以上连续换行符的位置
    # 用两个换行符加 '> ' 来替换
    result = re.sub(r"(\n{2,})", r"\n\n> ", text)
    return result


def query_valid(uid, cookie):
    query_url = (
        f"https://www.weibo.com/ajax/statuses/mymblog?uid={uid}&page=1&feature=0"
    )
    headers = get_headers(uid)
    try:
        response = requests.get(
            query_url, headers=headers, cookies=cookie, proxies=proxies, timeout=10
        )
        result = json.loads(str(response.content, "utf-8"))
        cards = result["data"]["list"]
        global cookies_valid
        for card in cards:
            if card["visible"]["type"] == 10:
                cookies_valid = True
                break
        return cookies_valid
    except:
        return True


def query_weibodynamic(uid, cookie, msg) -> bool:
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
        pic_url = card.get("pic_infos")
        if pic_url:
            return [i["largest"]["url"] for i in pic_url.values()]
        elif "page_info" in card:
            return card["page_info"].get("page_pic")
        return None

    def get_content(mblog):
        action = "微博更新"
        pic_url = get_pic(mblog)
        if mblog.get("text_raw"):
            content = mblog["text_raw"]
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
            if mblog["retweeted_status"].get("user"):
                origin_user = mblog["retweeted_status"]["user"]["screen_name"]
                content += f"\n\n转发**{origin_user}**的微博：\n> "
            else:
                content += "\n\n转发微博：\n> "
            if not pic_url:
                pic_url = get_pic(mblog["retweeted_status"])
            if mblog.get("text_raw"):
                retweeted_content = mblog["retweeted_status"]["text_raw"]
            else:
                retweeted_content = re.sub(
                    r"<[^>]+>", "", mblog["retweeted_status"]["text"]
                )
            content += format_re(retweeted_content)
        return content, pic_url, action

    if uid is None:
        return False
    query_url = (
        f"https://www.weibo.com/ajax/statuses/mymblog?uid={uid}&page=1&feature=0"
    )
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
        error_text = f"status:{response.status_code}, {response.reason} url: {query_url} \ncontent:{content}"
        if response.status_code == 403:
            logger.error(f"触发风控, 休眠五分钟, {error_text}", prefix)
            sleep(300)
        elif response.status_code == 432:
            logger.warning("微博Cookies无效", prefix)
            notify("微博Cookies无效", "", on_click="https://m.weibo.cn/")
            sleep(300)
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
                logger.warning("微博Cookies无效", prefix)
                notify("微博Cookies无效", "", on_click="https://m.weibo.cn/")
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
            for i in result["data"]["list"]
            if i["mblogtype"] == 0 and str(i["user"]["id"]) == uid
        ]
        if len(cards) == 0:
            if DYNAMIC_DICT.get(uid) is None:
                logger.debug(f"【{uid}】微博列表为空", prefix)
                DYNAMIC_DICT[uid] = {}
            return 1
        mblog = cards[0]
        user = mblog["user"]
        uname = user["screen_name"]
        face = user["profile_image_url"]
        face = face.split("?", 1)[0]
        # sign = user["description"]
        sign = ""
        total = result["data"]["total"]
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
    if DYNAMIC_DICT.get(uid) is None:
        DYNAMIC_DICT[uid] = {}
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        USER_NAME_DICT[uid] = uname
        USER_COUNT_DICT[uid] = total
        LAST_ID = cards[-1]["id"]
        for mblog in cards:
            mblog_id = mblog["id"]
            url = f"https://m.weibo.cn/detail/{mblog_id}"
            if mblog_id >= LAST_ID:
                created_at = datetime.strptime(
                    mblog["created_at"], "%a %b %d %H:%M:%S %z %Y"
                ).timestamp()
                content, pic_url, action = get_content(mblog)
                DYNAMIC_DICT[uid][mblog_id] = content, pic_url, created_at

        created_at = datetime.strptime(
            cards[-1]["created_at"], "%a %b %d %H:%M:%S %z %Y"
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

    cnt = 0
    for mblog in reversed(cards):
        mblog_id = mblog["id"]

        if mblog_id in DYNAMIC_DICT[uid] or mblog_id < min(DYNAMIC_DICT[uid]):
            continue

        created_at = datetime.strptime(
            mblog["created_at"], "%a %b %d %H:%M:%S +0800 %Y"
        )
        display_time = created_at.strftime("%Y-%m-%d %H:%M:%S")
        content, pic_url, action = get_content(mblog)
        url = f"https://m.weibo.cn/detail/{mblog_id}"

        if mblog_id < max(DYNAMIC_DICT[uid]):
            DYNAMIC_DICT[uid][mblog_id] = content, pic_url, created_at.timestamp()
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
        notify(
            f"【{uname}】{action}", content, on_click=url, image=image, icon=icon_path
        )
        DYNAMIC_DICT[uid][mblog_id] = content, pic_url, created_at.timestamp()
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTYELLOW_EX)

    _total = USER_COUNT_DICT[uid]
    USER_COUNT_DICT[uid] = total
    if total == _total + cnt:
        return get_active(uid)

    if total < _total + cnt:
        action = "删除了微博，但未能找到"
        # 尝试检测被删除的微博
        st = [card["id"] for card in cards]
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
                        f"【{uname}】删除微博：\n{content}，url: {url}",
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
    # headers["origin"] = "https://m.weibo.cn/"
    headers["referer"] = f"https://www.weibo.com/u/{uid}"
    headers["x-requested-with"] = "XMLHttpRequest"
    # headers["mweibo-pwa"] = "1"
    # headers["Sec-Ch-Ua-Mobile"] = "?1"
    # headers["Sec-Ch-Ua-Platform"] = "Android"
    # headers["User-Agent"] = (
    #     "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36 Edg/143.0.0.0"
    # )
    return headers
