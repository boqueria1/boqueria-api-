import os
from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'your_gpts_internal_api_key')
GAS_WEB_APP_URL = os.environ.get('GAS_WEB_APP_URL', 'https://script.google.com/macros/s/AKfycbzHoHVDVafFlRVxruP4hn571NzPy3S_seYH2yfWqA0LJCFQC1RePy4ZllrHLIC7xXNNEw/exec')

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
        
        # ★★★ここを元に戻すか、Content-Typeを明確にapplication/jsonに設定し、json=を使う★★★
        # GASがapplication/jsonを期待する場合の標準的な方法
        gas_response = requests.post(GAS_WEB_APP_URL, json=request_data, timeout=30)
        
        gas_response.raise_for_status()

        return jsonify(gas_response.json()), gas_response.status_code

    except requests.exceptions.Timeout:
        return jsonify({
            "status": "error",
            "message": "Timeout connecting to Google Apps Script Web App."
        })
    except requests.exceptions.RequestException as e:
        # このエラーメッセージをより詳細にすることで、GASからの不正なレスポンスもキャッチできる
        print(f"RequestException caught: {e}")
        print(f"GAS Response content: {gas_response.text if 'gas_response' in locals() else 'N/A'}")
        return jsonify({
            "status": "error",
            "message": f"Failed to connect to Google Apps Script Web App: {e}",
            "gas_response_text": gas_response.text if 'gas_response' in locals() else 'No response text'
        })
    except json.JSONDecodeError as e: # GASがJSON以外のものを返す場合に備える
        print(f"JSONDecodeError caught: {e}")
        print(f"GAS Response content: {gas_response.text if 'gas_response' in locals() else 'N/A'}")
        return jsonify({
            "status": "error",
            "message": f"Invalid JSON response from Google Apps Script Web App: {e}",
            "gas_response_text": gas_response.text if 'gas_response' in locals() else 'No response text'
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"An unexpected error occurred in intermediate API: {e}"
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
