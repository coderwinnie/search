#!/usr/bin/env python
# -*- coding:utf-8 -*-
import json
import os
import random
import collections
from conf.rtc_params_define import *
from service.videos.global_room import globalRoom
from utils.redis_utils import redis_cli

all_room = globalRoom.all_room

log_path = get_logger_file(name='rtc.log')
rtc_logger = configure_logger('rtc', log_path)


class Utility:
    def __init__(self):
        self.redis_cli = redis_cli

    def __iter__(self):
        pass

    def get_memcache_key_for_room(self, host, room_id):
        # return '{}/{}'.format(host, room_id)
        return '{}'.format(room_id)

    def generate_random(self, length=9):
        client_id = ''
        for _ in range(length):
            client_id += random.choice('0123456789')
        return client_id

    def get_hd_default(self, user_agent):
        if 'Android' in user_agent or 'Chrome' not in user_agent:
            return False
        return True

    def make_pc_config(self, ice_transports, ice_server_override):
        config = {
            'iceServers': [],
            'bundlePolicy': 'max-bundle',
            'rtcpMuxPolicy': 'require'
        }
        if ice_server_override:
            config['iceServers'] = ice_server_override
        if ice_transports:
            config['iceTransports'] = ice_transports
        return config

    def add_media_track_constraint(self, track_constraints, constraint_string):
        tokens = constraint_string.split(':')
        mandatory = True
        if len(tokens) == 2:
            # If specified, e.g. mandatory:minHeight=720, set mandatory appropriately.
            mandatory = (tokens[0] == 'mandatory')
        else:
            # Otherwise, default to mandatory, except for goog constraints, which
            # won't work in other browsers.
            mandatory = not tokens[0].startswith('goog')

        tokens = tokens[-1].split('=')
        if len(tokens) == 2:
            if mandatory:
                track_constraints['mandatory'][tokens[0]] = tokens[1]
            else:
                track_constraints['optional'].append({tokens[0]: tokens[1]})
        else:
            raise ValueError('Ignoring malformed constraint: ' + constraint_string)

    def make_media_track_constraints(self, constraints_string):
        if not constraints_string or constraints_string.lower() == 'true':
            track_constraints = True
        elif constraints_string.lower() == 'false':
            track_constraints = False
        else:
            track_constraints = {'mandatory': {}, 'optional': []}
            for constraint_string in constraints_string.split(','):
                self.add_media_track_constraint(track_constraints, constraint_string)

        return track_constraints

    def make_media_stream_constraints(self, audio, video, firefox_fake_device):
        stream_constraints = (
            {'audio': self.make_media_track_constraints(audio),
             'video': self.make_media_track_constraints(video)})
        if firefox_fake_device:
            stream_constraints['fake'] = True
        rtc_logger.info('Applying media constraints: ' + str(stream_constraints))
        return stream_constraints

    def get_version_info(self):
        try:
            path = os.path.join(os.path.dirname(__file__), 'version_info.json')
            f = open(path)
            if f is not None:
                try:
                    return json.load(f)
                except ValueError as e:
                    rtc_logger.warning('version_info.json cannot be decoded: ' + str(e))
        except IOError as e:
            rtc_logger.info('version_info.json cannot be opened: ' + str(e))
        return None

    def make_pc_constraints(self, dtls, dscp, ipv6):
        constraints = {'optional': []}
        self.maybe_add_constraint(constraints, dtls, 'DtlsSrtpKeyAgreement')
        self.maybe_add_constraint(constraints, dscp, 'googDscp')
        self.maybe_add_constraint(constraints, ipv6, 'googIPv6')

        return constraints

    def maybe_add_constraint(self, constraints, param, constraint):
        if param and param.lower():
            constraints['optional'].append({constraint: True})
        elif param and not param.lower():
            constraints['optional'].append({constraint: False})

        return constraints

    def get_wss_parameters(self, request):
        wss_host_port_pair = request.get('wshpp','')
        wss_tls = request.get('wstls','')

        if not wss_host_port_pair:
            # Attempt to get a wss server from the status provided by prober,
            # if that fails, use fallback value.

            wss_active_host = self.redis_cli.get(WSS_HOST_ACTIVE_HOST_KEY)
            # wss_active_host = pickle.loads(WSS_HOST_ACTIVE_HOST_KEY)

            if wss_active_host in WSS_HOST_PORT_PAIRS:
                wss_host_port_pair = wss_active_host
            else:
                rtc_logger.warning(
                    'Invalid or no value returned from memcache, using fallback: '
                    + json.dumps(wss_active_host))
                wss_host_port_pair = WSS_HOST_PORT_PAIRS[0]

        if wss_tls and wss_tls == 'false':
            wss_url = 'ws://' + wss_host_port_pair + '/ws'
            wss_post_url = 'http://' + wss_host_port_pair
        else:
            wss_url = 'wss://' + wss_host_port_pair + '/ws'
            wss_post_url = 'https://' + wss_host_port_pair
        return wss_url, wss_post_url

    def get_room_parameters(self, request, room_id, client_id, is_initiator):
        __request = request['request']
        error_messages = []
        warning_messages = []
        # Get the base url without arguments.
        # base_url = request.base_url
        # user_agent = request.headers['User-Agent']
        user_agent = request.get('User-Agent', '')

        # HTML or JSON.
        response_type = request.get('t')
        # Which ICE candidates to allow. This is useful for forcing a call to run
        # over TURN, by setting it=relay.
        ice_transports = request.get('it')
        # Which ICE server transport= to allow (i.e., only TURN URLs with
        # transport=<tt> will be used). This is useful for forcing a session to use
        # TURN/TCP, by setting it=relay&tt=tcp.
        ice_server_transports = request.get('tt')
        # A HTTP server that will be used to find the right ICE servers to use, as
        # described in http://tools.ietf.org/html/draft-uberti-rtcweb-turn-rest-00.
        ice_server_base_url = request.get('ts', ICE_SERVER_BASE_URL)

        # 从args里获取是否开启音频， 是否开启视频
        audio = request.get('audio')
        video = request.get('video')

        # Pass firefox_fake_device=1 to pass fake: true in the media constraints,
        # which will make Firefox use its built-in fake device.
        firefox_fake_device = request.get('firefox_fake_device')

        # The hd parameter is a shorthand to determine whether to open the
        # camera at 720p. If no value is provided, use a platform-specific default.
        # When defaulting to HD, use optional constraints, in case the camera
        # doesn't actually support HD modes.
        hd = request.get('hd', '').lower()
        if hd and video:
            message = 'The "hd" parameter has overridden video=' + video
            rtc_logger.warning(message)
            # HTML template is UTF-8, make sure the string is UTF-8 as well.
            warning_messages.append(message.encode('utf-8'))
        if hd == 'true':
            video = 'mandatory:minWidth=1280,mandatory:minHeight=720'
        elif not hd and not video and self.get_hd_default(user_agent) == 'true':
            video = 'optional:minWidth=1280,optional:minHeight=720'

        if request.get('minre') or request.get('maxre'):
            message = ('The "minre" and "maxre" parameters are no longer ' +
                       'supported. Use "video" instead.')
            rtc_logger.warning(message)
            # HTML template is UTF-8, make sure the string is UTF-8 as well.
            warning_messages.append(message.encode('utf-8'))

        # Options for controlling various networking features.
        dtls = request.get('dtls')
        dscp = request.get('dscp')
        ipv6 = request.get('ipv6')
        debug = request.get('debug')
        if debug == 'loopback':
            # Set dtls to false as DTLS does not work for loopback.
            dtls = 'false'
            include_loopback_js = '<script src="/js/loopback.js"></script>'
        else:
            include_loopback_js = ''

        include_rtstats_js = ''
        # if str(os.environ.get('WITH_RTSTATS')) != 'none':
        #     include_rtstats_js = \
        #         '<script src="/js/rtstats.js"></script><script src="/pako/pako.min.js"></script>'

        # TODO(tkchin): We want to provide a ICE request url on the initial get,
        # but we don't provide client_id until a join. For now just generate
        # a random id, but we should make this better.
        username = client_id if client_id is not None else self.generate_random(9)
        if len(ice_server_base_url) > 0:
            ice_server_url = ICE_SERVER_URL_TEMPLATE % \
                             (ice_server_base_url, ICE_SERVER_API_KEY)
        else:
            ice_server_url = ''

        # If defined it will override the ICE server provider and use the specified
        # turn servers directly.
        ice_server_override = ICE_SERVER_OVERRIDE

        pc_config = self.make_pc_config(ice_transports, ice_server_override)
        pc_constraints = self.make_pc_constraints(dtls, dscp, ipv6)
        offer_options = {}
        media_constraints = self.make_media_stream_constraints(audio, video,
                                                               firefox_fake_device)
        wss_url, wss_post_url = self.get_wss_parameters(request)

        bypass_join_confirmation = 'BYPASS_JOIN_CONFIRMATION' in os.environ and \
                                   os.environ['BYPASS_JOIN_CONFIRMATION'] == 'True'

        params = {
            'error_messages': error_messages,
            'warning_messages': warning_messages,
            'is_loopback': json.dumps(debug == 'loopback'),
            'pc_config': json.dumps(pc_config),
            'pc_constraints': json.dumps(pc_constraints),
            'offer_options': json.dumps(offer_options),
            'media_constraints': json.dumps(media_constraints),
            'ice_server_url': ice_server_url,
            'ice_server_transports': ice_server_transports,
            'include_loopback_js': include_loopback_js,
            'include_rtstats_js': include_rtstats_js,
            'wss_url': wss_url,
            'wss_post_url': wss_post_url,
            'bypass_join_confirmation': json.dumps(bypass_join_confirmation),
            #'version_info': None,
            #'version_info': json.dumps(self.get_version_info()),
            'is_screenshare': request.get('screenShare', 'false'),
            'k': request.get('k', 'false'),
            'room_id' : ''
        }

        if __request.url_root[-1:] == '/':
            __url = __request.url_root[:-1]
        else:
            __url = __request.url_root
        __url = __url.replace('http','https') if 'http' in __url else __url
        if __request.path[-1:] == '/':
            __url_trail = __request.path[:-1]
        else:
            __url_trail = __request.path
        params['room_link'] = __url + SERVICE_PREFIX

        if room_id is not None:
            params['room_id'] = room_id
            # params['room_link'] = params['room_link'] + '/r/' + room_id
        if client_id is not None:
            params['client_id'] = client_id
        if is_initiator is not None:
            params['is_initiator'] = json.dumps(is_initiator)
        return params


class Client:
    def __init__(self, is_initiator, messages=None):
        self.is_initiator = is_initiator
        if messages and isinstance(messages, list):
            self.messages = messages
        else:
            self.messages = []

    def add_message(self, msg):
        self.messages.append(msg)

    def clear_messages(self):
        self.messages = []

    def set_initiator(self, initiator):
        self.is_initiator = initiator

    def __str__(self):
        return '{%r, %d}' % (self.is_initiator, len(self.messages))

    def __call__(self, *args, **kwargs):
        return {
            'is_initiator': self.is_initiator,
            'messages': self.messages
        }


class Room:
    """
    ROOM 包含
    clients

    """

    def __init__(self, clients=None):
        self.clients = {}
        if clients:
            try:
                for client, attrib in clients.items():
                    self.clients[client] = attrib
            except Exception as e:
                raise TypeError("WRONG TYPE DETECTED {} EXCEPTION {}".format(clients, e))

    def __call__(self, *args, **kwargs):
        return dict(self.clients.items())
        # return json.dumps(self.clients, ensure_ascii=False)

    def get_new_room(self, key):
        __room = redis_cli.get(REDIS_PREFIX_KEY+key)
        if not __room:
            return {}
        else:
            __room = json.loads(__room)
            return __room

    def add_client(self, client_id, client):
        if callable(client):
            self.clients[client_id] = client()
        else:
            self.clients[client_id] = client

    def remove_client(self, client_id):
        del self.clients[client_id]

    def get_occupancy(self):
        return len(self.clients.keys())

    def has_client(self, client_id):
        return client_id in self.clients.keys()

    def get_client(self, client_id):
        return Client(self.clients[client_id])

    def get_other_client(self, client_id):
        for key, client in self.clients.items():
            if key != client_id:
                return client
        return None

    def new_add_client_to_room(self, client_id, room_key=''):
        # if not room_key:
        #     room_key = rtc_utils.get_memcache_key_for_room(request.host_url, room_id)
        error = None
        room = None
        is_initiator = None
        other_client = {}
        messages = []
        __room = all_room.get(room_key)
        if not __room:
            __room = redis_cli.get(name=REDIS_PREFIX_KEY + room_key)
            if not __room:
                __room = Room().get_new_room(key=room_key)
            else:
                __room = json.loads(__room)
            all_room[room_key] = __room
        occupancy = len(__room)
        tag = False if len(__room) > 0 else True
        if occupancy >= 2:
            error = RESPONSE_ROOM_FULL
        elif client_id in __room:
            error = RESPONSE_DUPLICATE_CLIENT
        if not error:
            if occupancy == 0:
                is_initiator = True
            elif occupancy == 1:
                is_initiator = False
                other_client = __room[list(filter(lambda x: x != client_id, list(__room.keys())))[0]]
                messages = other_client['messages']
                other_client['messages'] = []
            # else:
            #     tag = False
            all_room[room_key][client_id] = {'messages': [], 'is_initiator': tag, 'id': len(__room)}
            redis_cli.set(name=REDIS_PREFIX_KEY + room_key, value=json.dumps(all_room[room_key], ensure_ascii=False),
                          ex=86400)
        is_initiator = __room[client_id]['is_initiator'] if client_id in __room else is_initiator

        # messages = __room[client_id]['messages'] if client_id in __room else None
        return {'error': error, 'is_initiator': is_initiator,
                'messages': messages, 'room_state': str(__room)}

    def add_client_to_room(self, request, room_id, client_id, is_loopback=False):
        key = rtc_utils.get_memcache_key_for_room(request.host_url, room_id)
        error = None
        retries = 0
        room = None
        # Compare and set retry loop.
        while True:
            is_initiator = None
            messages = []
            room_state = ''

            # room_clients = self.redis_cli.get(key)
            room_clients = all_room.get(key)

            if not room_clients:
                # # 'set' and another 'gets' are needed for CAS to work.
                # if not self.redis_cli.set(key, json.dumps(Room(), ensure_ascii=False)):
                #     rtc_logger.warning('memcache.Client.set failed for key ' + key)
                #     error = RESPONSE_ERROR
                #     break
                # room = self.redis_cli.get(key)
                room = Room()
            else:
                room = Room(room_clients)

            occupancy = room.get_occupancy()

            if occupancy >= 2:
                error = RESPONSE_ROOM_FULL
                break
            if room.has_client(client_id):
                error = RESPONSE_DUPLICATE_CLIENT
                break

            if occupancy == 0:
                is_initiator = True
                room.add_client(client_id, Client(is_initiator))
                # if is_loopback:
                #     room.add_client(LOOPBACK_CLIENT_ID, Client(False))
            else:
                is_initiator = False
                other_client = room.get_other_client(client_id)
                # messages = other_client.messages
                messages = other_client['messages']
                room.add_client(client_id, Client(is_initiator))
                # other_client.clear_messages()
                other_client['messages'] = []

            all_room[key] = room()
            retries = None
            break
            # if self.redis_cli.set(key, room(), ROOM_MEMCACHE_EXPIRATION_SEC):
            #     rtc_logger.info('Added client {} in room {}, retries = {}'.format(client_id, room_id, retries))
            # else:
            #     retries = retries + 1
        return {'error': error, 'is_initiator': is_initiator,
                'messages': messages, 'room_state': str(room)}

    def new_remove_client_from_room(self, room_key, client_id):
        __room = all_room.get(room_key)
        if not __room:
            __room = redis_cli.get(REDIS_PREFIX_KEY + room_key)
        if not __room or not isinstance(__room, dict):
            rtc_logger.warning('remove_client_from_room: Unknown room ' + room_key)
            return {'error': RESPONSE_UNKNOWN_ROOM, 'room_state': None}
        if client_id not in __room:
            rtc_logger.warning('remove_client_from_room: Unknown client ' + client_id + \
                               ' for room ' + room_key)
            return {'error': RESPONSE_UNKNOWN_CLIENT, 'room_state': None}
        __room.pop(client_id)
        if len(__room) > 0:
            # 或许有朝一日会大于2个人
            __room[list(__room.keys())[0]]['is_initiator'] = True
            all_room[room_key] = __room
        else:
            all_room.pop(room_key)
        # 感觉redis读写频率可能会比较高，如果不需要的话可以不用在每个写操作之后update redis
        if room_key in all_room:
            redis_cli.set(name=REDIS_PREFIX_KEY + room_key, value=json.dumps(all_room[room_key], ensure_ascii=False),
                          ex=86400)
        else:
            res = redis_cli.delete(REDIS_PREFIX_KEY + room_key)
        return {'error': None, 'room_state': f'{__room}'}

    def remove_client_from_room(self, host, room_id, client_id):
        key = rtc_utils.get_memcache_key_for_room(host, room_id)
        retries = 0
        # Compare and set retry loop.
        # 循环
        while True:
            # room = self.redis_cli.get(key)
            room = Room(all_room.get(key))
            if room is None:
                rtc_logger.warning('remove_client_from_room: Unknown room ' + room_id)
                return {'error': RESPONSE_UNKNOWN_ROOM, 'room_state': None}
            if not room.has_client(client_id):
                rtc_logger.warning('remove_client_from_room: Unknown client ' + client_id + \
                                   ' for room ' + room_id)
                return {'error': RESPONSE_UNKNOWN_CLIENT, 'room_state': None}

            room.remove_client(client_id)
            if room.has_client(LOOPBACK_CLIENT_ID):
                room.remove_client(LOOPBACK_CLIENT_ID)
            if room.get_occupancy() > 0:
                room.get_other_client(client_id).set_initiator(True)
            else:
                room = None

            all_room[key] = room()
            # if self.redis_cli.set(key, room(), ROOM_MEMCACHE_EXPIRATION_SEC):
            #     rtc_logger.info('Removed client {} from room {}, retries={}'.format(client_id, room_id, retries))
            #     return {'error': None, 'room_state': str(room)}
            retries = retries + 1

    def __str__(self):
        return str(self.clients.keys())


rtc_utils = Utility()

