from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import re
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import geoip2.database
import os
from dotenv import load_dotenv

# .env файлыг унших
load_dotenv()

app = Flask(__name__)
CORS(app)

DB = os.getenv('CON_STRING')

if not DB:
    raise ValueError(
        "CON_STRING environment variable is not set. "
        "Please set CON_STRING to connect to PostgreSQL database. "
        "Example: postgresql://user:password@localhost:5432/database"
    )

def get_db_connection():
    try:
        return psycopg2.connect(DB)
    except psycopg2.OperationalError as e:
        raise ConnectionError(
            f"Failed to connect to PostgreSQL database. "
            f"Please ensure PostgreSQL is running and CON_STRING is correct.\n"
            f"Error: {str(e)}"
        ) from e

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                product_token VARCHAR(255) UNIQUE NOT NULL,
                region VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_token VARCHAR(255) UNIQUE NOT NULL,
                region VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize database: {str(e)}\n"
            f"Please check that PostgreSQL is running and accessible."
        ) from e

init_db()

# Regional server URLs
REGIONAL_SERVERS = {
    'CN': 'http://8.130.214.68:3000',
    'RU': 'http://your-ru-server:3000',  # RU серверийн URL-ийг энд оруулна
    'MN': 'http://your-mn-server:3000',  # MN серверийн URL-ийг энд оруулна
}

# GeoIP database
GEOIP_DB_PATH = os.environ.get('GEOIP_DB_PATH', 'GeoLite2-Country.mmdb')
geoip_reader = None

try:
    if os.path.exists(GEOIP_DB_PATH):
        geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
except Exception:
    pass

REGION_LANGUAGE = {
    'CN': 'zh-CN',
    'RU': 'ru-RU',
    'MN': 'mn-MN',
    'US': 'en-US',
    'LOCAL': 'en-US',
}


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
    # X-Forwarded-For header шалгах (proxy-ийн ард байвал)
    if request.headers.get('X-Forwarded-For'):
        # Эхний IP нь жинхэнэ client IP
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    # X-Real-IP header шалгах
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    # Шууд холбогдсон IP
    else:
        return request.remote_addr

# UUID validation pattern
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

@app.route('/getUserData', methods=['POST'])
def getUserData():
    try:
        data = request.get_json()
        
        if not data or 'uuid' not in data:
            return jsonify({
                'error': 'Missing uuid in request body'
            }), 400
        
        uuid = data['uuid']
        
        # Validate UUID format
        if not UUID_PATTERN.match(uuid):
            return jsonify({
                'error': 'invalid uuid'
            }), 400
        
        # SHA256 hash үүсгэх
        hash_obj = hashlib.sha256(uuid.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        
        # Hex hash-ийг 10-тын тооллын big integer болгох
        hash_int = int(hash_hex, 16)
        
        # 283-д хувааж, үлдэгдэл (remainder/modulo) авах
        remainder = hash_int % 283
        
        # Хэрэв үлдэгдэл нь 37 эсвэл 53 байвал CN буцаах
        if remainder == 37 or remainder == 53:
            response = 'CN'
            return jsonify({
                # 'uuid': uuid,
                # 'hash': hash_hex,
                # 'hash_decimal': str(hash_int),
                # 'divisor': 283,
                # 'remainder': remainder,
                'result': response
            }), 200
        else:
            # CN биш бол not user id буцаах
            return jsonify({
                'error': 'not user id'
            }), 404
        
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


def get_region_from_token(token):
    """Token-ийг SHA256 hash хийж, аль улсад хамаарахыг тодорхойлох"""
    hash_obj = hashlib.sha256(token.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    hash_int = int(hash_hex, 16)
    remainder = hash_int % 283
    
    # Remainder-ийн утгаар улс тодорхойлох
    if remainder == 37 or remainder == 53:
        return 'CN'
    elif remainder == 71 or remainder == 89:
        return 'RU'
    elif remainder == 101 or remainder == 113:
        return 'MN'
    else:
        return None


@app.route('/getProduct/<token>', methods=['GET'])
def getProduct(token):
    """
    Token-оор бараа мэдээлэл авах
    Query params:
        - lan: Хэл (жнь: zh-CN, en-US, ru-RU, mn-MN)
    Returns:
        - data: Барааны мэдээлэл
        - region: Улсын код (CN, RU, MN гэх мэт)
    """
    try:
        # Хэлний параметр авах
        lan = request.args.get('lan', 'en-US')
        
        # UUID форматыг шалгах
        if not UUID_PATTERN.match(token):
            return jsonify({
                'error': 'invalid token'
            }), 400
        
        # Token-оос улс тодорхойлох
        region = get_region_from_token(token)
        
        if not region:
            return jsonify({
                'error': 'region not supported'
            }), 404
        
        # Тухайн улсын серверийн URL авах
        server_url = REGIONAL_SERVERS.get(region)
        
        if not server_url:
            return jsonify({
                'error': f'server not configured for region: {region}'
            }), 500
        
        # Тухайн улсын серверээс бараа мэдээлэл авах
        response = requests.get(
            f'{server_url}/api/v1/product/getProduct/{token}',
            params={'lan': lan},
            timeout=10
        )
        
        if response.status_code == 200:
            product_data = response.json()
            return jsonify({
                'data': product_data,
                'region': region
            }), 200
        else:
            return jsonify({
                'error': 'Failed to fetch product data',
                'status_code': response.status_code
            }), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({
            'error': 'Request to regional server timed out'
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            'error': f'Request failed: {str(e)}'
        }), 502
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/addProduct', methods=['POST'])
def addProduct():
    """
    Product token-ийг database-д хадгалах
    Body: { "productToken": "uuid-here" }
    """
    try:
        data = request.get_json()
        
        if not data or 'productToken' not in data:
            return jsonify({
                'error': 'Missing productToken in request body'
            }), 400
        
        product_token = data['productToken']
        
        # UUID форматыг шалгах
        if not UUID_PATTERN.match(product_token):
            return jsonify({
                'error': 'invalid productToken format'
            }), 400
        
        # Region тодорхойлох
        region = get_region_from_token(product_token)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO products (product_token, region) VALUES (%s, %s)',
                (product_token, region)
            )
            conn.commit()
            
            return jsonify({
                'message': 'Product token saved successfully',
                'productToken': product_token,
                'region': region
            }), 201
            
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({
                'error': 'Product token already exists'
            }), 409
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/addUser', methods=['POST'])
def addUser():
    """
    User token-ийг database-д хадгалах
    Body: { "userToken": "uuid-here" }
    """
    try:
        data = request.get_json()
        
        if not data or 'userToken' not in data:
            return jsonify({
                'error': 'Missing userToken in request body'
            }), 400
        
        user_token = data['userToken']
        
        # UUID форматыг шалгах
        if not UUID_PATTERN.match(user_token):
            return jsonify({
                'error': 'invalid userToken format'
            }), 400
        
        # Region тодорхойлох
        region = get_region_from_token(user_token)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO users (user_token, region) VALUES (%s, %s)',
                (user_token, region)
            )
            conn.commit()
            
            return jsonify({
                'message': 'User token saved successfully',
                'userToken': user_token,
                'region': region
            }), 201
            
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({
                'error': 'User token already exists'
            }), 409
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/getProductList/<int:num>', methods=['GET'])
def getProductList(num):
    """
    Database-ээс {num} ширхэг random product token авах.
    - Хэрэв token нь request илгээж буй сервертэй нэг улсынх бол шууд token буцаана
    - Хэрэв token нь өөр улсынх бол тэр улсын серверээс бараа мэдээлэл авна
    
    Headers:
        - X-Forwarded-For эсвэл X-Real-IP: Client IP (улс тодорхойлоход)
    Query params:
        - lan: Хэл (optional, default: улсын хэл)
    """
    try:
        # Хамгийн ихдээ 100 бараа авах боломжтой
        if num < 1:
            return jsonify({'error': 'num must be at least 1'}), 400
        if num > 100:
            num = 100
        
        # Client IP-ээс улс тодорхойлох
        client_ip = get_client_ip()
        client_region = get_region_from_ip(client_ip)
        
        # Хэлний параметр авах (байхгүй бол улсын default хэл)
        default_lan = REGION_LANGUAGE.get(client_region, 'en-US')
        lan = request.args.get('lan', default_lan)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            'SELECT product_token, region FROM products ORDER BY RANDOM() LIMIT %s',
            (num,)
        )
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not products:
            return jsonify({
                'error': 'No products found in database',
                'client_ip': client_ip,
                'client_region': client_region
            }), 404
        
        result = []
        
        for product in products:
            token = product['product_token']
            token_region = product['region']
            
            # Local эсвэл remote эсэхийг тодорхойлох
            is_local = (token_region == client_region or client_region == 'LOCAL')
            
            # Серверээс барааны мэдээлэл авах (нэр авахын тулд)
            server_url = REGIONAL_SERVERS.get(token_region)
            
            if server_url:
                try:
                    response = requests.get(
                        f'{server_url}/api/v1/product/getProduct/{token}',
                        params={'lan': lan},
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        product_data = response.json()
                        # Барааны нэр авах (data.productname эсвэл productname)
                        product_name = None
                        if 'data' in product_data and 'productname' in product_data['data']:
                            product_name = product_data['data']['productname']
                        elif 'productname' in product_data:
                            product_name = product_data['productname']
                        
                        item = {
                            'token': token,
                            'region': token_region,
                            'source': 'local' if is_local else 'remote',
                            'productName': product_name
                        }
                        
                        # Remote бол бүх data-г нэмж өгөх
                        if not is_local:
                            item['data'] = product_data
                        
                        result.append(item)
                    else:
                        result.append({
                            'token': token,
                            'region': token_region,
                            'source': 'local' if is_local else 'remote',
                            'productName': None,
                            'error': f'Failed to fetch: {response.status_code}'
                        })
                except requests.exceptions.RequestException as e:
                    result.append({
                        'token': token,
                        'region': token_region,
                        'source': 'local' if is_local else 'remote',
                        'productName': None,
                        'error': str(e)
                    })
            else:
                result.append({
                    'token': token,
                    'region': token_region,
                    'source': 'unknown',
                    'productName': None,
                    'error': 'Server not configured for this region'
                })
        
        return jsonify({
            'count': len(result),
            'client_ip': client_ip,
            'client_region': client_region,
            'products': result
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)