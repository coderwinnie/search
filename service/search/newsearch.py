#!/usr/bin/env python
# -*- coding:utf-8 -*-
__author__ = 'jingyu.he'

from flask import Flask, request, jsonify, Blueprint
import json
import requests
import asyncio
import threading
import time
from conf.constants import is_check_ckey, auth_ckey_url, if_cached
from conf.search_params_define import *
from utils.request_util import RequestUtil
# from utils.common_sql import UserLib
from utils.lookback import Lookback
from utils.redis_utils import RedisUtil
from service.search.contact import Contact

# from service.search.lookback_es import lookback
# from service.search.lookback_sql import lookback


search_blueprint = Blueprint('search', __name__)

# -------------------------- 生成logger --------------------------
log_path = get_logger_file(name='search.log')
search_logger = configure_logger('search', log_path)

# -------------------------- 读取默认配置 --------------------------
if is_check_ckey:
    search_logger.info("CKEY AUTHORIZATION INITIALING...")
    from utils.authorization import check_ckey
# -------------------------- 既定的配置 --------------------------

ip = str()
s_args = dict()
l_args = dict()


def get_pinyin():
    global pinyin_name
    threading.Timer(86400, get_pinyin).start()
    # TODO:加入配置检查
    init = Lookback()
    pinyin_name = init.get_name()  # 方便转换拼音和中文名
    init.conn.close()


def authorization(func):
    def wrapper(*args, **kw):
        ckey = ''
        user_id = 'DEFAULT'
        request_util = RequestUtil()
        res = False
        if is_check_ckey:
            ckey = request_util.get_ckey(request)
            if ckey:
                if auth_ckey_url:
                    try:
                        r_data = {
                            'ckey': ckey,
                            'system': 'search'
                        }
                        ret = requests.post(url=auth_ckey_url, json=r_data)
                        if ret.json().get('ret'):
                            if ret.json().get('data').get('d') != r_domain:
                                return jsonify(ret=0, message="Error domain")
                            res = True
                            user_id = ret.json().get('data').get('u')
                    except (requests.RequestException or KeyError) as e:
                        search_logger.error("ckey api failed : {}".format(e))
                        # TODO notify developer to check
                        # res = check_ckey(ckey, user_id)
                        res, user_id = check_ckey(ckey)
                    except Exception as e:
                        search_logger.error("ckey api failed : {}".format(e))
                else:
                    res, user_id = check_ckey(ckey)
            if res:
                return func(user_id=user_id, *args, **kw)
            else:
                search_logger.info("user:{user} login failed, ckey : {ckey}, \
                                                ".format(user=user_id, ckey=ckey))
                return jsonify(ret=0, message="ckey check failed")
        return func(user_id=user_id, *args, **kw)

    wrapper.__name__ = func.__name__
    return wrapper


@search_blueprint.route('/search', methods=['GET', 'POST'])
@authorization
def main(user_id):
    # 记录每个ip 每次搜索的最后一次请求
    global ip, s_args
    request_ip = request.remote_addr
    args = RequestUtil.get_request_args(request)
    if not s_args:
        s_args = args
    if ip != request_ip:
        ip = request_ip
        search_logger.info(ip + ' :  {}'.format(json.dumps(s_args, ensure_ascii=False,indent=4)))
    s_args = args

    # 将str的action转为二进制 按照define里的定义长度
    _group_id = args.get("groupId", 0)
    action = ''
    if (_group_id or _group_id == '') and 'action' not in args:
        if _group_id == '':
            action = '7'
        elif _group_id == 'Q01':
            action = '1'
        elif _group_id == 'Q02':
            action = '2'
        elif _group_id == 'Q07':
            action = '4'
    elif ('action' not in args) and ('groupId' not in args):
        if args.get('platform').lower() == 'ios':  # 此处等ios兼容后就删掉
            action = '7'
        else:
            return jsonify(ret=0, message="WRONG ACTION")
    else:
        action = args.get("action", "NONE")
    try:
        if isinstance(action, str):
            action = format(int(action), "b")
        _register = dict()
        register_len = len(TYPE_REGISTER)
        for _p, _n in enumerate(action[-1: -1 - register_len: -1]):
            _register[TYPE_REGISTER[_p]] = (_n == '1')
    except (KeyError, ValueError, TypeError):
        return jsonify(ret=0, message="WRONG ACTION")

    # 获取相关任务准备进行协程分配
    register = [k for k, v in _register.items() if v is True]
    if_contact = []
    if_lookback = []
    for t in register:
        if t in ACTION_REGISTER['contact']:
            if_contact.append(t)
        if t in ACTION_REGISTER['lookback']:
            if_lookback.append(t)

    # 搜索关键词限制
    if if_contact:
        _key = args.get('key', '').strip()
        if len(_key) < 2:
            return jsonify(ret=0, message="key is illegal")
        elif len(_key) > 20:
            args['key'] = _key[:20]
            # TODO 或许要加上剪切提示
    if if_cached:
        redis_util = RedisUtil()
        user_habit = redis_util.get_user_habit(user_id=user_id)
    else:
        user_habit = ''
    # if _key in
    data = asyncio.run(
        go_coro(if_contact=if_contact, if_lookback=if_lookback, args=args, user=user_id, habit=user_habit))
    # TODO： data处理
    return jsonify(errcode=0, msg='', data=data)


async def go_coro(if_contact, if_lookback, args, user, habit):
    contact = ''
    lookback = ''
    tasks = []
    if if_contact:
        contact = Contact(user_id=user, args=args, habit=habit)
        for todo in if_contact:
            t = asyncio.create_task(contact.router[todo](user))
            tasks.append(t)
    if if_lookback:
        lookback = Lookback(user=user, args=args)
        for todo in if_lookback:
            t = asyncio.create_task(lookback.router[todo](user))
            tasks.append(t)
    completed, pending = await asyncio.wait(tasks, timeout=3)
    for pen in pending:
        search_logger.error("PENDING TASK FOUND {}".format(pen))
        pen.cancel()
    result = []
    for com in completed:
        # t = com.result()
        result.append(com.result())

    # 关闭数据库连接
    if contact:
        contact.userlib.close()
    return result


async def lookback(user_id, args):
    lookback = Lookback()
    args = RequestUtil.get_request_args(request)
    term = args.get('term')
    pagesize = args.get('pagesize')
    offset = args.get('offset')
    action = args.get('action', '')
    if action:
        search_logger.info("using old interface, params:" + args)
    method = args.get('method')
    if method == 'search_muc':
        has_more, count, ret = lookback.search_muc(user_id=user_id, term=term, pagesize=pagesize, offset=offset)
    elif method == 'search_single':
        has_more, count, ret = lookback.search_single(user_id=user_id, term=term, pagesize=pagesize, offset=offset)
    else:
        has_more, count, ret = '', '', ''
    return jsonify(ret=0, data=ret, errmsg='', errcode=0, total=count, hasMore=has_more)


class HandleHabit:
    def __init__(self, user_id):
        self.router = {
            'user': self.search_user,
            'muc': self.search_group,
            'common_muc': self.search_common_group,
            'ELSE': lambda x: search_logger.exception("COMMAND {} NOT FOUND ".format(x))
        }

    def handle_single_habit(self, habit):
        res = habit['searchSingle']
