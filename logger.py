import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os
from colorama import Fore, Style
from time import time
from collections import deque
from web import OutputList
import shutil
from datetime import datetime, timedelta


def move_old_logs(directory):
    """
    将指定目录及其子目录下修改日期在一个月前的 .log 文件移动到 old 文件夹中。

    :param directory: 要处理的目录路径
    """
    # 获取一个月前的日期
    old_date = datetime.now() - timedelta(days=30)
    old_dir = os.path.join(directory, "old")  # old 文件夹路径

    # 如果 old 文件夹不存在，则创建
    if not os.path.exists(old_dir):
        os.makedirs(old_dir)

    # 遍历目录及其子目录下的所有文件
    for files in os.listdir(directory):
        for file in files:
            if ".log" in file:  # 只处理 .log 文件
                file_path = os.path.join(directory, file)
                # 获取文件的最后修改时间
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                # 如果修改时间早于一个月前，则移动文件
                if file_mtime < old_date:
                    try:
                        shutil.move(file_path, os.path.join(old_dir, file))
                        logger.info(f"已将 {file_path} 移动到 {old_dir}")
                    except Exception as e:
                        logger.error(f"移动 {file_path} 失败: {e}")


class mylogger:
    def __init__(self) -> None:
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        logging.getLogger("urllib3").setLevel(logging.INFO)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        formatter = logging.Formatter(
            "%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s"
        )
        console_handler = logging.StreamHandler(stream=sys.stdout)
        web_handler = logging.StreamHandler(stream=OutputList())
        console_handler.setFormatter(formatter)
        web_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(web_handler)
        if not os.path.exists("log"):
            os.mkdir("log")
        fh = TimedRotatingFileHandler(
            filename="log/vtb_dynamic.log",
            encoding="utf-8",
            when="midnight",
            interval=1,
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.error_count = deque()

    def info(self, msg, prefix="", color=Fore.LIGHTGREEN_EX):
        msg = prefix + msg
        if color:
            msg = color + msg + Style.RESET_ALL
        self.logger.info(msg, stacklevel=2)

    def debug(self, msg, prefix="", color=""):
        msg = prefix + msg
        if color:
            msg = color + msg + Style.RESET_ALL
        self.logger.debug(msg, stacklevel=2)

    def warning(self, msg, prefix="", color=Fore.YELLOW):
        msg = prefix + msg
        if color:
            msg = color + msg + Style.RESET_ALL
        self.logger.warning(msg, stacklevel=2)

    def error(self, msg, prefix="", color=Fore.RED):
        msg = prefix + msg
        self.error_count.append(time())
        while len(self.error_count) and time() - self.error_count[0] > 3600:
            self.error_count.popleft()
        if len(self.error_count) == 10:
            from push import notify

            notify(
                "检测到大量报错",
                f"一小时内累计报错{len(self.error_count)}次，请检查运行状态",
            )

        if color:
            msg = color + msg + Style.RESET_ALL
        self.logger.error(msg, stacklevel=2)


logger = mylogger()
move_old_logs("log")
