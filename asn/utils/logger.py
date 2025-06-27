import os
import logging
import time
import sys

def set_logger(name="default", log_folder="log/", level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if log_folder == "":
        # stdout handler
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(level)
        stdout_handler.setFormatter(logging.Formatter("---%(asctime)s %(levelname)s \n%(message)s ---\n\n"))
        logger.addHandler(stdout_handler)
    else:
        # clear log folder
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        # else:
        #     for file in os.listdir(log_folder):
        #         os.remove(os.path.join(log_folder, file))
        # debug logfile handler
        # logfile_handler = logging.FileHandler(os.path.join(log_folder, "debug.log"), encoding='utf-8')
        logfile_handler = logging.FileHandler(os.path.join(log_folder, "debug_{time}.log".format(time=time.strftime("%m%d-%H%M-%S", time.localtime()))), encoding='utf-8')
        logfile_handler.setLevel(logging.DEBUG)
        logfile_handler.setFormatter(logging.Formatter("---%(asctime)s %(levelname)s \n%(message)s ---\n\n"))
        logger.addHandler(logfile_handler)
        # info logfile handler
        logfile_handler = logging.FileHandler(os.path.join(log_folder, "info_{time}.log".format(time=time.strftime("%m%d-%H%M-%S", time.localtime()))), encoding='utf-8')
        logfile_handler.setLevel(logging.INFO)
        logfile_handler.setFormatter(logging.Formatter("---%(asctime)s %(levelname)s \n%(message)s ---\n\n"))
        logger.addHandler(logfile_handler)
    return logger

def get_logger(name="default"):
    # 如果不存在logger，则创建一个新的logger
    if not logging.getLogger(name):
        set_logger(name)
    return logging.getLogger(name)
