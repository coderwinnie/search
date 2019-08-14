#!/usr/bin/env python
# -*- coding:utf-8 -*-
import json
import requests
import random
from flask import Blueprint, request, jsonify, Flask, render_template
from conf.rtc_params_define import *
from service.videos.global_room import globalRoom
from utils.redis_utils import redis_cli
from utils.request_util import RequestUtil
from utils.rtc_utils import Room, Client, Utility

all_room = globalRoom.all_room
room = Room()
request_util = RequestUtil()
rtc_utils = Utility()
rtc_blueprint = Blueprint('rtc', __name__, template_folder='../../templates', static_folder='../../static',
                          url_prefix='rtc')
log_path = get_logger_file(name='rtc.log')
rtc_logger = configure_logger('rtc', log_path)


@rtc_blueprint.route('/', methods=['GET'])
def main():
    __args = dict(request_util.get_request_args(request=request))
    __args['User-Agent'] = request.headers['User-Agent']
    __args['request'] = request
    __params = rtc_utils.get_room_parameters(request=__args, room_id=None, client_id=None, is_initiator=None)
    return render_template('index_template.html', **__params)


@rtc_blueprint.route('/echo', methods=['GET'])
def echo():
    return 'OK'


@rtc_blueprint.route('/join/<room_id>', methods=['GET', 'POST'])
def join(room_id):
    args = request_util.get_request_args(request)
    if args:
        args = dict(args)
        args['User-Agent'] = request.headers['User-Agent']
        args['request'] = request
    else:
        args = {'User-Agent': request.headers['User-Agent'], 'request': request}

    def write_response(__result, __params, messages):
        __params['messages'] = messages
        result_text = json.dumps({
            'result': __result,
            'params': __params
        }, ensure_ascii=False)
        return result_text

    def write_room_parameters(__room_id, __client_id, messages, is_initiator):
        __params = rtc_utils.get_room_parameters(request=args, room_id=__room_id, client_id=__client_id,
                                                 is_initiator=is_initiator)
        return write_response('SUCCESS', __params, messages)

    client_id = args.get('client_id')
    if not client_id:
        client_id = rtc_utils.generate_random(length=8)
    key = rtc_utils.get_memcache_key_for_room(request.host_url, room_id)
    result = Room().new_add_client_to_room(client_id=client_id, room_key=key)
    if result['error'] is not None:
        rtc_logger.info('Error adding client to room: ' + result['error'] + \
                        ', room_state=' + result['room_state'])
        write_response(result['error'], {}, [])
        return result['error']

    redis_cli.set(name=REDIS_PREFIX_KEY + key, value=json.dumps(all_room[key], ensure_ascii=False), ex=86400)

    __result = write_room_parameters(
        room_id, client_id, result['messages'], result['is_initiator'])
    rtc_logger.info('User ' + client_id + ' joined room ' + room_id)
    rtc_logger.info('Room ' + room_id + ' has state ' + result['room_state'])
    return __result


@rtc_blueprint.route('/leave/<room_id>/<client_id>', methods=['GET', 'POST'])
def leave(room_id, client_id):
    result = Room().new_remove_client_from_room(room_key=room_id, client_id=client_id)
    if result['error']:
        rtc_logger.error(result['error'])
        rtc_logger.error('Room {} has state {}'.format(room_id, result['room_state']))
    return jsonify(ret=True, data=json.dumps(result))


@rtc_blueprint.route('/message/<room_id>/<client_id>', methods=['GET', 'POST'])
def message(room_id, client_id):
    # global all_room

    def write_response(__result):
        content = json.dumps({'result': __result})
        return content

    def send_message_to_collider(room_id, client_id, message):
        rtc_logger.info('Forwarding message to collider for room ' + room_id +
                        ' client ' + client_id)
        wss_url, wss_post_url = rtc_utils.get_wss_parameters(request)
        url = wss_post_url + '/' + room_id + '/' + client_id
        rtc_logger.warning('url is %s', url)
        result = requests.post(url=url,
                               json=message)
        if result.status_code != 200:
            rtc_logger.error(
                'Failed to send message to collider: {}'.format(result.status_code))
            # TODO(tkchin): better error handling.
            # self.error(500)
            return jsonify(errcode=500)
        __content = write_response(RESPONSE_SUCCESS)
        return __content

    def save_message_from_client(host, room_id, client_id, message):
        # global all_room
        text = message
        key = rtc_utils.get_memcache_key_for_room(host, room_id)
        __room = all_room.get(key)
        if not __room:
            __room = redis_cli.get(name=REDIS_PREFIX_KEY + key)
            if not __room:
                rtc_logger.warning('Unknown room: ' + room_id)
                return {'error': RESPONSE_UNKNOWN_ROOM, 'saved': False}
            else:
                __room = json.loads(__room)
                all_room[room_id] = __room

        if client_id not in __room.keys():
            rtc_logger.warning('{}'.format(__room.keys()))
            rtc_logger.warning('Unknown client: ' + client_id)
            return {'error': RESPONSE_UNKNOWN_CLIENT, 'saved': False}

        # 已经有2个人 room full
        if len(__room) > 1:
            return {'error': None, 'saved': False}

        all_room[room_id].get(client_id)['messages'].append(json.dumps(text, ensure_ascii=False))
        redis_cli.set(name=REDIS_PREFIX_KEY + key, value=json.dumps(all_room[room_id], ensure_ascii=False), ex=86400)
        return {'error': None, 'saved': True}

    message_json = json.loads(request.data.decode('utf8'))
    result = save_message_from_client(
        request.host_url, room_id, client_id, message_json)
    if result and result['error'] is not None:
        write_response(result['error'])
        return 'error'
    if not result['saved']:
        rtc_logger.warning('not saved')
        __content = send_message_to_collider(room_id, client_id, message_json)
    else:
        rtc_logger.warning('saved and writing success')
        __content = write_response(RESPONSE_SUCCESS)
    return __content


@rtc_blueprint.route('/params', methods=['GET', 'POST'])
def params():
    args = dict(request_util.get_request_args(request))
    args['User-Agent'] = request.headers['User-Agent']
    args['request'] = request
    __params = rtc_utils.get_room_parameters(args, None, None, None)
    return json.dumps(__params)


@rtc_blueprint.route('/r/<room_id>', methods=['GET', 'POST'])
def room(room_id):
    # global all_room
    args = dict(request_util.get_request_args(request))
    args['User-Agent'] = request.headers['User-Agent']
    args['request'] = request
    # __room = redis_cli.get(name=rtc_utils.get_memcache_key_for_room(request.host_url, room_id))
    key = rtc_utils.get_memcache_key_for_room(request.host_url, room_id)
    __room = all_room.get(key)
    if __room:
        rtc_logger.info('Room ' + room_id + ' has state ' + str(__room))
        if len(__room) >= 2:
            rtc_logger.info('Room ' + room_id + ' is full')
            return render_template('full_template.html')
    else:
        __room = redis_cli.get(name=REDIS_PREFIX_KEY + key)
        if __room:
            __room = json.loads(__room)
            all_room[room_id] = __room
        else:
            __room = Room().get_new_room(key=key)
            all_room[key] = __room

    __params = rtc_utils.get_room_parameters(args, room_id, None, None)
    return render_template('index_template.html', **__params)
