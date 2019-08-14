#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""AppRTC Constants.

This module contains the constants used in AppRTC Python modules.
"""
import os
from utils.get_conf import get_config_file
from utils.logger_conf import configure_logger
from utils.get_conf import get_logger_file, get_config_file

REDIS_PREFIX_KEY = "RTC_ROOM_"
config = get_config_file()
SERVICE_PREFIX = '/py/rtc'
AUTH_CKEY_URL = config['qtalk']['auth_ckey_url']
STUN_SERVER = config['rtc']['stun_url']
TURN_SERVER = config['rtc']['turn_url']
if ';' in STUN_SERVER:
    STUN_SERVER = STUN_SERVER.split(';')
else:
    STUN_SERVER = [STUN_SERVER]
if ';' in TURN_SERVER:
    TURN_SERVER = TURN_SERVER.split(';')
else:
    TURN_SERVER = [TURN_SERVER]
TURN_USER = config['rtc']['turn_username']
TURN_PASSWORD = config['rtc']['turn_password']
WSS_SERVER = config['rtc']['wss_url']
if not TURN_SERVER and STUN_SERVER:
    TURN_SERVER = STUN_SERVER

# Deprecated domains which we should to redirect to REDIRECT_URL.
REDIRECT_DOMAINS = [
    'apprtc.appspot.com', 'apprtc.webrtc.org', 'www.appr.tc'
]
# URL which we should redirect to if matching in REDIRECT_DOMAINS.
REDIRECT_URL = 'https://appr.tc'

ROOM_MEMCACHE_EXPIRATION_SEC = 60 * 60 * 24
MEMCACHE_RETRY_LIMIT = 100

LOOPBACK_CLIENT_ID = 'LOOPBACK_CLIENT_ID'

# Turn/Stun server override. This allows AppRTC to connect to turn servers
# directly rather than retrieving them from an ICE server provider.
# ICE_SERVER_OVERRIDE = None
# Enable by uncomment below and comment out above, then specify turn and stun
ICE_SERVER_OVERRIDE = [
    {
        "urls": TURN_SERVER,
        "username": TURN_USER,
        "credential": TURN_PASSWORD
    },
    {
        "urls": STUN_SERVER

    }
]

ICE_SERVER_BASE_URL = 'https://networktraversal.googleapis.com'
ICE_SERVER_URL_TEMPLATE = '%s/v1alpha/iceconfig?key=%s'
ICE_SERVER_API_KEY = os.environ.get('ICE_SERVER_API_KEY')

# WSS_INSTANCE_HOST_KEY = '10.88.112.98:8089'
WSS_INSTANCE_HOST_KEY = WSS_SERVER
WSS_INSTANCE_NAME_KEY = 'vm_name'
WSS_INSTANCE_ZONE_KEY = 'zone'

WSS_INSTANCES = [{
    WSS_INSTANCE_HOST_KEY: WSS_SERVER,
    # WSS_INSTANCE_HOST_KEY: '10.88.112.98:8089',
    WSS_INSTANCE_NAME_KEY: 'wsserver-std',
    WSS_INSTANCE_ZONE_KEY: 'us-central1-a'
}, {
    WSS_INSTANCE_HOST_KEY: WSS_SERVER,
    # WSS_INSTANCE_HOST_KEY: '10.88.112.98:8089',
    WSS_INSTANCE_NAME_KEY: 'wsserver-std-2',
    WSS_INSTANCE_ZONE_KEY: 'us-central1-f'
}]
WSS_HOST_PORT_PAIRS = [ins[WSS_INSTANCE_HOST_KEY] for ins in WSS_INSTANCES]

# memcache key for the active collider host.
WSS_HOST_ACTIVE_HOST_KEY = 'wss_host_active_host'

# Dictionary keys in the collider probing result.
WSS_HOST_IS_UP_KEY = 'is_up'
WSS_HOST_STATUS_CODE_KEY = 'status_code'
WSS_HOST_ERROR_MESSAGE_KEY = 'error_message'

RESPONSE_ERROR = 'ERROR'
RESPONSE_ROOM_FULL = 'FULL'
RESPONSE_UNKNOWN_ROOM = 'UNKNOWN_ROOM'
RESPONSE_UNKNOWN_CLIENT = 'UNKNOWN_CLIENT'
RESPONSE_DUPLICATE_CLIENT = 'DUPLICATE_CLIENT'
RESPONSE_SUCCESS = 'SUCCESS'
RESPONSE_INVALID_REQUEST = 'INVALID_REQUEST'

IS_DEV_SERVER = os.environ.get('APPLICATION_ID', '').startswith('dev')

BIGQUERY_URL = 'https://www.googleapis.com/auth/bigquery'

# Dataset used in production.
BIGQUERY_DATASET_PROD = 'prod'

# Dataset used when running locally.
BIGQUERY_DATASET_LOCAL = 'dev'

# BigQuery table within the dataset.
BIGQUERY_TABLE = 'analytics'
