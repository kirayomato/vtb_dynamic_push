import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os
from colorama import Fore, Style
from time import time
from collections import deque
from web import output_stream
import shutil
from datetime import datetime, timedelta


def move_old_logs(directory):
    """
    将指定目录及其子目录下修改日期在一个月前的 .log 文件移动到 old 文件夹中。

    :param directory: 要处理的目录路径
    """
    # 获取一个月前的日期
    old_date = datetime.now() - timedelta(days=15)
    old_dir = os.path.join(directory, "old")  # old 文件夹路径

    os.makedirs(old_dir, exist_ok=True)

    # 遍历目录及其子目录下的所有文件
    for file in os.listdir(directory):
        if ".log" in file:  # 只处理 .log 文件
            file_path = os.path.join(directory, file)
            # 获取文件的最后修改时间
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            # 如果修改时间早于一个月前，则移动文件
            if file_mtime < old_date:
                try:
                    shutil.move(file_path, os.path.join(old_dir, file))
                    logger.debug(f"已将 {file_path} 移动到 {old_dir}")
                except Exception as e:
                    logger.error(f"移动 {file_path} 失败: {e}")


class mylogger:
    def __init__(self, log_dir="log"):
        self.log_dir = log_dir
        self.error_count = deque(maxlen=10)  # 限制错误计数队列长度
        os.makedirs(log_dir, exist_ok=True)
        self.log_level = logging.INFO
        self._setup_loggers()

    def _setup_loggers(self):
        """配置日志处理器"""
        formatter = logging.Formatter(
            "%(asctime)s|%(filename)14s|line:%(lineno)3d|%(levelname)7s|%(message)s"
        )
        logging.getLogger("urllib3").setLevel(logging.INFO)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        # 控制台日志
        self.console_logger = self._create_console_logger(formatter)
        # 文件日志
        self.file_logger = self._create_file_logger(formatter)

    def _create_console_logger(self, formatter):
        """创建控制台日志记录器"""
        logger = logging.getLogger("console")
        logger.setLevel(self.log_level)
        logger.propagate = False  # 防止日志传递给根记录器

        console_handler = logging.StreamHandler(stream=sys.stdout)
        web_handler = logging.StreamHandler(stream=output_stream)
        console_handler.setFormatter(formatter)
        web_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.addHandler(web_handler)
        return logger

    def _create_file_logger(self, formatter):
        """创建文件日志记录器"""
        logger = logging.getLogger("file")
        logger.setLevel(self.log_level)
        logger.propagate = False

        # 创建定时轮转文件处理器
        file_handler = TimedRotatingFileHandler(
            filename="log/vtb_dynamic.log",
            encoding="utf-8",
            when="midnight",
            interval=1,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def _log_message(self, level, msg, prefix="", color=""):
        """通用日志记录方法"""
        full_msg = prefix + msg

        # 记录到文件
        getattr(self.file_logger, level)(full_msg, stacklevel=3)

        # 记录到控制台（带颜色）
        if color:
            full_msg = color + full_msg + Style.RESET_ALL
        getattr(self.console_logger, level)(full_msg, stacklevel=3)

    def info(self, msg, prefix="", color=Fore.LIGHTGREEN_EX):
        self._log_message("info", msg, prefix, color)

    def debug(self, msg, prefix="", color=""):
        self._log_message("debug", msg, prefix, color)

    def warning(self, msg, prefix="", color=Fore.YELLOW):
        self._log_message("warning", msg, prefix, color)

    def error(self, msg, prefix="", color=Fore.RED):
        self.error_count.append(time())
        while len(self.error_count) and time() - self.error_count[0] > 3600:
            self.error_count.popleft()
        if len(self.error_count) == 10:
            from push import notify

            notify(
                "检测到大量报错",
                f"一小时内累计报错{len(self.error_count)}次，请检查运行状态",
            )

        self._log_message("error", msg, prefix, color)


logger = mylogger()
move_old_logs("log")
