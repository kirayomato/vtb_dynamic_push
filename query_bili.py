import json
import time
import requests
from requests.exceptions import RequestException
from collections import deque
from push import notify
from logger import logger
# from PIL import Image
from os.path import realpath, exists
from colorama import Fore, Style
from os import environ
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


def try_cookies(cookies=None):
    uid = '1932862336'
    query_url = f'http://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history?host_uid={uid}&offset_dynamic_id=0&need_top=0&platform=web&my_ts={int(time.time())}'
    headers = get_headers(uid)
    try:
        response = requests.get(
            query_url, cookies=cookies, headers=headers, proxies=proxies, timeout=10)
        result = json.loads(str(response.content, "utf-8"))
        if response.status_code == 200:
            return result['data']['cards'] is not None
        else:
            return True
    except:
        return True


def query_bilidynamic(uid, cookie, msg):
    def sleep(t):
        msg[0] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
            Fore.LIGHTBLUE_EX + '休眠中' + Style.RESET_ALL
        time.sleep(t)
    prefix = '【查询动态状态】'
    if uid is None:
        return
    uid = str(uid)
    query_url = f'http://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history?host_uid={uid}&offset_dynamic_id=0&need_top=0&platform=web'
    headers = get_headers(uid)
    try:
        response = requests.get(query_url, headers=headers,
                                cookies=cookie, proxies=proxies, timeout=10)
    except RequestException as e:
        logger.warning(f'网络错误 url:{query_url}, error:{e}, 休眠一分钟', prefix)
        sleep(60)
        return
    if response.status_code != 200:
        if response.status_code == 429:
            return
        if response.status_code == 412:
            logger.warning(
                f'触发风控 url:{query_url}, status:{response.status_code}, {response.reason}, 休眠五分钟', prefix)
            sleep(300)
        else:
            logger.warning(
                f'请求错误 url:{query_url}, status:{response.status_code}, {response.reason}, 休眠一分钟', prefix)
            sleep(60)
        return
    try:
        result = json.loads(str(response.content, "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f'【{uid}】解析content出错:{e}, url:{query_url}, 休眠三分钟, content:\n{str(response.content, "utf-8")}', prefix)
        sleep(180)
        return
    if result['code'] != 0:
        logger.error(
            f'【{uid}】请求返回数据code错误:{result["code"]}, url:{query_url}, msg:{result["message"]}, 休眠五分钟', prefix)
        sleep(300)
        return
    data = result['data']
    try:
        if len(data['cards']) == 0:
            if DYNAMIC_DICT.get(uid, None) is not None:
                logger.warning(f'{uid}】动态列表为空', prefix)
            return
        item = data['cards'][0]
        dynamic_id = item['desc']['dynamic_id']
        uname = item['desc']['user_profile']['info']['uname']
        face = item['desc']['user_profile']['info']['face']
        sign = item['desc']['user_profile']['sign']
    except (KeyError, TypeError):
        logger.error(
            f'【{uid}】返回数据不完整,url:{query_url}, 休眠三分钟\ndata:{data}', prefix)
        sleep(180)
        return
    msg[0] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
        Fore.LIGHTBLUE_EX+f'查询{uname}动态' + Style.RESET_ALL
    if DYNAMIC_DICT.get(uid, None) is None:
        DYNAMIC_DICT[uid] = deque(maxlen=LEN_OF_DEQUE)
        DYNAMIC_NAME_DICT[uid] = uname
        USER_FACE_DICT[uid] = face
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
    logger.debug(f'【{uname}】上一条动态id[{DYNAMIC_DICT[uid][-1]}],本条动态id[{dynamic_id}]',
                 prefix, Fore.LIGHTBLUE_EX)
    icon_path = None
    if face != USER_FACE_DICT[uid]:
        logger.info(f'【{uname}】更改了头像', prefix, Fore.LIGHTBLUE_EX)
        notify(f'【{uname}】更改了头像', '', icon=icon_path,
               on_click=f'https://space.bilibili.com/{uid}', pic_url=face,
               )
        USER_FACE_DICT[uid] = face
    if sign != USER_SIGN_DICT[uid]:
        logger.info(f'【{uname}】更改了签名：【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
                    prefix, Fore.LIGHTBLUE_EX)
        notify(f'【{uname}】更改了签名', f'【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
               icon=icon_path,
               on_click=f'https://space.bilibili.com/{uid}'
               )
        USER_SIGN_DICT[uid] = sign
    if dynamic_id not in DYNAMIC_DICT[uid]:
        dynamic_type = item['desc']['type']
        # if dynamic_type not in [2, 4, 8, 64]:
        #     logger.info(Fore.LIGHTBLUE_EX+
        #         '【{uname}】动态有更新,但不在需要推送的动态类型列表中'.format(uname=uname))
        #     return

        timestamp = item['desc']['timestamp']
        dynamic_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        card_str = item['card']
        card = json.loads(card_str)
        content = None
        pic_url = None
        action = '动态更新'
        if dynamic_type == 1:
            # 转发动态
            action = '转发动态'
            content = card['item']['content']
            try:
                origin = json.loads(card['origin'])
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                origin = card['origin']
                logger.warning(
                    f'【{uid}】源动态解析出错:{e}, url:{query_url}, content:\n{origin}', prefix)
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
            action = '发布投稿'
            content = card['title']
            pic_url = card['pic']
        elif dynamic_type == 64:
            # 专栏动态
            action = '发布投稿'
            content = card['title']
            pic_url = card['image_urls'][0]
        url = f'https://www.bilibili.com/opus/{dynamic_id}'
        image = None
        logger.info(f'【{uname}】{dynamic_time}：{action} {content}, url:{url}',
                    prefix, Fore.LIGHTBLUE_EX)
        notify(f"【{uname}】{action}", content,
               on_click=url, image=image,
               icon=icon_path, pic_url=pic_url)
        DYNAMIC_DICT[uid].append(dynamic_id)
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTBLUE_EX)


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
#         result = json.loads(str(response.content, "utf-8"))
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
#                     logger.info(Fore.LIGHTGREEN_EX+'【{name}】开播了,准备推送：{room_title}'.format(
#                         name=name, room_title=room_title), prefix)
#                     push.push_for_bili_live(
#                         name, room_id, room_title, room_cover_url)


def query_live_status_batch(uid_list, cookie, msg, special):
    prefix = '【查询直播状态】'

    def sleep(t):
        msg[2] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
            Fore.LIGHTBLUE_EX + '休眠中' + Style.RESET_ALL
        time.sleep(t)
    if uid_list is None or len(uid_list) == 0:
        return
    query_url = 'https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids'
    headers = get_headers(list(uid_list)[0])
    data = json.dumps({"uids": list(map(int, uid_list))})
    try:
        response = requests.post(
            query_url, headers=headers, data=data, cookies=cookie, timeout=10)
    except RequestException as e:
        logger.warning(f'网络错误 url:{query_url}, error:{e}, 休眠一分钟', prefix)
        sleep(60)
        return
    if response.status_code != 200:
        logger.warning(
            f'请求错误 url:{query_url} status:{response.status_code}, 休眠一分钟', prefix)
        sleep(60)
        return
    try:
        result = json.loads(str(response.content, "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f'解析content出错:{e}, url:{query_url}, 休眠一分钟, content:\n{str(response.content, "utf-8")}', prefix)
        sleep(60)
        return
    if result['code'] != 0:
        logger.error(f'请求返回数据code错误：{result["code"]}, 休眠一分钟', prefix)
        sleep(60)
    else:
        live_status_list = result['data']
        if not hasattr(live_status_list, 'items'):
            logger.error('返回数据不完整, 休眠一分钟', prefix)
            sleep(60)
            return
        for uid, item_info in live_status_list.items():
            try:
                uname = item_info['uname']
                LIVE_NAME_DICT[uid] = uname
                # face = item_info['face']
                live_status = item_info['live_status']
                room_id = item_info['room_id']
                room_title = item_info['title']
                room_cover_url = item_info['cover_from_user']
                keyframe = item_info['keyframe']
            except (KeyError, TypeError):
                logger.error(f'【{uid}】返回数据不完整, 休眠一分钟', prefix)
                sleep(60)
                return
            url = f'https://live.bilibili.com/{room_id}'
            msg[2] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
                Fore.CYAN+f'查询{uname}直播状态' + Style.RESET_ALL
            if LIVING_STATUS_DICT.get(uid, None) is None:
                ROOM_TITLE_DICT[uid] = room_title
                LIVING_STATUS_DICT[uid] = live_status
                if room_cover_url == '':
                    room_cover_url = keyframe
                ROOM_COVER_DICT[uid] = room_cover_url
                if live_status == 1:
                    logger.info(f'【{uname}】【{room_title}】直播中', prefix)
                else:
                    logger.info(f'【{uname}】【{room_title}】未开播', prefix,
                                Fore.CYAN)
                continue
            icon_path = None
            image = None
            if ROOM_TITLE_DICT[uid] != room_title:
                logger.info(f'【{uname}】更改了直播间标题：【{ROOM_TITLE_DICT[uid]}】 -> 【{room_title}】',
                            prefix, Fore.CYAN)
                notify(f'【{uname}】更改了直播间标题', f'【{ROOM_TITLE_DICT[uid]}】->【{room_title}】',
                       icon=icon_path, on_click=url)
                ROOM_TITLE_DICT[uid] = room_title
            if ROOM_COVER_DICT[uid] != room_cover_url and room_cover_url != '':
                logger.info(f'【{uname}】更改了直播间封面', prefix, Fore.CYAN)
                notify(f'【{uname}】更改了直播间封面', '', on_click=url,
                       image=image, icon=icon_path, pic_url=room_cover_url)
                ROOM_COVER_DICT[uid] = room_cover_url
            if LIVING_STATUS_DICT[uid] != live_status:
                if live_status == 1:
                    logger.info(f'【{uname}】【{room_title}】开播了',
                                prefix)
                    if uid in special:
                        audio = {
                            'src': 'ms-winsoundevent:Notification.Looping.Alarm',
                            'loop': 'true'
                        }
                    else:
                        audio = None
                    notify(f"【{uname}】开播了", room_title,
                           on_click=url, audio=audio,
                           image=image, icon=icon_path,
                           pic_url=room_cover_url)
                else:
                    logger.info(f'【{uname}】下播了', prefix, Fore.CYAN)
                LIVING_STATUS_DICT[uid] = live_status
            elif live_status == 1:
                logger.debug(f'【{uname}】【{room_title}】直播中', prefix,
                             Fore.GREEN)
            else:
                logger.debug(f'【{uname}】【{room_title}】未开播', prefix,
                             Fore.CYAN)


def get_headers(uid):
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-encoding': 'utf-8, gzip, deflate, zstd',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'max-age=0',
        'origin': 'https://space.bilibili.com/',
        'pragma': 'no-cache',
        'referer': f'https://space.bilibili.com/{uid}/dynamic',
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }
