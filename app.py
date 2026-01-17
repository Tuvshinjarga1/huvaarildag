from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import os
from dotenv import load_dotenv
import psycopg2

# Local modules
from utils import (
    get_db_connection, get_region_from_token, UUID_PATTERN
)
from product import product_bp

# .env файлыг унших
load_dotenv()

app = Flask(__name__)
# Register Blueprints
app.register_blueprint(product_bp)

CORS(app)

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

@app.route('/getUserData', methods=['POST'])
def getUserData():
    try:
        data = request.get_json()
        
        if not data or 'uuid' not in data:
            return jsonify({'error': 'Missing uuid in request body'}), 400
        
        uuid = data['uuid']
        
        # Validate UUID format
        if not UUID_PATTERN.match(uuid):
            return jsonify({'error': 'invalid uuid'}), 400
        
        # SHA256 hash үүсгэх
        hash_obj = hashlib.sha256(uuid.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        hash_int = int(hash_hex, 16)
        remainder = hash_int % 283
        
        if remainder == 37 or remainder == 53:
            return jsonify({'result': 'CN'}), 200
        else:
            return jsonify({'error': 'not user id'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/addUser', methods=['POST'])
def addUser():
    """
    User token-ийг database-д хадгалах
    Body: { "userToken": "uuid-here" }
    """
    try:
        data = request.get_json()
        
        if not data or 'userToken' not in data:
            return jsonify({'error': 'Missing userToken in request body'}), 400
        
        user_token = data['userToken']
        
        # UUID форматыг шалгах
        if not UUID_PATTERN.match(user_token):
            return jsonify({'error': 'invalid userToken format'}), 400
        
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
            return jsonify({'error': 'User token already exists'}), 409
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)