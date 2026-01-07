from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import re

app = Flask(__name__)
CORS(app)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

