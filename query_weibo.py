from datetime import datetime, timedelta
import json
import re
import time
from push import notify
from logger import logger
import requests
from requests.exceptions import RequestException
from os.path import realpath, exists
from colorama import Fore, Style
from os import environ


environ['NO_PROXY'] = '*'
DYNAMIC_DICT = {}
LAST_ID = {}
USER_FACE_DICT = {}
USER_SIGN_DICT = {}
USER_NAME_DICT = {}
USER_COUNT_DICT = {}
proxies = {
    "http": "",
    "https": "",
}
prefix = '【查询微博状态】'


def query_valid(uid, cookie):
    query_url = 'https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25'.format(
        uid=uid)
    headers = get_headers(uid)
    try:
        response = requests.get(query_url, headers=headers,
                                cookies=cookie, proxies=proxies, timeout=10)
        result = json.loads(str(response.content, "utf-8"))
        cards = result['data']['cards']
        return len(cards) > 10
    except:
        return True


def query_weibodynamic(uid, cookie, msg):
    def sleep(t):
        msg[1] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
            Fore.LIGHTYELLOW_EX + '休眠中' + Style.RESET_ALL
        time.sleep(t)

    def get_content(mblog):
        if mblog.get('raw_text', None):
            return mblog['raw_text']
        else:
            return re.sub(r'<[^>]+>', '', mblog['text'])

    if uid is None:
        return
    query_url = f'https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&count=25'
    headers = get_headers(uid)
    try:
        response = requests.get(query_url, headers=headers,
                                cookies=cookie, proxies=proxies, timeout=10)
    except RequestException as e:
        logger.warning(f'网络错误 url:{query_url}, error:{e}, 休眠一分钟', prefix)
        sleep(60)
        return
    if response.status_code != 200:
        if response.status_code == 403:
            logger.warning(
                f'触发风控 url:{query_url}, status:{response.status_code}, msg:{response.reason}, 休眠五分钟', prefix)
            sleep(300)
        else:
            logger.warning(
                f'请求错误 url:{query_url}, status:{response.status_code}, msg:{response.reason}, 休眠一分钟', prefix)
            sleep(60)
        return
    try:
        result = json.loads(str(response.content, "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.error(
            f'【{uid}】解析content出错:{e}, url:{query_url}, 休眠一分钟, content:\n{str(response.content, "utf-8")}', prefix)
        sleep(60)
        return
    if result['ok'] not in (0, 1):
        logger.error(
            f'【{uid}】请求返回数据code错误:{result["ok"]}, url:{query_url}, msg:{result["msg"]}, 休眠五分钟', prefix)
        sleep(300)
        return
    try:
        cards = [i for i in result['data']['cards'] if i['card_type'] == 9]
        n = len(cards)
        if n == 0:
            if DYNAMIC_DICT.get(uid, None) is None:
                logger.debug(f'【{uid}】微博列表为空', prefix)
                return
        card = cards[0]
        mblog = card['mblog']
        user = mblog['user']
        uname = user['screen_name']
        face = user['profile_image_url']
        face = face[:face.find('?')]
        sign = user['description']
        total = result['data']['cardlistInfo']['total']
    except KeyError:
        logger.error(
            f'【{uid}】返回数据不完整,休眠一分钟, url:{query_url}\ndata:{result}', prefix)
        sleep(60)
        return
    msg[1] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' - ' + \
        Fore.LIGHTYELLOW_EX+f'查询{uname}微博' + Style.RESET_ALL
    if DYNAMIC_DICT.get(uid, None) is None:
        DYNAMIC_DICT[uid] = {}
        USER_FACE_DICT[uid] = face
        USER_SIGN_DICT[uid] = sign
        USER_NAME_DICT[uid] = uname
        USER_COUNT_DICT[uid] = total
        LAST_ID[uid] = cards[-1]['mblog']['id']
        for card in cards:
            mblog = card['mblog']
            mblog_id = mblog['id']
            if mblog_id >= LAST_ID[uid]:
                DYNAMIC_DICT[uid][mblog['id']] = get_content(mblog)
        logger.info(
            f'【{uname}】微博初始化,len = {len(DYNAMIC_DICT[uid])}', prefix, Fore.LIGHTYELLOW_EX)
        logger.debug(
            f'【{uname}】微博初始化 {DYNAMIC_DICT[uid]}', prefix, Fore.LIGHTYELLOW_EX)
        return
    icon_path = None
    if face != USER_FACE_DICT[uid]:
        logger.info(f'【{uname}】更改了头像', prefix, Fore.LIGHTYELLOW_EX)
        notify(f'【{uname}】更改了头像', '', icon=icon_path,
               on_click=f'https://m.weibo.cn/profile/{uid}')
        USER_FACE_DICT[uid] = face
    if sign != USER_SIGN_DICT[uid]:
        logger.info(f'【{uname}】更改了签名：【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
                    prefix, Fore.LIGHTYELLOW_EX)
        notify(f'【{uname}】更改了签名', f'【{USER_SIGN_DICT[uid]}】 -> 【{sign}】',
               icon=icon_path,
               on_click=f'https://m.weibo.cn/profile/{uid}')
        USER_SIGN_DICT[uid] = sign

    cnt = 0
    for card in cards:
        mblog = card['mblog']
        mblog_id = mblog['id']
        if mblog_id in DYNAMIC_DICT[uid] or mblog_id < LAST_ID[uid]:
            continue
        cnt += 1
        created_at = time.strptime(
            mblog['created_at'], '%a %b %d %H:%M:%S %z %Y')
        dynamic_time = time.strftime('%Y-%m-%d %H:%M:%S', created_at)
        action = '微博更新'

        pic_url = mblog.get('original_pic', None)
        if 'retweeted_status' in mblog:
            action = '转发微博'
            pic_url = mblog['retweeted_status'].get(
                'original_pic', None)
            if not pic_url and 'page_info' in mblog['retweeted_status']:
                pic_url = mblog['retweeted_status']['page_info']['page_pic']['url']

        url = card['scheme']
        content = get_content(mblog)
        image = None
        logger.info(f'【{uname}】{action} {dynamic_time}: {content}，url: {url}',
                    prefix, Fore.LIGHTYELLOW_EX)
        notify(f"【{uname}】{action}", content,
               on_click=url, image=image, icon=icon_path)
        DYNAMIC_DICT[uid][mblog_id] = content
        logger.debug(str(DYNAMIC_DICT[uid]), prefix, Fore.LIGHTYELLOW_EX)

    _total = USER_COUNT_DICT[uid]
    USER_COUNT_DICT[uid] = total
    if total == _total+cnt:
        return

    if total < _total+cnt:
        action = '删除了微博，但未能找到'
        # 尝试检测被删除的微博
        st = [card['mblog']['id'] for card in cards]
        last_id = st[-1]
        st = set(st)
        del_list = []
        for id in DYNAMIC_DICT[uid]:
            if id >= last_id and id not in st:
                cnt -= 1
                del_list.append(id)
                logger.info(f'【{uname}】删除微博：{DYNAMIC_DICT[uid][id]}',
                            prefix, Fore.LIGHTYELLOW_EX)
                notify(f'【{uname}】删除微博', f'{DYNAMIC_DICT[uid][id]}',
                       icon=icon_path,
                       on_click=f'https://m.weibo.cn/profile/{uid}')
        for id in del_list:
            del DYNAMIC_DICT[uid][id]
        if total == _total+cnt:
            return

    else:
        action = '发布了微博，但未能抓取'
    logger.info(f'【{uname}】{action}：{_total} -> {total}',
                prefix, Fore.LIGHTYELLOW_EX)
    notify(f'【{uname}】{action}', f'{_total} -> {total}',
           icon=icon_path,
           on_click=f'https://m.weibo.cn/profile/{uid}')


def get_headers(uid):
    return {
        'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'utf-8, gzip, deflate, zstd',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'no-cache',
        'connection': 'keep-alive',
        'pragma': 'no-cache',
        'mweibo-pwa': '1',
        'referer': 'https://m.weibo.cn/u/{}'.format(uid),
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'x-requested-with': 'XMLHttpRequest',
    }
