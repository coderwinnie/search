#!/usr/bin/env python
# -*- coding:utf-8 -*-
from datetime import datetime
import time
from time import mktime
import asyncio
import psycopg2
import asyncpg
import logging
from conf.es_params_define import saas
from elasticsearch import Elasticsearch, helpers
from xml.etree import ElementTree as eTree
from elasticsearch_async import AsyncElasticsearch

from utils.get_conf import get_config_file, get_logger_file
from utils.common_sql import UserLib, AsyncLib, if_async, domain
from utils.time_utils import TimeUtils
from service.kafka2es.kafka2es import handle_body, revoke_es

# 创建logger实例
logger = logging.getLogger('es')

# 从配置文件读取pg相关信息
config = get_config_file()
pgconfig = config['postgresql']
host = pgconfig['host']
port = pgconfig['port']
user = pgconfig['user']
database = pgconfig['database']
password = pgconfig['password']


time_utils = TimeUtils()


def struct_time_2_datetime(struct):
    if isinstance(struct, time.struct_time):
        return datetime.fromtimestamp(mktime(struct))
    else:
        print('input type wrong {}'.format(type(struct)))
        return struct


class Prepare:
    def __init__(self, start_date, end_date):
        self.conn = psycopg2.connect(host=host, database=database, user=user, password=password, port=port)
        self.conn.autocommit = True
        start_date = time.strptime(start_date, '%Y-%m-%d')
        end_date = time.strptime(end_date, '%Y-%m-%d')
        self.start_date = start_date
        self.end_date = end_date
        # 获取backupinfo 最后一条消息的id 和 date
        maxes = self.get_backup_max_id()
        self.single_max_backup_id = maxes[0].get('id')
        self.single_max_backup_date = maxes[0].get('date')

        self.muc_max_backup_id = maxes[1].get('id')
        self.muc_max_backup_date = maxes[1].get('date')

        # 获取要查询的最后一条消息的id
        maxers = self.get_max_id(start=start_date, end=end_date)
        miners = self.get_min_id(start=start_date, end=end_date)  # 什么傻吊命名哈哈哈
        if maxers and miners:
            self.single_max_id = maxers[0]
            self.muc_max_id = maxers[1]
            self.single_min_id = miners[0]
            self.muc_min_id = miners[1]
        else:
            raise BaseException("NO MAXER OR ID FOUND, CHECK DATABASE")

        # 获取不入库的机器人id
        self.robot_list = self.get_robots()
        self.conn_str = 'postgres://{user}:{password}@{host}:{port}/{database}'.format(host=host,
                                                                                       database=database,
                                                                                       user=user,
                                                                                       password=password,
                                                                                       port=port)

        self.conn.close()

    def get_backup_max_id(self):
        res = []
        conn = self.conn
        cursor = conn.cursor()
        sql = """select a.id as sid, a.create_time as stime, b.id as mid, b.create_time as mtime from (select id,create_time from msg_history_backup order by create_time desc limit 1)a, (select id,create_time from muc_room_history_backup order by create_time desc limit 1)b"""
        cursor.execute(sql)
        rs = cursor.fetchall()
        for row in rs:
            # if not isinstance(row[0], int) or not isinstance(row[2], int):
            res.append(dict(id=row[0], date=row[1]))
            res.append(dict(id=row[2], date=row[3]))
            break
        return res

    def get_backup_max_id(self):
        res = []
        conn = self.conn
        cursor = conn.cursor()
        sql = """select a.id as sid, a.create_time as stime, b.id as mid, b.create_time as mtime from (select id,create_time from msg_history_backup order by create_time desc limit 1)a, (select id,create_time from muc_room_history_backup order by create_time desc limit 1)b"""
        cursor.execute(sql)
        rs = cursor.fetchall()
        for row in rs:
            # if not isinstance(row[0], int) or not isinstance(row[2], int):
            res.append(dict(id=row[0], date=row[1]))
            res.append(dict(id=row[2], date=row[3]))
            break
        return res

    def get_robots(self):
        res = []
        conn = self.conn
        cursor = conn.cursor()
        sql = """select user_id from host_users where user_type = 'R' or department = '/智能服务助手' """
        cursor.execute(sql)
        rs = cursor.fetchall()
        for row in rs:
            if row[0]:
                res.append(row[0])
        return res

    def get_max_id(self, start, end):
        res = []
        conn = self.conn
        cursor = conn.cursor()
        _start = datetime.fromtimestamp(time.mktime(start))
        _end = datetime.fromtimestamp(time.mktime(end))

        # 单人
        table = 'msg_history' if self.compare_date(end,
                                                   self.single_max_backup_date.timetuple()) else 'msg_history_backup'
        sql = """select id from {} where create_time > %(sdate)s and create_time < %(edate)s order by create_time desc limit 1;""".format(
            table)
        cursor.execute(sql, {'sdate': _start, 'edate': _end})
        rs = cursor.fetchall()
        for row in rs:
            res.append(row[0])
        # 群组
        table = 'muc_room_history' if self.compare_date(end,
                                                        self.single_max_backup_date.timetuple()) else 'muc_room_history_backup'
        sql = """select id from {} where create_time > %(sdate)s and create_time < %(edate)s order by create_time desc limit 1;""".format(
            table)
        cursor.execute(sql, {'sdate': _start, 'edate': _end})
        rs = cursor.fetchall()
        for row in rs:
            res.append(row[0])
        cursor.close()
        return res

    def get_min_id(self, start, end):
        res = []
        conn = self.conn
        cursor = conn.cursor()
        _start = datetime.fromtimestamp(time.mktime(start))
        _end = datetime.fromtimestamp(time.mktime(end))

        # 单人
        table = 'msg_history' if self.compare_date(start,
                                                   self.single_max_backup_date.timetuple()) else 'msg_history_backup'
        sql = """select id from {} where create_time > %(sdate)s and create_time < %(edate)s order by create_time asc limit 1;""".format(
            table)
        cursor.execute(sql, {'sdate': _start, 'edate': _end})
        rs = cursor.fetchall()
        for row in rs:
            res.append(row[0])
        # 群组
        table = 'muc_room_history' if self.compare_date(start,
                                                        self.single_max_backup_date.timetuple()) else 'muc_room_history_backup'
        sql = """select id from {} where create_time > %(sdate)s and create_time < %(edate)s order by create_time asc limit 1;""".format(
            table)
        cursor.execute(sql, {'sdate': _start, 'edate': _end})
        rs = cursor.fetchall()
        for row in rs:
            res.append(row[0])
        cursor.close()
        return res

    @staticmethod
    def compare_date(a, b):
        if time.mktime(a) - time.mktime(b) > 0:
            return True
        else:
            return False


class Single:
    def __init__(self, p):
        self.conn_str = p.conn_str
        self.start_id = p.single_min_id
        self.end_id = p.single_max_id
        self.single_diff = p.single_max_id - p.single_min_id
        self.backup_max = p.single_max_backup_id
        self.pagesize = p.pagesize
        self.start_date = struct_time_2_datetime(p.start_date)
        self.end_date = struct_time_2_datetime(p.end_date)
        self.id = None
        userlib = None
        if if_async:
            try:
                userlib = AsyncLib()
            except ConnectionError as e:
                # TODO 这里可能抓不到
                logger.error(e)
                try:
                    userlib = UserLib()
                except Exception as e:
                    logger.exception("POSTGRESQL INITIALIZATION FAILED {}".format(e))
                    raise TypeError("CANT FIND USERLIB")
            except Exception as e:
                logger.exception("POSTGRESQL INITIALIZATION FAILED {}".format(e))
                exit()
        else:
            userlib = UserLib()
        self.userlib = userlib

    async def get_msg(self):
        if not self.id:
            self.id = self.start_id
            if self.start_id > self.backup_max:
                table = "msg_history"
            else:
                table = "msg_history_backup"
        elif self.id + self.pagesize > self.end_id:
            table = ["msg_history_backup", "msg_history"]
        elif self.id > self.end_id:
            return
        elif self.id > self.backup_max:
            table = "msg_history"
        elif self.id <= self.backup_max:
            table = "msg_history_backup"
        else:
            table = 'msg_history_backup'

        result = {'s': []}
        pgconn = await asyncpg.connect(self.conn_str)

        if isinstance(table, list):
            sql = """select m_body,id,m_from,from_host, m_to, to_host, msg_id from {} where id > $1 and id <= $2 union all select m_body,id,m_from,m_to,msg_id from {} where id > $1 and id < $4 order by id asc limit $3 offset 0""".format(
                table[0], table[1])
            injection = [self.id, self.backup_max, self.pagesize, self.end_id]

        else:
            sql = """select m_body,id,m_from,from_host,m_to, to_host, msg_id from {} where id > $1 and id < $2 order by id asc limit $3 offset 0 """.format(
                table)
            injection = [self.id, self.end_id, self.pagesize]

        stmt = await pgconn.prepare(sql)
        for (m_body, __id, m_from, from_host, m_to, to_host, msg_id) in await stmt.fetch(*injection):
            res = dict()
            row = [m_body, __id, m_from, from_host, m_to, to_host, msg_id]
            row = ['' if x is None else x for x in row]
            res['body'] = row[0]
            res['id'] = row[1]
            res['from'] = row[2] + '@' + row[3]
            res['to'] = row[4] + '@' + row[5]
            res['msg_id'] = row[6]
            result['s'].append(res)
            if int(__id) > self.id:
                self.id = __id
        await pgconn.close()
        return result


class Muc:
    def __init__(self, p):
        self.conn_str = p.conn_str
        self.start_id = p.muc_min_id
        self.end_id = p.muc_max_id
        self.single_diff = p.muc_max_id - p.muc_min_id
        self.backup_max = p.muc_max_backup_id
        self.pagesize = p.pagesize
        self.start_date = struct_time_2_datetime(p.start_date)
        self.end_date = struct_time_2_datetime(p.end_date)

        self.id = None
        userlib = None
        if if_async:
            try:
                userlib = AsyncLib()
            except ConnectionError as e:
                # TODO 这里可能抓不到
                logger.error(e)
                try:
                    userlib = UserLib()
                except Exception as e:
                    logger.exception("POSTGRESQL INITIALIZATION FAILED {}".format(e))
                    raise TypeError("CANT FIND USERLIB")
            except Exception as e:
                logger.exception("POSTGRESQL INITIALIZATION FAILED {}".format(e))
                exit()
        else:
            userlib = UserLib()
        self.userlib = userlib

    async def get_msg(self):
        if not self.id:
            self.id = self.start_id
            if self.start_id > self.backup_max:
                table = "muc_room_history"
            else:
                table = "muc_room_history_backup"
        elif self.id + self.pagesize > self.end_id:
            table = ["muc_room_history_backup", "muc_room_history"]
        elif self.id > self.end_id:
            return
        elif self.id > self.backup_max:
            table = "muc_room_history"
        elif self.id <= self.backup_max:
            table = "muc_room_history_backup"
        else:
            table = 'muc_room_history_backup'

        result = {'m': []}

        pgconn = await asyncpg.connect(self.conn_str)

        if isinstance(table, list):
            sql = """select packet,id,muc_room_name,msg_id from {} where id > $1 and id <= $2 and create_time > $3 and create_time < $4 union all select packet,id,muc_room_name,msg_id from {} where id > $1 and id < $6 and create_time > $3 and create_time < $4 order by id asc limit $5 offset 0""".format(
                table[0], table[1])
            injection = [self.id, self.backup_max, self.start_date, self.end_date, self.pagesize, self.end_id]

        else:
            sql = """select packet,id,muc_room_name,msg_id from {} where id > $1 and id < $2 and create_time > $3 and create_time < $4 order by id asc limit $5 offset 0 """.format(
                table)
            injection = [self.id, self.end_id, self.start_date, self.end_date, self.pagesize]

        stmt = await pgconn.prepare(sql)
        for (packet, __id, muc_room_name, msg_id) in await stmt.fetch(*injection):
            if packet and __id:
                res = dict()
                row = [packet, __id, muc_room_name, msg_id]
                row = ['' if x is None else x for x in row]
                res['body'] = row[0]
                res['id'] = row[1]
                res['from'] = ''
                res['to'] = row[2]
                res['msg_id'] = row[3]
                result['m'].append(res)
                if int(__id) > self.id:
                    self.id = __id
        await pgconn.close()

        return result


class SingleES:
    def __init__(self):
        self.client = AsyncElasticsearch(hosts=saas)
        pass

    async def push_msgs(self, data, robot_list):
        if not data:
            return
        for _msg in data:
            try:
                msg = _msg.get('body')
                root = eTree.fromstring(msg)
                _chattype = root.get('type')
                if _chattype not in ['chat', 'revoke', 'consult']:
                    logger.info('extra type found {}'.format(_chattype))
                    continue
                _chattype = root.get('type')
                if _chattype not in ['chat', 'groupchat', 'revoke', 'consult']:
                    continue
                _from = _msg.get("from")
                if '@' not in _from:
                    _from = _from + '@' + domain
                _to = _msg.get("to")
                if '@' not in _to:
                    _to = _to + '@' + domain
                _time = root.attrib['msec_times']  # time 1542877246165 ms 可能是int
                body = root.find("body")
                _body = body.text
                _mtype = body.attrib["msgType"]
                _id = _msg.get('id')
                _conversation = sorted([_from, _to])[0] + '_' + sorted([_from, _to])[1]
                _msg_id = _msg.get('msg_id')
                doc_type = 'message'
                if '@' in _from:
                    if _from.split('@')[0] in robot_list:
                        continue
                elif _from in robot_list:
                    continue
                if 'sendjid' in root.attrib:
                    _realfrom = root.attrib.get('sendjid', _from)
                elif 'realfrom' in root.attrib:
                    _realfrom = root.attrib.get('realfrom', _from)
                else:
                    _realfrom = _from
                if 'realto' in root.attrib:
                    _realto = root.attrib.get('realto', _to)
                else:
                    _realto = _to
                if _chattype == 'chat':
                    doc_body = {
                        'msg': msg,
                        'body': _body,
                        'raw_body': _body,
                        'msgid': _msg_id,
                        'id': _id,
                        'from': _from,
                        'to': _to,
                        'conversation': _conversation,
                        'realfrom': _realfrom,
                        'realto': _realto,
                        'mtype': _mtype,
                        'time': _time,
                        'doc_type': doc_type,
                        'chat_type': _chattype
                    }
                    if _chattype == 'consult':
                        _qchatid = root.attrib.get('qchatid', None)
                        if not _qchatid:
                            continue
                        doc_body['qchatid'] = _qchatid
                    extendinfo = body.attrib.get("extendInfo", "")
                    if extendinfo:
                        extend_dict = {'extendinfo': extendinfo}
                        doc_body = {**doc_body, **extend_dict}
                    year, mon = time_utils.get_specific_ymd(_time)
                    es_index = 'message_' + str(year) + '_' + str(mon)
                    if await self.check_exist(index=es_index, _id=_id, doc_type="message"):
                        continue
                    handle_body(doc_body)
                elif _chattype == 'revoke':
                    doc_body = {
                        'msg': _msg,
                        'body': '',
                        'raw_body': '[撤回一条消息]',
                        'msgid': _msg_id,
                        'id': _id,
                        'from': _from,
                        'to': _to,
                        'conversation': _conversation,
                        'mtype': '-1',
                        'time': _time,
                        'doc_type': doc_type,
                        'chat_type': _chattype
                    }
                    year, mon = time_utils.get_specific_ymd(_time)
                    es_index = 'message_' + str(year) + '_' + str(mon)
                    revoke_es(es_index, doc_body)
                elif _chattype == 'consult':
                    doc_body = {
                        'msg': msg,
                        'body': _body,
                        'raw_body': _body,
                        'msgid': _msg_id,
                        'id': _id,
                        'from': _from,
                        'to': _to,
                        'conversation': _conversation,
                        'realfrom': _realfrom,
                        'realto': _realto,
                        'mtype': _mtype,
                        'time': _time,
                        'doc_type': doc_type,
                        'chat_type': _chattype,
                    }
                    if _chattype == 'consult':
                        _qchatid = root.attrib.get('qchatid', None)
                        if not _qchatid:
                            continue
                        doc_body['qchatid'] = _qchatid

                    extendinfo = body.attrib.get("extendInfo", "")
                    if extendinfo:
                        extend_dict = {'extendinfo': extendinfo}
                        doc_body = {**doc_body, **extend_dict}
                    year, mon = time_utils.get_specific_ymd(_time)
                    es_index = 'message_' + str(year) + '_' + str(mon)
                    await self.delete_msg(index=es_index, _id=_id, doc_type="message")
                    handle_body(doc_body)

            except Exception as e:
                logger.exception(e)
                continue

    async def check_exist(self, index, _id, doc_type="message"):
        return self.client.exists(index=index, id=_id, doc_type=doc_type)

    async def delete_msg(self, index, _id, doc_type="message"):
        return self.client.delete(index=index, id=_id, doc_type=doc_type)


class MucES:

    def __init__(self):
        pass

    async def push_msgs(self, data, robot_list):
        if not data:
            return
        for _msg in data:
            try:
                msg = _msg.get('body')
                root = eTree.fromstring(msg)
                _chattype = root.get('type')
                if _chattype not in ['groupchat', 'revoke']:
                    logger.info('extra type found {}'.format(_chattype))
                    continue
                _chattype = root.get('type')
                # _to = root.attrib.get('to')
                _to = _msg.get('to')
                if '@' not in _to:
                    _to = _to + '@conference.' + domain
                _time = root.attrib['msec_times']  # time 1542877246165 ms 可能是int
                body = root.find("body")
                _body = body.text
                _mtype = body.attrib["msgType"]
                _id = _msg.get('id')
                _msg_id = _msg.get('msg_id')
                doc_type = 'muc_msg'

                if 'sendjid' in root.attrib:
                    _realfrom = root.attrib.get('sendjid', '')
                elif 'realfrom' in root.attrib:
                    _realfrom = root.attrib.get('realfrom', '')
                else:
                    _realfrom = root.attrib.get('from').rsplit('/')[-1]
                if '@' not in _realfrom:
                    _realfrom = _realfrom + '@' + domain
                _from = _realfrom
                if '@' in _realfrom:
                    if _realfrom.split('@')[0] in robot_list:
                        continue
                elif _realfrom in robot_list:
                    continue
                if 'realto' in root.attrib:
                    _realto = root.attrib['realto']
                else:
                    _realto = _to
                _conversation = _from + '_' + _to
                if _chattype == 'groupchat':
                    doc_body = {
                        'msg': msg,
                        'body': _body,
                        'raw_body': _body,
                        'msgid': _msg_id,
                        'id': _id,
                        'from': _from,
                        'to': _to,
                        'conversation': _conversation,
                        'realfrom': _realfrom,
                        'realto': _realto,
                        'mtype': _mtype,
                        'time': _time,
                        'doc_type': doc_type,
                        'chat_type': _chattype

                    }
                    extendinfo = body.attrib.get("extendInfo", "")
                    if extendinfo:
                        extend_dict = {'extendinfo': extendinfo}
                        doc_body = {**doc_body, **extend_dict}
                    handle_body(doc_body)
                elif _chattype == 'revoke':
                    doc_body = {
                        'msg': _msg,
                        'body': '',
                        'raw_body': '[撤回一条消息]',
                        'msgid': _msg_id,
                        'id': _id,
                        'from': _from,
                        'to': _to,
                        'conversation': _conversation,
                        'mtype': '-1',
                        'time': _time,
                        'doc_type': doc_type,
                        'chat_type': _chattype
                    }
                    year, mon = time_utils.get_specific_ymd(_time)
                    es_index = 'message_' + str(year) + '_' + str(mon)
                    revoke_es(es_index, doc_body)
            except Exception as e:
                logger.exception(e)
                continue


