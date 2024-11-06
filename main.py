import json
import threading
import os
from time import sleep
import traceback
from config import global_config as config
from logger import logger
from web import app
from query_weibo import query_weibodynamic, query_valid, USER_NAME_DICT
from query_bili import query_bilidynamic, query_live_status_batch, DYNAMIC_NAME_DICT, LIVE_NAME_DICT, try_cookies
from colorama import Fore, init, Style
from push import notify
import uvicorn


def weibo():
    prefix = '【查询微博状态】'
    enable_dynamic_push = config.get_raw(
        'weibo', 'enable_dynamic_push')
    cookies_check = config.get_raw(
        'weibo', 'enable_cookies_check')
    if enable_dynamic_push != 'true':
        logger.warning('未开启微博推送功能', prefix)
        return
    if cookies_check == 'true':
        check_uid = config.get_raw(
            'weibo', 'cookies_check_uid')
    logger.info('开始检测微博', prefix, Fore.GREEN)
    test = 0
    while True:
        intervals_second = int(
            config.get_raw('weibo', 'intervals_second'))
        if cookies_check == 'true' and not query_valid(check_uid, config.WeiboCookies):
            test += 1
            if test == 5:
                logger.warning('微博Cookies无效', prefix)
                notify("微博Cookies无效", "", on_click='https://m.weibo.cn/')
        else:
            test = 0
        uid_list = config.get_raw('weibo', 'uid_list')
        if uid_list:
            uid_list = set(uid_list.split(','))
            for uid in uid_list:
                try:
                    query_weibodynamic(
                        uid, config.WeiboCookies, msg)
                except KeyboardInterrupt:
                    return
                except BaseException as e:
                    logger.error(
                        f'【{uid}】出错【{e}】：{traceback.format_exc()}', prefix)
                sleep(max(1, intervals_second/len(uid_list)))
        else:
            logger.warning('未填写UID', prefix)
            return
        if not swi[1]:
            swi[1] = 1
            logger.info(f'监控列表({len(USER_NAME_DICT)}):{",".join(USER_NAME_DICT.values())}',
                        prefix, Fore.LIGHTYELLOW_EX)


def bili_dy():
    prefix = '【查询动态状态】'
    enable_dynamic_push = config.get_raw(
        'bili', 'enable_dynamic_push')
    if enable_dynamic_push != 'true':
        logger.warning('未开启动态推送功能', prefix)
        return
    logger.info('开始检测动态', prefix, Fore.GREEN)
    test = 0
    while True:
        intervals_second = int(config.get_raw(
            'bili', 'dynamic_intervals_second'))
        if not try_cookies(config.BiliCookies):
            test += 1
            if test == 5:
                logger.warning('B站Cookies无效', prefix)
                notify("B站Cookies无效", "", on_click='https://www.bilibili.com/')
        else:
            test = 0
        uid_list = config.get_raw('bili', 'dynamic_uid_list')
        if uid_list:
            uid_list = set(uid_list.split(','))
            for uid in uid_list:
                try:
                    query_bilidynamic(uid, config.BiliCookies, msg)
                except KeyboardInterrupt:
                    return
                except BaseException as e:
                    logger.error(
                        f'【{uid}】出错【{e}】：{traceback.format_exc()}', prefix)
                sleep(max(1, intervals_second/len(uid_list)))
        else:
            logger.warning('未填写UID', prefix)
            return
        if not swi[0]:
            swi[0] = 1
            logger.info(f'监控列表({len(DYNAMIC_NAME_DICT)}):{",".join(DYNAMIC_NAME_DICT.values())}',
                        prefix, Fore.LIGHTBLUE_EX)


def bili_live():
    prefix = '【查询直播状态】'
    enable_living_push = config.get_raw('bili', 'enable_living_push')
    if enable_living_push != 'true':
        logger.warning('未开启直播推送功能', prefix)
        return
    logger.info('开始检测直播', prefix, Fore.GREEN)
    while True:
        intervals_second = int(config.get_raw(
            'bili', 'live_intervals_second'))
        uid_list = config.get_raw('bili', 'live_uid_list')
        special = config.get_raw('bili', 'special_list')
        if special:
            special = set(special.split(','))
        else:
            special = set()
        if uid_list:
            uid_list = set(uid_list.split(','))
            try:
                query_live_status_batch(
                    uid_list, config.BiliCookies, msg, special)
            except KeyboardInterrupt:
                return
            except BaseException as e:
                logger.error(f'出错【{e}】：{traceback.format_exc()}', prefix)
        else:
            logger.warning('未填写UID', prefix)
            return
        if not swi[2]:
            swi[2] = 1
            logger.info(f'监控列表({len(LIVE_NAME_DICT)}):{",".join(LIVE_NAME_DICT.values())}',
                        prefix, Fore.CYAN)
        sleep(intervals_second)


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
    thread1.start()
    thread2.start()
    thread3.start()
    uvicorn.run(app, host='0.0.0.0', port=5000, log_level='warning')
