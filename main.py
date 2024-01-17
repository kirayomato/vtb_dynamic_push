import json
import threading
import os
from time import sleep
from config import Config
from logger import logger
from query_weibo import query_weibodynamic, query_valid
from query_bili import query_bilidynamic, query_live_status_batch
from colorama import Fore, Style, init
from win11toast import notify


def load_cookie(path):
    try:
        ck = json.load(open(path, "r"))
        cookies = {}
        for cookie in ck:
            cookies[cookie.get('name')] = cookie.get('value')
        return cookies
    except BaseException:
        return {}


def weibo():
    enable_dynamic_push = global_config.get_raw(
        'weibo', 'enable_dynamic_push')
    if enable_dynamic_push != 'true':
        logger.info(Fore.YELLOW+'【查询微博状态】未开启微博推送功能'+Style.RESET_ALL)
        return
    intervals_second = int(global_config.get_raw('weibo', 'intervals_second'))
    logger.info(Fore.GREEN+'【查询微博状态】开始检测微博'+Style.RESET_ALL)
    test = 0
    while True:
        WeiboCookies = load_cookie('WeiboCookies.txt')
        uid_list = global_config.get_raw('weibo', 'uid_list')
        if uid_list:
            uid_list = uid_list.split(',')
            try:
                if not query_valid(WeiboCookies):
                    test += 1
                    if test > 5:
                        logger.warning(
                            Fore.YELLOW + '【查询微博状态】微博Cookies无效' + Style.RESET_ALL)
                        notify("微博Cookies无效", "", duration='long',
                               app_id='vtb_dynamic', on_click='https://m.weibo.cn/')
                else:
                    test = 0
                for uid in uid_list:
                    query_weibodynamic(uid, WeiboCookies)
                    sleep(intervals_second/len(uid_list))
            except KeyboardInterrupt:
                return
            except BaseException as e:
                logger.error(
                    Fore.RED + f'【查询微博状态】【出错【{e}】' + Style.RESET_ALL)
        else:
            logger.info('【查询微博状态】未填写UID')
            sleep(intervals_second)


def bili_dy():
    enable_dynamic_push = global_config.get_raw(
        'bili', 'enable_dynamic_push')
    if enable_dynamic_push != 'true':
        logger.info(Fore.YELLOW+'【查询动态状态】未开启动态推送功能'+Style.RESET_ALL)
        return
    intervals_second = int(global_config.get_raw('bili', 'intervals_second'))
    logger.info(Fore.GREEN+'【查询动态状态】开始检测动态'+Style.RESET_ALL)
    while True:
        BiliCookies = load_cookie('BiliCookies.txt')
        uid_list = global_config.get_raw('bili', 'dynamic_uid_list')
        if uid_list:
            uid_list = uid_list.split(',')
            try:
                for uid in uid_list:
                    query_bilidynamic(uid, BiliCookies)
                    sleep(intervals_second/len(uid_list))
            except KeyboardInterrupt:
                return
            except BaseException as e:
                logger.error(
                    Fore.RED + f'【查询动态状态】【出错【{e}】' + Style.RESET_ALL)
        else:
            logger.info('【查询动态状态】未填写UID')
            sleep(intervals_second)


def bili_live():
    enable_living_push = global_config.get_raw('bili', 'enable_living_push')
    if enable_living_push != 'true':
        logger.info(Fore.YELLOW+'【查询直播状态】未开启直播推送功能'+Style.RESET_ALL)
        return
    intervals_second = int(global_config.get_raw('bili', 'intervals_second'))
    logger.info(Fore.GREEN+'【查询直播状态】开始检测直播'+Style.RESET_ALL)
    while True:
        BiliCookies = load_cookie('BiliCookies.txt')
        uid_list = global_config.get_raw('bili', 'live_uid_list')
        if uid_list:
            uid_list = uid_list.split(',')
            try:
                query_live_status_batch(uid_list, BiliCookies)
                sleep(intervals_second)
            except KeyboardInterrupt:
                return
            except BaseException as e:
                logger.error(
                    Fore.RED + f'【查询直播状态】【出错【{e}】' + Style.RESET_ALL)
        else:
            logger.info('【查询直播状态】未填写UID')
            sleep(intervals_second)


def update_config():
    while True:
        global global_config
        global_config = Config()
        logger.info(Fore.GREEN+'【Config】更新Config'+Style.RESET_ALL)
        sleep(30)

if __name__ == '__main__':
    global_config = Config()
    if not os.path.exists('icon'):
        os.mkdir('icon')
    init(autoreset=True)
    thread1 = threading.Thread(target=bili_dy)
    thread2 = threading.Thread(target=bili_live)
    thread3 = threading.Thread(target=weibo)
    thread4 = threading.Thread(target=update_config)
    thread1.start()
    thread2.start()
    thread3.start()
    thread4.start()
