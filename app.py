from flask import Flask, request, jsonify
import hashlib
import re

app = Flask(__name__)

# UUID validation pattern
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

# Known UUIDs and their status
KNOWN_UUIDS = {
    '0bd75917-8640-4592-8fff-b8457522e18f': 'found',
    '18296be4-f1c7-4479-a175-531cd3afbc12': 'not_found'
}

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
        
        # Check if user exists
        if uuid.lower() not in KNOWN_UUIDS:
            return jsonify({
                'error': 'user not found'
            }), 404
        
        if KNOWN_UUIDS[uuid.lower()] == 'not_found':
            return jsonify({
                'error': 'user not found'
            }), 404
        
        # Create SHA256 hash of the UUID
        hash_obj = hashlib.sha256(uuid.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        
        # Extract characters at positions 37 and 53 (0-indexed)
        char_37 = hash_hex[37] if len(hash_hex) > 37 else ''
        char_53 = hash_hex[53] if len(hash_hex) > 53 else ''
        
        # Check for specific combinations and return appropriate response
        if char_37 == 'M' and char_53 == 'N':
            response = 'MN'
        elif char_37 == 'C' and char_53 == 'N':
            response = 'CN'
        else:
            response = char_37 + char_53
        
        return jsonify({
            'uuid': uuid,
            'hash': hash_hex,
            'char_37': char_37,
            'char_53': char_53,
            'result': response
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

