import threading
from random import random
from time import sleep
import traceback

import uvicorn
from colorama import Fore, init

import web
from config import global_config as config
from logger import logger, output_manager, Slot
from push import notify
from query_afd import query_afddynamic, AFD_NAME_DICT, init_state as init_afd_state
from query_bili import (
    query_bilidynamic,
    query_live_status_batch,
    DYNAMIC_NAME_DICT,
    LIVE_NAME_DICT,
    init_state as init_bili_state,
)
from query_weibo import (
    query_weibodynamic,
    query_valid,
    USER_NAME_DICT,
    init_state as init_weibo_state,
)
from scheduler import Scheduler
from web import app


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


def read_uids(section, key, prefix):
    """读 uid 列表并拆分。

    未配置视为该平台未使用，提示后返回 None，调用方据此结束线程。
    """
    uid_list = config.get(section, key)
    if not uid_list:
        logger.warning("未填写UID", prefix)
        return None
    return uid_list.split(",")


def report_ready(slot, names, prefix, color):
    """首轮抓取完成后上报控制台就绪，并打印一次监控列表。

    幂等：已经就绪的槽位直接返回，因此每个线程只在首轮打印一次。
    """
    if output_manager.is_ready(slot):
        return
    output_manager.mark_ready(slot)
    logger.info(f'监控列表({len(names)}):{",".join(names.values())}', prefix, color)


def run_user(sched, uid, query, prefix):
    """抓取单个用户，并按返回的权重更新调度。

    query 返回 False 表示本次未取到有效权重（如已进入退避），此时跳过调度更新；
    其余返回值必须是 int。异常只记录不抛出，避免单个用户中断整轮。
    """
    try:
        weight = query(uid, output_manager)
        if weight is not False:
            assert type(weight) is int
            sched.update(uid, weight)
    except BaseException as e:
        logger.error(f"【{uid}】出错【{e}】：{traceback.format_exc()}", prefix)


def bili_dynamic_loop():
    """B 站动态：按用户权重轮转，逐用户抓取。"""
    prefix = "【查询B站动态】"
    if config.get("bili", "enable_dynamic_push") != "true":
        logger.warning("未开启动态推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测动态", prefix, Fore.GREEN)
    sched = Scheduler("bili_dy")
    web.scheduler_registry["bili_dy"] = sched

    while True:
        uids = read_uids("bili", "dynamic_uid_list", prefix)
        if uids is None:
            return
        sched.update_targets(uids)
        for _ in range(len(uids)):
            uid = sched.next_target()
            if uid:
                run_user(sched, uid, query_bilidynamic, prefix)
            seconds = float(config.get("bili", "dynamic_intervals_second"))
            sleep(max(1, seconds) * (1 + random() / 10))
        report_ready(Slot.BILI, DYNAMIC_NAME_DICT, prefix, Fore.LIGHTBLUE_EX)


def bili_live_loop():
    """B 站直播：一轮一次批量查询，轮间休眠。"""
    prefix = "【查询B站直播】"
    if config.get("bili", "enable_living_push") != "true":
        logger.warning("未开启直播推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测直播", prefix, Fore.GREEN)

    while True:
        uids = read_uids("bili", "live_uid_list", prefix)
        if uids is None:
            return
        seconds = int(config.get("bili", "live_intervals_second"))
        try:
            query_live_status_batch(set(uids), output_manager)
        except BaseException as e:
            logger.error(f"出错【{e}】：{traceback.format_exc()}", prefix)
        report_ready(Slot.LIVE, LIVE_NAME_DICT, prefix, Fore.CYAN)
        sleep(seconds * (1 + random() / 10))


def weibo_loop():
    """微博：按用户权重轮转，逐用户抓取；每轮先校验一次 Cookie 有效性。"""
    prefix = "【查询微博动态】"
    if config.get("weibo", "enable_dynamic_push") != "true":
        logger.warning("未开启微博推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测微博", prefix, Fore.GREEN)
    sched = Scheduler("weibo")
    web.scheduler_registry["weibo"] = sched
    failures = 0

    while True:
        uids = read_uids("weibo", "uid_list", prefix)
        if uids is None:
            return
        if config.get("weibo", "enable_cookie_check") == "true":
            check_uid = config.get("weibo", "cookie_check_uid")
            if query_valid(check_uid, config.WeiboCookies):
                failures = 0
            else:
                failures += 1
                # 连续失败 3 次才告警一次，避开网络抖动造成的误报
                if failures % 3 == 0:
                    logger.warning("微博Cookie无效", prefix)
                    notify("微博Cookie无效", "", on_click="https://m.weibo.cn/")
        sched.update_targets(uids)
        for _ in range(len(uids)):
            uid = sched.next_target()
            if uid:
                run_user(sched, uid, query_weibodynamic, prefix)
            seconds = float(config.get("weibo", "intervals_second"))
            sleep(max(1, seconds) * (1 + random() / 10))
        report_ready(Slot.WEIBO, USER_NAME_DICT, prefix, Fore.LIGHTYELLOW_EX)


def afd_loop():
    """爱发电：一轮内每个 uid 只查一次。"""
    prefix = "【查询爱发电】"
    if config.get("afd", "enable_dynamic_push") != "true":
        logger.warning("未开启动态推送功能", prefix)
        return
    output_manager.inc_cnt()
    logger.info("开始检测爱发电", prefix, Fore.GREEN)

    while True:
        uids = read_uids("afd", "uid_list", prefix)
        if uids is None:
            return
        for uid in set(uids):
            # 一轮内的用户间停顿取配置值的一半
            seconds = float(config.get("afd", "intervals_second")) / 2
            try:
                query_afddynamic(uid, None, output_manager, seconds)
            except BaseException as e:
                logger.error(f"【{uid}】出错【{e}】：{traceback.format_exc()}", prefix)
            sleep(max(1, seconds) * (1 + random() / 10))
        report_ready(Slot.AFD, AFD_NAME_DICT, prefix, Fore.LIGHTCYAN_EX)


def run_server():
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="warning")


if __name__ == "__main__":
    init(autoreset=True)
    # 从本地数据库恢复各平台状态，必须在任何查询线程启动之前完成，
    # 否则线程会先跑到初始化分支，把已有状态当成"新用户"重新拉取一遍。
    init_bili_state()
    init_weibo_state()
    init_afd_state()
    # 列表顺序即线程启动顺序，线程名同时用于崩溃通知里的任务标识
    for name, target in [
        ("查询B站动态", bili_dynamic_loop),
        ("查询B站直播", bili_live_loop),
        ("查询微博动态", weibo_loop),
        ("查询爱发电", afd_loop),
        ("web服务", run_server),
    ]:
        threading.Thread(target=target, daemon=True, name=name).start()
    while True:
        output_manager.refresh()
        sleep(0.1)
