import json
import time
import requests
from requests.exceptions import RequestException
from collections import deque
from util import notify
from logger import logger
from push import push
# from PIL import Image
from os.path import realpath, exists
from colorama import Fore, Style
from os import environ
from random import choice
from datetime import datetime


environ['NO_PROXY'] = '*'
DYNAMIC_DICT = {}
LIVING_STATUS_DICT = {}
ROOM_TITLE_DICT = {}
ROOM_COVER_DICT = {}
USER_SIGN_DICT = {}
USER_FACE_DICT = {}
DYNAMIC_NAME_DICT = {}
LIVE_NAME_DICT = {}
LEN_OF_DEQUE = 20
proxies = {
    "http": "",
    "https": "",
}


def get_icon(uid, face, path=''):
    icon = f'icon/{path}bili_{uid}.jpg'
    try:
        r = requests.get(face, timeout=5)
    except RequestException as e:
        logger.error(f'请求错误 url:{face},error:{e}', '【下载B站图片】')
        return
    with open(icon, 'wb') as f:
        f.write(r.content)
    # img = Image.open(icon)
    # img = img.resize((64, 64))
    # img.save(f'icon/{uid}.ico')
    return realpath(icon)


def query_bilidynamic(uid, cookie, msg):
    prefix = '【查询动态状态】'
    if uid is None:
        return
    uid = str(uid)
    query_url = 'http://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history' \
                '?host_uid={uid}&offset_dynamic_id=0&need_top=0&platform=web&my_ts={my_ts}'.format(
                    uid=uid, my_ts=int(time.time()))
    headers = get_headers(uid)
    try:
        response = requests.get(query_url, headers=headers,
                                cookies=cookie, proxies=proxies, timeout=5)
    except RequestException as e:
        logger.error(f'请求错误 url:{query_url},error:{e}', prefix)
        return
    if response.status_code == 412:
        logger.error(f'status:{response.status_code}, 触发风控休眠五分钟', prefix)
        time.sleep(300)
        return
    elif response.status_code != 200:
        logger.error(
            f'请求错误 url:{query_url} status:{response.status_code}', prefix)
        return
    try:
        result = json.loads(str(response.content, 'utf-8'))
    except UnicodeDecodeError:
        logger.error(f'【{uid}】解析content出错', prefix)
        return
    if result['code'] != 0:
        logger.error(f'【{uid}】请求返回数据code错误：{result["code"]}', prefix)
        return
    data = result['data']
    try:
        if len(data['cards']) == 0:
            if DYNAMIC_DICT.get(uid, None) is not None:
                logger.warning(f'{uid}】动态列表为空', prefix)
            return
    except KeyError:
        logger.error(f'【{uid}】返回数据不全', prefix)
        return
    item = data['cards'][0]
    dynamic_id = item['desc']['dynamic_id']
    try:
        uname = item['desc']['user_profile']['info']['uname']
        face = item['desc']['user_profile']['info']['face']
        sign = item['desc']['user_profile']['sign']
    except KeyError:
        logger.error(f'【{uid}】获取不到用户信息', prefix)
        return
    msg[0] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
        Fore.LIGHTBLUE_EX+f'查询{uname}动态' + Style.RESET_ALL
    if DYNAMIC_DICT.get(uid, None) is None:
        DYNAMIC_DICT[uid] = deque(maxlen=LEN_OF_DEQUE)
        DYNAMIC_NAME_DICT[uid] = uname
        USER_FACE_DICT[uid] = face
        get_icon(uid, face)
        USER_SIGN_DICT[uid] = sign
        cards = data['cards']
        for index in range(LEN_OF_DEQUE):
            if index < len(cards):
                DYNAMIC_DICT[uid].appendleft(
                    cards[index]['desc']['dynamic_id'])
        logger.info(
            f'【{uname}】动态初始化,len = {len(DYNAMIC_DICT[uid])}', prefix, Fore.LIGHTBLUE_EX)
        logger.debug(
            f'【{uname}】动态初始化 {DYNAMIC_DICT[uid]}', prefix, Fore.LIGHTBLUE_EX)
        return
    logger.debug(f'【{uname}】上一条动态id[{DYNAMIC_DICT[uid][-1]}]，本条动态id[{dynamic_id}]',
                 prefix, Fore.LIGHTBLUE_EX)
    icon_path = realpath(f'icon/bili_{uid}.jpg')
    if face != USER_FACE_DICT[uid]:
        get_icon(uid, face)
        logger.info(f'【{uname}】修改了头像', prefix, Fore.LIGHTGREEN_EX)
        notify(f'【{uname}】修改了头像', '',
               icon=icon_path, on_click=f'https://space.bilibili.com/{uid}'
               )
        USER_FACE_DICT[uid] = face
    if sign != USER_SIGN_DICT[uid]:
        logger.info(f'【{uname}】修改了签名：【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
                    prefix, Fore.LIGHTGREEN_EX)
        notify(f'【{uname}】修改了签名', f'【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
               icon=icon_path,
               on_click=f'https://space.bilibili.com/{uid}'
               )
        USER_SIGN_DICT[uid] = sign
    if dynamic_id not in DYNAMIC_DICT[uid]:
        dynamic_type = item['desc']['type']
        # if dynamic_type not in [2, 4, 8, 64]:
        #     logger.info(Fore.LIGHTBLUE_EX+
        #         '【{uname}】动态有更新，但不在需要推送的动态类型列表中'.format(uname=uname))
        #     return

        timestamp = item['desc']['timestamp']
        dynamic_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        card_str = item['card']
        card = json.loads(card_str)
        content = None
        pic_url = None
        if dynamic_type == 1:
            # 转发动态
            content = card['item']['content']
            origin = json.loads(card['origin'])
            if 'videos' in origin:
                pic_url = origin['pic']
            elif 'item' in origin:
                if 'pictures' in origin['item']:
                    pic_url = origin['item']['pictures'][0]['img_src']
            elif 'title' in origin:
                pic_url = origin['image_urls'][0]
        elif dynamic_type == 2:
            # 图文动态
            content = card['item']['description']
            pic_url = card['item']['pictures'][0]['img_src']
        elif dynamic_type == 4:
            # 文字动态
            content = card['item']['content']
        elif dynamic_type == 8:
            # 投稿动态
            content = card['title']
            pic_url = card['pic']
        elif dynamic_type == 64:
            # 专栏动态
            content = card['title']
            pic_url = card['image_urls'][0]

        url = f'https://www.bilibili.com/opus/{dynamic_id}'
        logger.info(f'【{uname}】动态更新：{content}，url:{url}',
                    prefix, Fore.LIGHTGREEN_EX)
        if pic_url is None:
            notify(f"【{uname}】动态更新", content,
                   icon=icon_path, on_click=url)
        else:
            get_icon(uid, pic_url, 'opus/')
            opus_path = realpath(f'icon/opus/bili_{uid}.jpg')
            notify(f"【{uname}】动态更新", content,
                   on_click=url,
                   image={
                       'src': opus_path,
                       'placement': 'hero'
                   }, icon=icon_path)
        DYNAMIC_DICT[uid].append(dynamic_id)
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTBLUE_EX)
        push.push_for_bili_dynamic(
            uname, dynamic_id, content, pic_url, dynamic_type, dynamic_time)


# 此方法已废弃
# def query_live_status(uid=None):
#     if uid is None:
#         return
#     uid = str(uid)
#     query_url = 'http://api.bilibili.com/x/space/acc/info?mid={}&my_ts={}'.format(
#         uid, int(time.time()))
#     headers = get_headers(uid)
#     response = requests.get(
#         query_url, '查询直播状态', headers=headers, timeout=5)
#     if util.check_response_is_ok(response):
#         result = json.loads(str(response.content, 'utf-8'))
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

#             if LIVING_STATUS_DICT.get(uid, None) is None:
#                 LIVING_STATUS_DICT[uid] = live_status
#                 logger.info(Fore.LIGHTBLUE_EX+'【{uname}】初始化'.format(uname=name), prefix)
#                 return

#             if LIVING_STATUS_DICT.get(uid, None) != live_status:
#                 LIVING_STATUS_DICT[uid] = live_status

#                 room_id = result['data']['live_room']['roomid']
#                 room_title = result['data']['live_room']['title']
#                 room_cover_url = result['data']['live_room']['cover']

#                 if live_status == 1:
#                     logger.info(Fore.LIGHTGREEN_EX+'【{name}】开播了，准备推送：{room_title}'.format(
#                         name=name, room_title=room_title), prefix)
#                     push.push_for_bili_live(
#                         name, room_id, room_title, room_cover_url)


def query_live_status_batch(uid_list, cookie, msg, special):
    prefix = '【查询直播状态】'
    if uid_list is None:
        uid_list = []
    if len(uid_list) == 0:
        return
    query_url = 'https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids'
    headers = get_headers(list(uid_list)[0])
    data = json.dumps({
        "uids": list(map(int, uid_list))
    })
    try:
        response = requests.post(
            query_url, headers=headers, data=data, cookies=cookie, timeout=5)
    except RequestException as e:
        logger.error(f'请求错误 url:{query_url},error:{e}', prefix)
        return
    if response.status_code != 200:
        logger.error(
            f'请求错误 url:{query_url} status:{response.status_code}', prefix)
        return
    result = json.loads(str(response.content, 'utf-8'))
    if result['code'] != 0:
        logger.error(f'请求返回数据code错误：{result["code"]}', prefix)
    else:
        live_status_list = result['data']
        for uid, item_info in live_status_list.items():
            try:
                uname = item_info['uname']
                LIVE_NAME_DICT[uid] = uname
                face = item_info['face']
                live_status = item_info['live_status']
                room_id = item_info['room_id']
                room_title = item_info['title']
                room_cover_url = item_info['cover_from_user']
                keyframe = item_info['keyframe']
            except KeyError:
                logger.error(f'【{uid}】获取不到直播信息', prefix)
                continue
            url = f'https://live.bilibili.com/{room_id}'
            msg[2] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
                Fore.CYAN+f'查询{uname}直播状态' + Style.RESET_ALL
            if LIVING_STATUS_DICT.get(uid, None) is None:
                ROOM_TITLE_DICT[uid] = room_title
                LIVING_STATUS_DICT[uid] = live_status
                ROOM_COVER_DICT[uid] = room_cover_url
                get_icon(uid, face)
                if room_cover_url != '':
                    get_icon(uid, room_cover_url, 'cover/')
                elif keyframe != '':
                    get_icon(uid, keyframe, 'cover/')
                if live_status == 1:
                    logger.info(f'【{uname}】【{room_title}】直播中',
                                prefix, Fore.LIGHTGREEN_EX)
                else:
                    logger.info(f'【{uname}】【{room_title}】未开播',
                                prefix, Fore.CYAN)
                continue
            icon_path = realpath(f'icon/bili_{uid}.jpg')
            cover_path = realpath(f'icon/cover/bili_{uid}.jpg')
            if not exists(cover_path):
                cover_path = ""
            if ROOM_TITLE_DICT[uid] != room_title:
                logger.info(f'【{uname}】修改了直播间标题：【{ROOM_TITLE_DICT[uid]}】 -> 【{room_title}】',
                            prefix, Fore.LIGHTGREEN_EX)
                notify(f'【{uname}】修改了直播间标题', f'【{ROOM_TITLE_DICT[uid]}】->【{room_title}】',
                       icon=icon_path, on_click=url)
                ROOM_TITLE_DICT[uid] = room_title
            if ROOM_COVER_DICT[uid] != room_cover_url and room_cover_url != '':
                get_icon(uid, room_cover_url, 'cover/')
                logger.info(f'【{uname}】修改了直播间封面', prefix, Fore.LIGHTGREEN_EX)
                notify(f'【{uname}】修改了直播间封面', '', on_click=url,
                       image={
                           'src': cover_path,
                           'placement': 'hero'
                       }, icon=icon_path)
                ROOM_COVER_DICT[uid] = room_cover_url
            if LIVING_STATUS_DICT[uid] != live_status:
                LIVING_STATUS_DICT[uid] = live_status
                if live_status == 1:
                    logger.info(f'【{uname}】【{room_title}】开播了',
                                prefix, Fore.LIGHTGREEN_EX)
                    if uid in special:
                        notify(f"【{uname}】开播了", room_title,
                               on_click=url, scenario='alarm',
                               audio={
                                   'src': 'ms-winsoundevent:Notification.Looping.Alarm', 'loop': 'true'},
                               image={
                                   'src': cover_path,
                                   'placement': 'hero'
                               }, icon=icon_path)
                    else:
                        notify(f"【{uname}】开播了", room_title,
                               on_click=url,
                               image={
                                   'src': cover_path,
                                   'placement': 'hero'
                               }, icon=icon_path)
                    push.push_for_bili_live(
                        uname, room_id, room_title, room_cover_url)
                else:
                    logger.info(f'【{uname}】下播了', prefix, Fore.LIGHTGREEN_EX)
            elif live_status == 1:
                logger.debug(f'【{uname}】【{room_title}】直播中',
                             prefix, Fore.LIGHTGREEN_EX)
            else:
                logger.debug(f'【{uname}】【{room_title}】未开播',
                             prefix, Fore.CYAN)


def get_headers(uid):
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1664.3 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_2) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1309.0 Safari/537.17",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1664.3 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1944.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.1 Safari/537.36",
        "Mozilla/5.0 (Windows NT 4.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.3319.102 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2309.372 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2117.157 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1866.237 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2224.3 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.16 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.60 Safari/537.17",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.62 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.101 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1623.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.90 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1468.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1464.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1467.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.14 (KHTML, like Gecko) Chrome/24.0.1292.0 Safari/537.14",
        "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15",
        "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1500.55 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.2 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.17 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1667.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2226.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.4; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2214.93 Safari/537.36",
    ]
    return {
        'User-Agent': choice(USER_AGENTS),
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'no-cache',
        'cookie': 'l=v;',
        'origin': 'https://space.bilibili.com',
        'pragma': 'no-cache',
        'referer': 'https://space.bilibili.com/{}/dynamic'.format(uid),
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
    }
