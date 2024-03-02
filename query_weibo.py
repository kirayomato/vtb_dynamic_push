from datetime import datetime, timedelta
import json
import re
import time
from collections import deque
from util import notify0
from logger import logger
from push import push
import requests
from requests.exceptions import RequestException
# from PIL import Image
from os.path import realpath
from colorama import Fore, Style
from os import environ


environ['NO_PROXY'] = '*'
DYNAMIC_DICT = {}
USER_FACE_DICT = {}
USER_SIGN_DICT = {}
LEN_OF_DEQUE = 50
proxies = {
    "http": "",
    "https": "",
}


def get_icon(uid, face, path=''):
    headrs = {
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://weibo.com/',
        'Sec-Ch-Ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    }
    icon = f'icon/{path}wb_{uid}.jpg'
    try:
        r = requests.get(face, headers=headrs, timeout=5)
    except RequestException as e:
        logger.error(
            Fore.RED + f'【查询微博状态】请求错误 url:{face},error:{e}' + Style.RESET_ALL)
        return
    with open(icon, 'wb') as f:
        f.write(r.content)
    # img = Image.open(icon)
    # img = img.resize((64, 64))
    # img.save(f'icon/{uid}.ico')
    return realpath(icon)


def query_valid(uid, cookie):
    query_url = 'https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25'.format(
        uid=uid)
    headers = get_headers(uid)
    try:
        response = requests.get(query_url, headers=headers,
                                cookies=cookie, proxies=proxies, timeout=5)
    except RequestException as e:
        logger.error(
            Fore.RED + f'【查询微博状态】请求错误 url:{query_url},error:{e}' + Style.RESET_ALL)
        return True
    if response.status_code == 200:
        result = json.loads(str(response.content, 'utf-8'))
        cards = result['data']['cards']
        return len(cards) > 5
    else:
        logger.error(
            Fore.RED + f'【查询微博状态】请求错误 url:{query_url},status:{response.status_code}' + Style.RESET_ALL)
        return True


def query_weibodynamic(uid, cookie, msg):
    if uid is None:
        return
    query_url = 'https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25'.format(
        uid=uid)
    headers = get_headers(uid)
    try:
        response = requests.get(query_url, headers=headers,
                                cookies=cookie, proxies=proxies, timeout=5)
    except RequestException as e:
        logger.error(
            Fore.RED + f'【查询微博状态】请求错误 url:{query_url},error:{e},休眠一分钟' + Style.RESET_ALL)
        time.sleep(60)
        return False
    if response.status_code != 200:
        logger.error(
            Fore.RED+f'【查询微博状态】请求错误 url:{query_url} status:{response.status_code}'+Style.RESET_ALL)
        return
    result = json.loads(str(response.content, 'utf-8'))
    cards = result['data']['cards']
    n = len(cards)
    if n == 0:
        logger.debug(
            Fore.YELLOW + f'【查询微博状态】【{uid}】微博列表为空' + Style.RESET_ALL)
        return
    # 跳过置顶
    for i in range(n):
        card = cards[i]
        if card['card_type'] != 9 or card['mblog'].get('isTop', None) == 1 or card['mblog'].get('mblogtype', None) == 2:
            continue
        else:
            break
    mblog = card['mblog']
    mblog_id = mblog['id']
    user = mblog['user']
    uname = user['screen_name']
    face = user['profile_image_url']
    face = face[:face.find('?')]
    sign = user['description']
    msg[1] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
        Fore.LIGHTYELLOW_EX+f'【查询微博状态】查询{uname}微博' + Style.RESET_ALL
    if DYNAMIC_DICT.get(uid, None) is None:
        DYNAMIC_DICT[uid] = deque(maxlen=LEN_OF_DEQUE)
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        get_icon(uid, face)
        for index in range(LEN_OF_DEQUE):
            if index < len(cards):
                if cards[index]['card_type'] != 9:
                    continue
                DYNAMIC_DICT[uid].appendleft(cards[index]['mblog']['id'])
        logger.info(Fore.LIGHTYELLOW_EX +
                    f'【查询微博状态】【{uname}】微博初始化,len = {len(DYNAMIC_DICT[uid])}' + Style.RESET_ALL)
        logger.debug(Fore.LIGHTYELLOW_EX +
                     f'【查询微博状态】【{uname}】微博初始化 {DYNAMIC_DICT[uid]}' + Style.RESET_ALL)
        return
    logger.debug(Fore.LIGHTYELLOW_EX+'【查询微博状态】【{}】上一条微博id[{}]，本条微博id[{}]'.format(
        uname, DYNAMIC_DICT[uid][-1], mblog_id) + Style.RESET_ALL)
    icon_path = realpath(f'icon/wb_{uid}.jpg')
    if face != USER_FACE_DICT[uid]:
        get_icon(uid, face)
        logger.info(Fore.LIGHTGREEN_EX +
                    f'【查询微博状态】【{uname}】修改了头像' + Style.RESET_ALL)
        notify0(f'【{uname}】修改了头像', '', icon=icon_path,
                on_click=f'https://m.weibo.cn/profile/{uid}')
        USER_FACE_DICT[uid] = face
    if sign != USER_SIGN_DICT[uid]:
        logger.info(Fore.LIGHTGREEN_EX +
                    f'【查询动态状态】【{uname}】修改了签名：【{USER_SIGN_DICT[uid]}】 -> 【{sign}】' +
                    Style.RESET_ALL)
        notify0(f'【{uname}】修改了签名', f'【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
                icon=icon_path,
                on_click=f'https://m.weibo.cn/profile/{uid}')
        USER_SIGN_DICT[uid] = sign
    if mblog_id not in DYNAMIC_DICT[uid]:
        previous_mblog_id = DYNAMIC_DICT[uid].pop()
        DYNAMIC_DICT[uid].append(previous_mblog_id)
        DYNAMIC_DICT[uid].append(mblog_id)
        logger.debug(Fore.LIGHTYELLOW_EX+str(DYNAMIC_DICT[uid]))

        card_type = card['card_type']
        if card_type not in [9]:
            logger.info(Fore.LIGHTYELLOW_EX+'【查询微博状态】【{screen_name}】微博有更新，但不在需要推送的微博类型列表中'.format(
                screen_name=uname) + Style.RESET_ALL)
            return

        # 如果微博发送日期早于昨天，则跳过（既能避免因api返回历史内容导致的误推送，也可以兼顾到前一天停止检测后产生的微博）
        created_at = time.strptime(
            mblog['created_at'], '%a %b %d %H:%M:%S %z %Y')
        created_at_ts = time.mktime(created_at)
        yesterday = (datetime.now() +
                     timedelta(days=-1)).strftime("%Y-%m-%d")
        yesterday_ts = time.mktime(time.strptime(yesterday, '%Y-%m-%d'))
        if created_at_ts < yesterday_ts:
            logger.info(Fore.LIGHTYELLOW_EX+'【查询微博状态】【{screen_name}】微博有更新，但微博发送时间早于今天，可能是历史微博，不予推送'.format(
                screen_name=uname) + Style.RESET_ALL)
            return
        dynamic_time = time.strftime('%Y-%m-%d %H:%M:%S', created_at)

        text = mblog['text']
        text = re.sub(r'<[^>]+>', '', text)
        content = mblog['raw_text'] if mblog.get(
            'raw_text', None) is not None else text
        pic_url = mblog.get('original_pic', None)
        url = card['scheme']
        logger.info(Fore.LIGHTGREEN_EX+f'【查询微博状态】【{uname}】微博有更新，准备推送：{content}' +
                    Style.RESET_ALL)
        if pic_url is None:
            notify0(f"【{uname}】微博更新", content,
                    icon=icon_path, on_click=url)
        else:
            get_icon(uid, pic_url, 'opus/')
            opus_path = realpath(f'icon/opus/wb_{uid}.jpg')
            notify0(f"【{uname}】微博更新", content,
                    on_click=url,
                    image={
                        'src': opus_path,
                        'placement': 'hero'
                    }, icon=icon_path)
        push.push_for_weibo_dynamic(
            uname, mblog_id, content, pic_url, url, dynamic_time)


def get_headers(uid):
    return {
        'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'mweibo-pwa': '1',
        'referer': 'https://m.weibo.cn/u/{}'.format(uid),
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'x-requested-with': 'XMLHttpRequest',
    }
