import json
import time
import requests
from requests.exceptions import RequestException
from push import notify
from logger import logger
from config import general_headers
from utils import check_diff, get_icon, get_image
from wbi import build_query, _update_wbi_key

# from PIL import Image
from colorama import Fore, Style
from os import environ
from datetime import datetime
import re
from functools import partial

environ["NO_PROXY"] = "*"
DYNAMIC_DICT = {}
LIVING_STATUS_DICT = {}
ROOM_TITLE_DICT = {}
ROOM_COVER_DICT = {}
USER_SIGN_DICT = {}
USER_FACE_DICT = {}
DYNAMIC_NAME_DICT = {}
LIVE_NAME_DICT = {}
WBI_KEY = None
proxies = {
    "http": "",
    "https": "",
}
cookies_failed_count = 0


def format_re(text):
    # 匹配两个及以上连续换行符的位置
    # 用两个换行符加 '> ' 来替换
    result = re.sub(r"(\n{2,})", r"\n\n> ", text)
    return result


def get_active(uid):
    time_threshold = time.time() - 7 * 24 * 3600
    return 1 + sum(1 for i in DYNAMIC_DICT[uid].values() if i[2] > time_threshold)


def query_bilidynamic(uid, cookie, msg) -> bool:
    def sleep(t):
        msg[0] = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " - "
            + Fore.LIGHTBLUE_EX
            + "休眠中"
            + Style.RESET_ALL
        )
        time.sleep(t)

    def deal_major(major):
        content = ""
        pic_url = None
        if not major:
            return "", None
        major_type = major.get("type")
        if major_type == "MAJOR_TYPE_OPUS":
            opus = major["opus"]
            if opus.get("title"):
                content += f"## {opus['title']}\n"
            content += opus["summary"]["text"]
            pic_url = opus.get("pics")
        elif major_type == "MAJOR_TYPE_ARCHIVE":
            archive = major["archive"]
            content = archive["title"]
            pic_url = archive.get("cover")
        elif major_type == "MAJOR_TYPE_PGC":
            pgc = major["pgc"]
            content = pgc["title"]
            pic_url = pgc.get("cover")
        elif major_type == "MAJOR_TYPE_LIVE_RCMD":
            live_rcmd = json.loads(major["live_rcmd"]["content"])
            live_info = live_rcmd.get("live_play_info", {})
            content = f"【{live_info.get('area_name')}】{live_info.get('title')}"
            pic_url = live_info.get("cover")
        elif major_type == "MAJOR_TYPE_LIVE":
            live = major["live"]
            content = f"【{live.get('desc_first')}】{live.get('title')}"
            pic_url = live.get("cover")
        elif major_type == "MAJOR_TYPE_NONE":
            content = "源动态已被作者删除"
        elif major_type == "MAJOR_TYPE_COMMON":
            common = major["common"]
            content = f"【{common.get('title')}】{common.get('desc')}"
            pic_url = common.get("cover")
        else:
            logger.error(f"无法识别的动态类型: {major_type}\n{major}", prefix)
            return "", None
        if isinstance(pic_url, list):
            pic_url = [i["url"] for i in pic_url]
        if not pic_url:
            pic_url = None
        return content, pic_url

    def get_content(item):
        """根据动态类型提取内容"""
        dynamic_type = item["type"]
        modules = item["modules"]
        module_dynamic = modules["module_dynamic"]

        DYNAMIC_TYPE_MAP = {
            "DYNAMIC_TYPE_DRAW": "动态更新",
            "DYNAMIC_TYPE_WORD": "动态更新",
            "DYNAMIC_TYPE_FORWARD": "转发动态",
            "DYNAMIC_TYPE_AV": "投稿视频",
            "DYNAMIC_TYPE_ARTICLE": "投稿专栏",
            "DYNAMIC_TYPE_PGC_UNION": "转发视频",
            "DYNAMIC_TYPE_LIVE_RCMD": "开播了",
            "DYNAMIC_TYPE_LIVE": "开播了",
            "DYNAMIC_TYPE_NONE": "原动态被删除",
            "DYNAMIC_TYPE_COMMON_SQUARE": "更换装扮",
        }

        if dynamic_type not in DYNAMIC_TYPE_MAP.keys():
            logger.error(f"无法识别的动态类型: {dynamic_type}", prefix)
        action = DYNAMIC_TYPE_MAP.get(dynamic_type)

        pic_url = None
        content = ""
        if dynamic_type in (
            "DYNAMIC_TYPE_LIVE_RCMD",
            "DYNAMIC_TYPE_LIVE",
            "DYNAMIC_TYPE_NONE",
            "DYNAMIC_TYPE_COMMON_SQUARE",
        ):
            return "", None, "skip"
        if dynamic_type == "DYNAMIC_TYPE_FORWARD":
            content = module_dynamic["desc"]["text"]
            # 尝试获取原始动态内容
            orig_item = item.get("orig", {})
            if orig_item:
                if orig_item.get("module_author"):
                    origin_user = orig_item["module_author"]["name"]
                    content += f"\n\n转发**{origin_user}**的动态：\n> "
                else:
                    content += "\n\n转发动态：\n> "
                ori_content, pic_url, _ = get_content(orig_item)
                content += format_re(ori_content)
            else:
                logger.error(f"原动态获取失败: {item}", prefix)
        else:
            major = module_dynamic.get("major", {})
            content, pic_url = deal_major(major)

        if not content:
            if item["basic"]["is_only_fans"]:
                content = "仅粉丝可见动态，获取内容失败"
            else:
                logger.error(f"无法获取动态内容: {item}", prefix)
        return content, pic_url, action

    def get_wbi_key():
        """获取WBI签名key，优先使用缓存"""
        global WBI_KEY
        if WBI_KEY is None:
            try:
                WBI_KEY = _update_wbi_key(general_headers, cookie)
                assert WBI_KEY is not None, "获取WBI签名key失败"
            except Exception as e:
                logger.error(f"获取WBI签名key失败: {e}", prefix)
                return None
        return WBI_KEY

    def refresh_wbi_key():
        """刷新WBI签名key"""
        global WBI_KEY
        WBI_KEY = None
        return get_wbi_key()

    prefix = "【查询B站动态】"
    if uid is None:
        return False
    uid = str(uid)

    # 获取WBI签名key（使用缓存）
    try:
        wbi_key = get_wbi_key()
    except Exception as e:
        logger.error(f"获取WBI签名key失败: {e}", prefix)
        sleep(60)
        return False

    # 构建请求参数
    ts = int(time.time())
    params = [
        ("host_mid", uid),
        ("offset", ""),
        ("timezone_offset", "-480"),
        ("platform", "web"),
        (
            "features",
            "itemOpusStyle,ClistOnlyfans,CopusBigCover,ConlyfansVote,CforwardListHidden,CdecorationCard,CcommentsNewVersion,ConlyfansAssetsV2,CugcDelete,ConlyfansQaCard,CavatarAutoTheme,CsunflowerStyle,CcardsEnhance,Ceva3CardOpus,Ceva3CardVideo,Ceva3CardComment,Ceva3CardUser",
        ),
        ("web_location", "0.0"),
        ("x-bili-device-req-json", '{"platform":"web","device":"pc","spmid":"0.0"}'),
    ]

    # 生成签名
    query_string = build_query(wbi_key, ts, params)
    query_url = (
        f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?{query_string}"
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
        error_text = (
            f"status:{response.status_code}, {response.reason} url: {query_url}"
        )
        if response.status_code == 429:
            logger.warning(f"触发风控, 休眠一分钟, {error_text}", prefix)
            sleep(60)
        elif response.status_code == 412:
            logger.error(f"触发风控, 休眠十分钟, {error_text}", prefix)
            sleep(600)
        else:
            logger.warning(f"请求错误, 休眠一分钟, {error_text}", prefix)
            sleep(60)
        return False
    try:
        result = json.loads(response.text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f"【{uid}】解析content出错:{e}, 休眠三分钟, url: {query_url} \ncontent:{content}",
            prefix,
        )
        sleep(180)
        return False
    if result["code"] != 0:
        if result["code"] == -101:
            logger.warning("B站Cookies无效", prefix)
            notify("B站Cookies无效", "", on_click="https://www.bilibili.com/")
        elif result["code"] == -352:
            # WBI签名失效，刷新key后重试
            logger.warning("WBI签名失效，正在刷新key", prefix)
            try:
                refresh_wbi_key()
            except Exception as e:
                logger.error(f"刷新WBI key失败: {e}", prefix)
                sleep(60)
            finally:
                return False
        else:
            logger.error(
                f'【{uid}】请求返回数据code错误:{result["code"]}, 休眠五分钟, msg:{result["message"]}, url: {query_url} \ndata:{result}',
                prefix,
            )
        sleep(300)
        return False
    try:
        items = result["data"]["items"]
        if len(items) == 0:
            if DYNAMIC_DICT.get(uid) is not None:
                logger.warning(f"{uid}】动态列表为空, url: {query_url}", prefix)
            return 1

        # 获取用户信息（从第一个动态获取）
        first_item = items[0]
        modules = first_item.get("modules", {})
        module_author = modules.get("module_author", {})
        uname = module_author.get("name", "")
        face = module_author.get("face", "")
        sign = module_author.get("sign", "")
        home_url = f"https://space.bilibili.com/{uid}"
    except (KeyError, TypeError):
        logger.error(
            f"【{uid}】返回数据不完整, 休眠五分钟, url: {query_url} \ndata:{result}",
            prefix,
        )
        global cookies_failed_count
        cookies_failed_count += 1
        if cookies_failed_count % 3 == 0:
            logger.warning("B站Cookies无效", prefix)
            notify("B站Cookies无效", "", on_click="https://www.bilibili.com/")
        else:
            cookies_failed_count = 0
        sleep(300)
        return False
    msg[0] = (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + " - "
        + Fore.LIGHTBLUE_EX
        + f"查询{uname}动态"
        + Style.RESET_ALL
    )
    if DYNAMIC_DICT.get(uid) is None:
        DYNAMIC_DICT[uid] = {}
        DYNAMIC_NAME_DICT[uid] = uname
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        for item in items:
            dynamic_id = item["id_str"]
            modules = item.get("modules", {})
            if (
                modules.get("module_tag", {})
                and modules["module_tag"].get("text") == "置顶"
            ):
                continue
            module_author = modules.get("module_author", {})
            timestamp = int(module_author.get("pub_ts", 0))
            url = f"https://t.bilibili.com/{dynamic_id}"
            content, pic_url, action = get_content(item)
            if not content:
                if action == "skip":
                    continue
                else:
                    logger.error(
                        f"【{uname}】动态解析错误:\n {item}",
                        prefix,
                    )
            DYNAMIC_DICT[uid][dynamic_id] = content, pic_url, timestamp
        logger.info(
            f"【{uname}】动态初始化,len={len(DYNAMIC_DICT[uid])}",
            prefix,
            Fore.LIGHTBLUE_EX,
        )
        logger.debug(
            f"【{uname}】动态初始化 {DYNAMIC_DICT[uid]}", prefix, Fore.LIGHTBLUE_EX
        )
        return get_active(uid)
    icon_path = get_icon(headers, face, prefix, "bili", uname, "face")

    chk_diff = partial(
        check_diff,
        uid=uid,
        uname=uname,
        prefix=prefix,
        color=Fore.LIGHTBLUE_EX,
        on_click=home_url,
        icon_path=icon_path,
    )
    chk_diff(face, USER_FACE_DICT, "B站头像", pic=face)
    chk_diff(sign, USER_SIGN_DICT, "B站签名")
    chk_diff(uname, DYNAMIC_NAME_DICT, "B站昵称")

    last_id = min(DYNAMIC_DICT[uid])
    for item in reversed(items):
        dynamic_id = item["id_str"]
        if dynamic_id in DYNAMIC_DICT[uid] or dynamic_id < last_id:
            continue

        modules = item.get("modules", {})
        if (
            modules.get("module_tag", {})
            and modules["module_tag"].get("text") == "置顶"
        ):
            continue
        module_author = modules.get("module_author", {})
        timestamp = int(module_author.get("pub_ts", 0))
        dynamic_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

        content, pic_url, action = get_content(item)
        if not content:
            if action == "skip":
                continue
            else:
                logger.error(
                    f"【{uname}】动态解析错误:\n {item}",
                    prefix,
                )
        url = f"https://t.bilibili.com/{dynamic_id}"

        image = get_image(pic_url, headers, prefix, "bili", uname, "dynamic")

        logger.info(
            f"【{uname}】{action} {dynamic_time}：\n{content}, url: {url}",
            prefix,
            Fore.LIGHTBLUE_EX,
        )
        notify(
            f"【{uname}】{action}",
            content,
            on_click=url,
            image=image,
            icon=icon_path,
            pic_url=pic_url,
        )
        DYNAMIC_DICT[uid][dynamic_id] = content, pic_url, timestamp
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTBLUE_EX)

    # 检测删除动态
    st = set([item["id_str"] for item in items])
    last_id = items[-1]["id_str"]
    del_list = []
    for _id in DYNAMIC_DICT[uid]:
        if _id >= last_id and _id not in st:
            content, pic_url, timestamp = DYNAMIC_DICT[uid][_id]
            image = get_image(pic_url, headers, prefix, "bili", uname, "dynamic")

            url = f"https://t.bilibili.com/{_id}"
            logger.info(
                f"【{uname}】删除动态: \n{content}，url: {url}\nimage list:{pic_url}",
                prefix,
                Fore.LIGHTBLUE_EX,
            )
            notify(
                f"【{uname}】删除动态",
                content,
                on_click=url,
                image=image,
                icon=icon_path,
                pic_url=pic_url,
            )
            del_list.append(_id)

    for _id in del_list:
        del DYNAMIC_DICT[uid][_id]
    return get_active(uid)


# 此方法已废弃
# def query_live_status(uid=None):
#     if uid is None:
#         return
#     uid = str(uid)
#     query_url = 'http://api.bilibili.com/x/space/acc/info?mid={}&my_ts={}'.format(
#         uid, int(time.time()))
#     headers = get_headers(uid)
#     response = requests.get(
#         query_url, '查询直播状态', headers=headers, timeout=10)
#     if util.check_response_is_ok(response):
#         result = json.loads(response.text)
#         if result['code'] != 0:
#             logger.error('请求返回数据code错误：{code}'.format(
#                 code=result['code']), prefix)
#         else:
#             name = result['data']['name']
#             try:
#                 live_status = result['data']['live_room']['liveStatus']
#             except (KeyError, TypeError):
#                 logger.error('【{uid}】获取不到liveStatus'.format(uid=uid), prefix)
#                 return

#             if LIVING_STATUS_DICT.get(uid) is None:
#                 LIVING_STATUS_DICT[uid] = live_status
#                 logger.info(Fore.LIGHTBLUE_EX+'【{uname}】初始化'.format(uname=name), prefix)
#                 return

#             if LIVING_STATUS_DICT.get(uid) != live_status:
#                 LIVING_STATUS_DICT[uid] = live_status

#                 room_id = result['data']['live_room']['roomid']
#                 room_title = result['data']['live_room']['title']
#                 room_cover_url = result['data']['live_room']['cover']

#                 if live_status == 1:
#                     logger.info(Fore.LIGHTGREEN_EX+'【{name}】开播了,准备推送：{room_title}'.format(
#                         name=name, room_title=room_title), prefix)
#                     push.push_for_bili_live(
#                         name, room_id, room_title, room_cover_url)


def query_live_status_batch(uid_list, cookie, msg, special):
    prefix = "【查询B站直播】"

    def sleep(t):
        msg[2] = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " - "
            + Fore.LIGHTBLUE_EX
            + "休眠中"
            + Style.RESET_ALL
        )
        time.sleep(t)

    if uid_list is None or len(uid_list) == 0:
        return
    query_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"
    headers = get_headers(list(uid_list)[0])
    data = json.dumps({"uids": list(map(int, uid_list))})
    try:
        response = requests.post(
            query_url, headers=headers, data=data, cookies=cookie, timeout=10
        )
    except RequestException as e:
        logger.warning(f"网络错误, error:{e}, 休眠一分钟, url: {query_url} ", prefix)
        sleep(60)
        return
    content = response.content.decode("utf-8", errors="replace")
    if response.status_code != 200:
        logger.warning(
            f"请求错误 status:{response.status_code}, 休眠一分钟, url: {query_url}",
            prefix,
        )
        sleep(60)
        return
    try:
        result = json.loads(response.text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f"解析content出错:{e}, 休眠一分钟, url: {query_url} \ncontent:{content}",
            prefix,
        )
        sleep(60)
        return
    if result["code"] != 0:
        logger.error(
            f'请求返回数据code错误：{result["code"]}, 休眠一分钟, url: {query_url} \ndata:{result}',
            prefix,
        )
        sleep(60)
    else:
        live_status_list = result["data"]
        if not hasattr(live_status_list, "items"):
            logger.error(
                f"返回数据不完整, 休眠一分钟, url: {query_url} \ndata:{result}", prefix
            )
            sleep(60)
            return
        for uid, item_info in live_status_list.items():
            try:
                uname = item_info["uname"]
                area = item_info["area_v2_name"]
                LIVE_NAME_DICT[uid] = uname
                face = item_info["face"]
                live_status = item_info["live_status"]
                room_id = item_info["room_id"]
                room_title = item_info["title"]
                room_cover_url = item_info["cover_from_user"]
                keyframe = item_info["keyframe"]
            except (KeyError, TypeError):
                logger.error(
                    f"【{uid}】返回数据不完整, 休眠一分钟, url: {query_url} \ndata:{item_info}",
                    prefix,
                )
                sleep(60)
                return
            live_url = f"https://live.bilibili.com/{room_id}"
            msg[2] = (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + " - "
                + Fore.CYAN
                + f"查询{uname}直播状态"
                + Style.RESET_ALL
            )
            if LIVING_STATUS_DICT.get(uid) is None:
                ROOM_TITLE_DICT[uid] = room_title
                LIVING_STATUS_DICT[uid] = live_status
                if room_cover_url == "":
                    room_cover_url = keyframe
                ROOM_COVER_DICT[uid] = room_cover_url
                if live_status == 1:
                    logger.info(f"【{uname}】【{area}】【{room_title}】直播中", prefix)
                else:
                    logger.info(
                        f"【{uname}】【{area}】【{room_title}】未开播",
                        prefix,
                        Fore.CYAN,
                    )
                continue

            icon_path = get_icon(headers, face, prefix, "bili", uname, "face")

            image = get_image(room_cover_url, headers, prefix, "bili", uname, "cover")

            chk_diff = partial(
                check_diff,
                uid=uid,
                uname=uname,
                prefix=prefix,
                color=Fore.CYAN,
                on_click=live_url,
                icon_path=icon_path,
            )
            chk_diff(room_title, ROOM_TITLE_DICT, "直播间标题")

            if room_cover_url:
                chk_diff(
                    room_cover_url,
                    ROOM_COVER_DICT,
                    "直播间封面",
                    pic=room_cover_url,
                    image=image,
                )

            if LIVING_STATUS_DICT[uid] != live_status:
                if live_status == 1:
                    logger.info(
                        f"【{uname}】【{area}】【{room_title}】开播了, url: {live_url}",
                        prefix,
                    )
                    if uid in special:
                        audio = {
                            "src": "ms-winsoundevent:Notification.Looping.Alarm",
                            "loop": "true",
                        }
                    else:
                        audio = None
                    notify(
                        f"【{uname}】开播了",
                        f"【{area}】" + room_title,
                        on_click=live_url,
                        audio=audio,
                        image=image,
                        icon=icon_path,
                        pic_url=room_cover_url,
                    )
                else:
                    logger.info(f"【{uname}】下播了", prefix, Fore.CYAN)
                LIVING_STATUS_DICT[uid] = live_status
            elif live_status == 1:
                logger.debug(
                    f"【{uname}】【{area}】【{room_title}】直播中", prefix, Fore.GREEN
                )
            else:
                logger.debug(
                    f"【{uname}】【{area}】【{room_title}】未开播", prefix, Fore.CYAN
                )


def get_headers(uid):
    headers = general_headers.copy()
    headers["origin"] = "https://www.bilibili.com/"
    headers["referer"] = f"https://space.bilibili.com/{uid}/dynamic"
    headers["Dnt"] = "1"
    headers["sec-fetch-site"] = "same-site"
    headers["sec-fetch-mode"] = "cors"
    headers["sec-fetch-dest"] = "empty"
    return headers
