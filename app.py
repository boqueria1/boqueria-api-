import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'your_gpts_internal_api_key')
GAS_WEB_APP_URL = os.environ.get('GAS_WEB_APP_URL', 'https://script.google.com/macros/s/xxxxxxxxxxxxxxxxxxx/exec')

@app.route('/quiz-api', methods=['POST'])
def handle_quiz_api():
    client_internal_api_key = request.headers.get('x-api-key')
    if not client_internal_api_key or client_internal_api_key != INTERNAL_API_KEY:
        return jsonify({
            "status": "error",
            "message": "Authentication failed for intermediate API. Invalid or missing x-api-key."
        }), 401

    try:
        request_data = request.json
        gas_headers = {'Content-Type': 'application/json', 'x-api-key': 'testkey123'}
        gas_response = requests.post(GAS_WEB_APP_URL, json=request_data, headers=gas_headers, timeout=30)
        gas_response.raise_for_status()
        return jsonify(gas_response.json()), gas_response.status_code

    except requests.exceptions.Timeout:
        return jsonify({
            "status": "error",
            "message": "Timeout connecting to Google Apps Script Web App."
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to connect to Google Apps Script Web App: {e}"
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"An unexpected error occurred in intermediate API: {e}"
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
