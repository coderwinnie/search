#!/usr/bin/env python
# -*- coding:utf-8 -*-
import time
import asyncio
from tools.remake_msg_utils import Prepare, Single, Muc, SingleES, MucES

# 开始日期 结束日期 睡眠间隔 切片大小
START_DATE = '2018-12-01'
END_DATE = '2018-12-31'

INTERVAL = 2  # second
SLICE = 10000  # 1000 条
ROBOTS = [] # 添加机器人消息黑名单
POTENTIAL = {} # 添加黑名单用户
ALL_USERS = [] # 所有用户
ROBOTS = ROBOTS + [x for x in POTENTIAL if x not in ALL_USERS]
print(ROBOTS)
p = Prepare(START_DATE, END_DATE)
p.pagesize = SLICE
robot_list = set(p.robot_list + ROBOTS)
print(p.__dict__)
# 获取最大值最小值

single = Single(p)
muc = Muc(p)
single_es = SingleES()
muc_es = MucES()



async def go_db_coro():
    tasks = []
    single_coro = asyncio.create_task(single.get_msg())
    muc_coro = asyncio.create_task(muc.get_msg())
    tasks.append(single_coro)
    tasks.append(muc_coro)
    completed, pending = await asyncio.wait(tasks, timeout=10)
    for pen in pending:
        print("PENDING TASK FOUND {}".format(pen))
        pen.cancel()
    result = {}
    for com in completed:
        # t = com.result()
        if com.result():
            if isinstance(com.result(), dict):
                result = {**result, **com.result()}
            else:
                continue
            # result.append(com.result())
    return result


async def go_es_coro(_data, robot_list):
    tasks = []
    single_es_coro = asyncio.create_task(single_es.push_msgs(_data.get('s'), robot_list))
    muc_es_coro = asyncio.create_task(muc_es.push_msgs(_data.get('m'), robot_list))
    tasks.append(single_es_coro)
    tasks.append(muc_es_coro)
    completed, pending = await asyncio.wait(tasks, timeout=10)
    for pen in pending:
        print("PENDING TASK FOUND {}".format(pen))
        pen.cancel()
    result = []
    for com in completed:
        # t = com.result()
        if com.result():
            result.append(com.result())
    return result


while True:
    data = asyncio.run(go_db_coro())
    if not data or (not data.get('s') and not data.get('m')):
        break
    # for d in data:
    #     go_es = asyncio.run(go_es_coro(d))
    go_es = asyncio.run(go_es_coro(data, robot_list))

    time.sleep(INTERVAL)
