from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import re
import requests
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Database тохиргоо
DATABASE = 'tokens.db'

def init_db():
    """Database болон хүснэгтүүдийг үүсгэх"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Products хүснэгт
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_token TEXT UNIQUE NOT NULL,
            region TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Users хүснэгт
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_token TEXT UNIQUE NOT NULL,
            region TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# App эхлэхэд database үүсгэх
init_db()

# Regional server URLs
REGIONAL_SERVERS = {
    'CN': 'http://8.130.214.68:3000',
    'RU': 'http://your-ru-server:3000',  # RU серверийн URL-ийг энд оруулна
    'MN': 'http://your-mn-server:3000',  # MN серверийн URL-ийг энд оруулна
}

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
        
        # Database-д хадгалах
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO products (product_token, region) VALUES (?, ?)',
                (product_token, region)
            )
            conn.commit()
            
            return jsonify({
                'message': 'Product token saved successfully',
                'productToken': product_token,
                'region': region
            }), 201
            
        except sqlite3.IntegrityError:
            return jsonify({
                'error': 'Product token already exists'
            }), 409
        finally:
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
        
        # Database-д хадгалах
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO users (user_token, region) VALUES (?, ?)',
                (user_token, region)
            )
            conn.commit()
            
            return jsonify({
                'message': 'User token saved successfully',
                'userToken': user_token,
                'region': region
            }), 201
            
        except sqlite3.IntegrityError:
            return jsonify({
                'error': 'User token already exists'
            }), 409
        finally:
            conn.close()
            
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

