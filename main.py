import threading
from time import sleep
import traceback
from logger import logger, output_manager
from web import app
from query_weibo import query_weibodynamic, query_valid, USER_NAME_DICT
from query_bili import (
    query_bilidynamic,
    query_live_status_batch,
    DYNAMIC_NAME_DICT,
    LIVE_NAME_DICT,
)
from query_afd import query_afddynamic, AFD_NAME_DICT
from colorama import Fore, init
from push import notify
from push import global_config as config
import uvicorn
from random import random
from scheduler import Scheduler


def crash_handler(args):
    logger.error(
        f"任务【{args.thread.name}】崩溃: \n{''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))}"
    )
    notify(
        f"任务【{args.thread.name}】崩溃",
        "".join(
            traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            )
        ),
    )


# 注册全局异常钩子
threading.excepthook = crash_handler


def weibo():
    prefix = "【查询微博动态】"
    enable_dynamic_push = config.get("weibo", "enable_dynamic_push")
    cookies_check = config.get("weibo", "enable_cookie_check")
    if enable_dynamic_push != "true":
        logger.warning("未开启微博推送功能", prefix)
        return
    if cookies_check == "true":
        check_uid = config.get("weibo", "cookie_check_uid")
    output_manager.inc_cnt()
    logger.info("开始检测微博", prefix, Fore.GREEN)
    test = 0
    intervals_second = 5
    sched = Scheduler()
    while True:
        if cookies_check == "true" and not query_valid(check_uid, config.WeiboCookies):
            test += 1
            if test % 3 == 0:
                logger.warning("微博Cookie无效", prefix)
                notify("微博Cookie无效", "", on_click="https://m.weibo.cn/")
        else:
            test = 0
        uid_list = config.get("weibo", "uid_list")
        if uid_list:
            uid_list = uid_list.split(",")
            sched.update_targets(uid_list)
            for _ in range(len(uid_list)):
                uid = sched.next_target()
                if uid:
                    try:
                        weight = query_weibodynamic(
                            uid, config.WeiboCookies, output_manager.msg
                        )
                        if weight is not False:
                            assert type(weight) is int
                            sched.update(uid, weight)
                    except BaseException as e:
                        logger.error(
                            f"【{uid}】出错【{e}】：{traceback.format_exc()}", prefix
                        )
                intervals_second = float(config.get("weibo", "intervals_second"))
                sleep(max(1, intervals_second) * (1 + random() / 10))
        else:
            logger.warning("未填写UID", prefix)
            return
        if not output_manager.swi[1]:
            output_manager.set_swi(1)
            logger.info(
                f'监控列表({len(USER_NAME_DICT)}):{",".join(USER_NAME_DICT.values())}',
                prefix,
                Fore.LIGHTYELLOW_EX,
            )


def bili_dy():
    prefix = "【查询B站动态】"
    enable_dynamic_push = config.get("bili", "enable_dynamic_push")
    if enable_dynamic_push != "true":
        logger.warning("未开启动态推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测动态", prefix, Fore.GREEN)
    intervals_second = 5
    sched = Scheduler()
    while True:
        uid_list = config.get("bili", "dynamic_uid_list")
        if uid_list:
            uid_list = uid_list.split(",")
            sched.update_targets(uid_list)
            for _ in range(len(uid_list)):
                uid = sched.next_target()
                if uid:
                    try:
                        weight = query_bilidynamic(
                            uid, config.BiliCookies, output_manager.msg
                        )
                        if weight is not False:
                            assert type(weight) is int
                            sched.update(uid, weight)
                    except BaseException as e:
                        logger.error(
                            f"【{uid}】出错【{e}】：{traceback.format_exc()}", prefix
                        )
                intervals_second = float(config.get("bili", "dynamic_intervals_second"))
                sleep(max(1, intervals_second) * (1 + random() / 10))
        else:
            logger.warning("未填写UID", prefix)
            return
        if not output_manager.swi[0]:
            output_manager.set_swi(0)
            logger.info(
                f'监控列表({len(DYNAMIC_NAME_DICT)}):{",".join(DYNAMIC_NAME_DICT.values())}',
                prefix,
                Fore.LIGHTBLUE_EX,
            )


def afd_dy():
    prefix = "【查询爱发电】"
    enable_dynamic_push = config.get("afd", "enable_dynamic_push")
    if enable_dynamic_push != "true":
        logger.warning("未开启动态推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测爱发电", prefix, Fore.GREEN)
    intervals_second = 10
    while True:
        uid_list = config.get("afd", "uid_list")
        if uid_list:
            uid_list = set(uid_list.split(","))
            for uid in uid_list:
                intervals_second = float(config.get("afd", "intervals_second")) / 2
                try:
                    query_afddynamic(uid, None, output_manager.msg, intervals_second)
                except BaseException as e:
                    logger.error(
                        f"【{uid}】出错【{e}】：{traceback.format_exc()}", prefix
                    )
                sleep(max(1, intervals_second) * (1 + random() / 10))
        else:
            logger.warning("未填写UID", prefix)
            return
        if not output_manager.swi[3]:
            output_manager.set_swi(3)
            logger.info(
                f'监控列表({len(AFD_NAME_DICT)}):{",".join(AFD_NAME_DICT.values())}',
                prefix,
                Fore.LIGHTCYAN_EX,
            )


def bili_live():
    prefix = "【查询B站直播】"
    enable_living_push = config.get("bili", "enable_living_push")
    if enable_living_push != "true":
        logger.warning("未开启直播推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测直播", prefix, Fore.GREEN)
    intervals_second = 30
    while True:
        intervals_second = int(config.get("bili", "live_intervals_second"))
        uid_list = config.get("bili", "live_uid_list")
        special = config.get("bili", "special_list")
        if special:
            special = set(special.split(","))
        else:
            special = set()
        if uid_list:
            uid_list = set(uid_list.split(","))
            try:
                query_live_status_batch(
                    uid_list, config.BiliCookies, output_manager.msg, special
                )
            except BaseException as e:
                logger.error(f"出错【{e}】：{traceback.format_exc()}", prefix)
        else:
            logger.warning("未填写UID", prefix)
            return
        if not output_manager.swi[2]:
            output_manager.set_swi(2)
            logger.info(
                f'监控列表({len(LIVE_NAME_DICT)}):{",".join(LIVE_NAME_DICT.values())}',
                prefix,
                Fore.CYAN,
            )
        sleep(intervals_second * (1 + random() / 10))


def run_server():
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="warning")


if __name__ == "__main__":
    init(autoreset=True)
    thread1 = threading.Thread(target=bili_dy, daemon=True, name="查询B站动态")
    thread2 = threading.Thread(target=bili_live, daemon=True, name="查询B站直播")
    thread3 = threading.Thread(target=weibo, daemon=True, name="查询微博动态")
    thread4 = threading.Thread(target=afd_dy, daemon=True, name="查询爱发电")
    thread5 = threading.Thread(target=run_server, daemon=True, name="web服务")
    thread1.start()
    thread2.start()
    thread3.start()
    thread4.start()
    thread5.start()
    while True:
        output_manager.refresh()
        sleep(0.1)
