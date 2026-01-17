from flask import Blueprint, request, jsonify
import requests
import asyncio
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from utils import (
    get_db_connection, get_region_from_token, get_client_ip, 
    get_region_from_ip, REGIONAL_SERVERS, REGION_LANGUAGE, UUID_PATTERN
)

product_bp = Blueprint('product', __name__)

@product_bp.route('/getProduct/<token>', methods=['GET'])
def get_product(token):
    try:
        lan = request.args.get('lan', 'en-US')
        
        if not UUID_PATTERN.match(token):
            return jsonify({'error': 'invalid token'}), 400
        
        region = get_region_from_token(token)
        if not region:
            return jsonify({'error': 'region not supported'}), 404
        
        server_url = REGIONAL_SERVERS.get(region)
        if not server_url:
            return jsonify({'error': f'server not configured for region: {region}'}), 500
        
        response = requests.get(
            f'{server_url}/api/v1/product/getProduct/{token}',
            params={'lan': lan},
            timeout=10
        )
        
        if response.status_code == 200:
            return jsonify({'data': response.json(), 'region': region}), 200
        else:
            return jsonify({'error': 'Failed to fetch product data', 'status_code': response.status_code}), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request to regional server timed out'}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Request failed: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@product_bp.route('/addProduct', methods=['POST'])
def add_product():
    try:
        data = request.get_json()
        if not data or 'productToken' not in data:
            return jsonify({'error': 'Missing productToken in request body'}), 400
        
        product_token = data['productToken']
        if not UUID_PATTERN.match(product_token):
            return jsonify({'error': 'invalid productToken format'}), 400
        
        region = get_region_from_token(product_token)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO products (product_token, region) VALUES (%s, %s)',
                (product_token, region)
            )
            conn.commit()
            return jsonify({'message': 'Product token saved successfully', 'productToken': product_token, 'region': region}), 201
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({'error': 'Product token already exists'}), 409
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@product_bp.route('/deleteProductToken', methods=['DELETE'])
def delete_product_token():
    try:
        data = request.get_json()
        if not data or 'producttoken' not in data:
            return jsonify({'error': 'Missing producttoken in request body'}), 400
        
        product_token = data['producttoken']
        if not UUID_PATTERN.match(product_token):
            return jsonify({'error': 'invalid producttoken format'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM products WHERE product_token = %s', (product_token,))
            rows_deleted = cursor.rowcount
            conn.commit()
            
            if rows_deleted == 0:
                return jsonify({'error': 'Product token not found'}), 404
            
            return jsonify({'message': 'Product token deleted successfully', 'producttoken': product_token}), 200
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@product_bp.route('/getProductList/<int:num>', methods=['GET'])
def get_product_list(num):
    try:
        if num < 1: return jsonify({'error': 'num must be at least 1'}), 400
        if num > 100: num = 100
        
        client_ip = get_client_ip()
        client_region = get_region_from_ip(client_ip)
        default_lan = REGION_LANGUAGE.get(client_region, 'en-US')
        lan = request.args.get('lan', default_lan)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT product_token, region FROM products ORDER BY RANDOM() LIMIT %s', (num,))
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not products:
            return jsonify({'error': 'No products found in database', 'client_ip': client_ip, 'client_region': client_region}), 404
        
        result = []
        local_products = []
        remote_products = []
        
        for product in products:
            token = product['product_token']
            region = product['region']
            if region == client_region or client_region == 'LOCAL':
                local_products.append({'token': token, 'region': region, 'source': 'local', 'productName': None})
            else:
                remote_products.append((token, region))
        
        async def fetch_product(client, server_url, token, token_region, lan):
            try:
                response = await client.get(f'{server_url}/api/v1/product/getProduct/{token}', params={'lan': lan})
                if response.status_code == 200:
                    product_data = response.json()
                    product_name = product_data.get('data', {}).get('productname') or product_data.get('productname')
                    return {'token': token, 'region': token_region, 'source': 'remote', 'productName': product_name, 'data': product_data}
                return {'token': token, 'region': token_region, 'source': 'remote', 'productName': None, 'error': f'Failed to fetch: {response.status_code}'}
            except Exception as e:
                return {'token': token, 'region': token_region, 'source': 'remote', 'productName': None, 'error': str(e)}

        async def fetch_remote_products():
            async with httpx.AsyncClient(timeout=5.0) as client:
                tasks = []
                for token, region in remote_products:
                    server_url = REGIONAL_SERVERS.get(region)
                    if server_url:
                        tasks.append(fetch_product(client, server_url, token, region, lan))
                    else:
                        result.append({'token': token, 'region': region, 'source': 'unknown', 'productName': None, 'error': 'Server not configured'})
                if tasks:
                    return await asyncio.gather(*tasks, return_exceptions=True)
            return []

        if remote_products:
            remote_results = asyncio.run(fetch_remote_products())
            for item in remote_results:
                if isinstance(item, dict): result.append(item)
        
        result.extend(local_products)
        return jsonify({'count': len(result), 'client_ip': client_ip, 'client_region': client_region, 'products': result}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
