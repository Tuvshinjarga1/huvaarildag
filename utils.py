import os
import hashlib
import re
import psycopg2
import geoip2.database
from flask import request

# UUID validation pattern
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

# Regional server URLs
REGIONAL_SERVERS = {
    'CN': 'http://8.130.214.68:3000',
    'RU': 'http://your-ru-server:3000',
    'MN': 'http://your-mn-server:3000',
}

REGION_LANGUAGE = {
    'CN': 'zh-CN',
    'RU': 'ru-RU',
    'MN': 'mn-MN',
    'US': 'en-US',
    'LOCAL': 'en-US',
}

DB = os.getenv('CON_STRING')

def get_db_connection():
    try:
        return psycopg2.connect(DB)
    except psycopg2.OperationalError as e:
        raise ConnectionError(
            f"Failed to connect to PostgreSQL database. "
            f"Please ensure PostgreSQL is running and CON_STRING is correct.\n"
            f"Error: {str(e)}"
        ) from e

# GeoIP database
GEOIP_DB_PATH = os.environ.get('GEOIP_DB_PATH', 'GeoLite2-Country.mmdb')
geoip_reader = None

try:
    if os.path.exists(GEOIP_DB_PATH):
        geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
except Exception:
    pass

def get_region_from_ip(ip_address):
    if not ip_address:
        return None
    
    if ip_address.startswith('127.') or ip_address.startswith('192.168.') or ip_address.startswith('10.'):
        return 'LOCAL'
    
    if not geoip_reader:
        return None
    
    try:
        response = geoip_reader.country(ip_address)
        return response.country.iso_code
    except Exception:
        return None

def get_client_ip():
    """Client-ийн IP хаягийг авах (proxy-ийн ард байсан ч)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def get_region_from_token(token):
    """Token-ийг SHA256 hash хийж, аль улсад хамаарахыг тодорхойлох"""
    hash_obj = hashlib.sha256(token.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    hash_int = int(hash_hex, 16)
    remainder = hash_int % 283
    
    if remainder == 37 or remainder == 53:
        return 'CN'
    elif remainder == 71 or remainder == 89:
        return 'RU'
    elif remainder == 101 or remainder == 113:
        return 'MN'
    else:
        return None
