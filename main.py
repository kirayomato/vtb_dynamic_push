import json
import threading
import os
from time import sleep
import traceback
from config import global_config
from logger import logger, output_list, cnt
from query_weibo import query_weibodynamic, query_valid, USER_NAME_DICT
from query_bili import query_bilidynamic, query_live_status_batch, DYNAMIC_NAME_DICT, LIVE_NAME_DICT, try_cookies
from colorama import Fore, init, Style
from push import notify


def load_cookie(path):
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write('[]')
    try:
        ck = json.load(open(path, "r"))
        cookies = {}
        for cookie in ck:
            cookies[cookie.get('name')] = cookie.get('value')
        logger.debug(f'读取{path}', '【Cookies】', Fore.GREEN)
        return cookies
    except BaseException:
        return {}


def weibo():
    prefix = '【查询微博状态】'
    enable_dynamic_push = global_config.get_raw(
        'weibo', 'enable_dynamic_push')
    cookies_check = global_config.get_raw(
        'weibo', 'enable_cookies_check')
    if enable_dynamic_push != 'true':
        logger.warning('未开启微博推送功能', prefix)
        return
    if cookies_check == 'true':
        check_uid = global_config.get_raw(
            'weibo', 'cookies_check_uid')
    global cnt
    cnt += 1
    logger.info('开始检测微博', prefix, Fore.GREEN)
    test = 0
    WeiboCookies = {}
    while True:
        ck = load_cookie('WeiboCookies.json')
        intervals_second = int(
            global_config.get_raw('weibo', 'intervals_second'))
        if WeiboCookies != ck:
            WeiboCookies = ck
            test = 0
            logger.info('微博Cookies更新', prefix, Fore.GREEN)
        uid_list = global_config.get_raw('weibo', 'uid_list')
        if uid_list:
            uid_list = set(uid_list.split(','))
            if cookies_check == 'true' and not query_valid(check_uid, WeiboCookies):
                test += 1
                if test == 5:
                    logger.warning('微博Cookies无效', prefix)
                    notify("微博Cookies无效", "", on_click='https://m.weibo.cn/')
            else:
                test = 0
            for uid in uid_list:
                try:
                    query_weibodynamic(uid, WeiboCookies, msg)
                except KeyboardInterrupt:
                    return
                except BaseException as e:
                    logger.error(
                        f'【{uid}】出错【{e}】：{traceback.format_exc()}', prefix)
                sleep(max(1, intervals_second/len(uid_list)))
        else:
            logger.warning('未填写UID', prefix)
            sleep(intervals_second)
        if not swi[1]:
            swi[1] = 1
            logger.info(f'监控列表({len(USER_NAME_DICT)}):{",".join(USER_NAME_DICT.values())}',
                        prefix, Fore.LIGHTYELLOW_EX)


def bili_dy():
    prefix = '【查询动态状态】'
    enable_dynamic_push = global_config.get_raw(
        'bili', 'enable_dynamic_push')
    if enable_dynamic_push != 'true':
        logger.warning('未开启动态推送功能', prefix)
        return
    global cnt
    cnt += 1
    logger.info('开始检测动态', prefix, Fore.GREEN)
    test = 0
    BiliCookies = {}
    while True:
        bk = load_cookie('BiliCookies.json')
        intervals_second = int(global_config.get_raw(
            'bili', 'dynamic_intervals_second'))
        if BiliCookies != bk:
            BiliCookies = bk
            test = 0
            logger.info('B站Cookies更新', prefix, Fore.GREEN)
        if not try_cookies(BiliCookies):
            test += 1
            if test == 5:
                logger.warning('B站Cookies无效', prefix)
                notify("B站Cookies无效", "", on_click='https://www.bilibili.com/')
        else:
            test = 0
        uid_list = global_config.get_raw('bili', 'dynamic_uid_list')
        if uid_list:
            uid_list = set(uid_list.split(','))
            for uid in uid_list:
                try:
                    query_bilidynamic(uid, BiliCookies, msg)
                except KeyboardInterrupt:
                    return
                except BaseException as e:
                    logger.error(
                        f'【{uid}】出错【{e}】：{traceback.format_exc()}', prefix)
                sleep(max(1, intervals_second/len(uid_list)))
        else:
            logger.warning('未填写UID', prefix)
            sleep(intervals_second)
        if not swi[0]:
            swi[0] = 1
            logger.info(f'监控列表({len(DYNAMIC_NAME_DICT)}):{",".join(DYNAMIC_NAME_DICT.values())}',
                        prefix, Fore.LIGHTBLUE_EX)


def bili_live():
    prefix = '【查询直播状态】'
    enable_living_push = global_config.get_raw('bili', 'enable_living_push')
    if enable_living_push != 'true':
        logger.warning('未开启直播推送功能', prefix)
        return
    global cnt
    cnt += 1
    logger.info('开始检测直播', prefix, Fore.GREEN)
    while True:
        intervals_second = int(global_config.get_raw(
            'bili', 'live_intervals_second'))
        BiliCookies = load_cookie('BiliCookies.json')
        uid_list = global_config.get_raw('bili', 'live_uid_list')
        special = global_config.get_raw('bili', 'special_list')
        if special:
            special = set(special.split(','))
        else:
            special = set()
        if uid_list:
            uid_list = set(uid_list.split(','))
            try:
                query_live_status_batch(uid_list, BiliCookies, msg, special)
            except KeyboardInterrupt:
                return
            except BaseException as e:
                logger.error(
                    f'出错【{e}】：{traceback.format_exc()}', prefix)
        else:
            logger.warning('未填写UID', prefix)
        if not swi[2]:
            swi[2] = 1
            logger.info(f'监控列表({len(LIVE_NAME_DICT)}):{",".join(LIVE_NAME_DICT.values())}',
                        prefix, Fore.CYAN)
        sleep(intervals_second)


def print_state():
    while True:
        if sum(swi) == cnt:
            global output_list
            for i in range(3):
                if msg[i]:
                    output_list[i] = msg[i]
        sleep(0.1)


if __name__ == '__main__':
    if not os.path.exists('icon/cover'):
        os.makedirs('icon/cover')
    if not os.path.exists('icon/opus'):
        os.makedirs('icon/opus')
    msg = [""]*3
    swi = [0]*3
    init(autoreset=True)
    thread1 = threading.Thread(target=bili_dy)
    thread2 = threading.Thread(target=bili_live)
    thread3 = threading.Thread(target=weibo)
    thread4 = threading.Thread(target=print_state)
    thread1.start()
    thread2.start()
    thread3.start()
    thread4.start()
    thread4.join()
