# -*- coding: utf-8 -*-
import logging
import os
from decimal import *
from enum import Enum
from logging.handlers import RotatingFileHandler

import pandas as pd

from zvt import LOG_PATH
from zvt.utils.time_utils import to_time_str

getcontext().prec = 16

logger = logging.getLogger(__name__)

none_values = ['不变', '--', '-', '新进']
zero_values = ['不变', '--', '-', '新进']


def first_item_to_float(the_list):
    return to_float(the_list[0])


def second_item_to_float(the_list):
    return to_float(the_list[1])


def add_func_to_value(the_map, the_func):
    for k, v in the_map.items():
        the_map[k] = (v, the_func)
    return the_map


def to_float(the_str, default=None):
    if not the_str:
        return default
    if the_str in none_values:
        return None

    if '%' in the_str:
        return pct_to_float(the_str)
    try:
        scale = 1.0
        if the_str[-2:] == '万亿':
            the_str = the_str[0:-2]
            scale = 1000000000000
        elif the_str[-1] == '亿':
            the_str = the_str[0:-1]
            scale = 100000000
        elif the_str[-1] == '万':
            the_str = the_str[0:-1]
            scale = 10000
        if not the_str:
            return default
        return float(Decimal(the_str.replace(',', '')) * Decimal(scale))
    except Exception as e:
        logger.error('the_str:{}'.format(the_str))
        logger.exception(e)
        return default


def pct_to_float(the_str, default=None):
    if the_str in none_values:
        return None

    try:
        return float(Decimal(the_str.replace('%', '')) / Decimal(100))
    except Exception as e:
        logger.exception(e)
        return default


def json_callback_param(the_str):
    return eval(the_str[the_str.index("(") + 1:the_str.index(")")])


def fill_domain_from_dict(the_domain, the_dict: dict, the_map: dict):
    if not the_map:
        the_map = {}
        for k in the_dict:
            the_map[k] = (k, lambda x: x)

    for k, v in the_map.items():
        if isinstance(v, tuple):
            field_in_dict = v[0]
            the_func = v[1]
        else:
            field_in_dict = v
            the_func = to_float

        the_value = the_dict.get(field_in_dict)
        if the_value is not None:
            to_value = the_value
            if to_value in none_values:
                setattr(the_domain, k, None)
            else:
                result_value = the_func(to_value)
                setattr(the_domain, k, result_value)
                exec('the_domain.{}=result_value'.format(k))


def init_process_log(file_name, log_dir=LOG_PATH):
    root_logger = logging.getLogger()

    # reset the handlers
    root_logger.handlers = []

    root_logger.setLevel(logging.INFO)

    if log_dir:
        file_name = os.path.join(log_dir, file_name)

    fh = RotatingFileHandler(file_name, maxBytes=524288000, backupCount=10)

    fh.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        "%(levelname)s  %(threadName)s  %(asctime)s  %(name)s:%(lineno)s  %(funcName)s  %(message)s")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    root_logger.addHandler(fh)
    root_logger.addHandler(ch)


SUPPORT_ENCODINGS = ['GB2312', 'GBK', 'GB18030', 'UTF-8']


def read_csv(f, encoding, sep=None, na_values=None):
    encodings = [encoding] + SUPPORT_ENCODINGS
    for encoding in encodings:
        try:
            if sep:
                return pd.read_csv(f, sep=sep, encoding=encoding, na_values=na_values)
            else:
                return pd.read_csv(f, encoding=encoding, na_values=na_values)
        except UnicodeDecodeError as e:
            logger.warning('read_csv failed by using encoding:{}'.format(encoding), e)
            f.seek(0)
            continue
    return None


def marshal_object_for_ui(object):
    if isinstance(object, Enum):
        return object.value

    if isinstance(object, pd.Timestamp):
        return to_time_str(object)

    return object
