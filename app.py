import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# 環境変数からAPIキーとGAS WebアプリのURLを取得
# デフォルト値は開発用のため、Renderデプロイ時には環境変数が優先されます
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'your_gpts_internal_api_key')
GAS_WEB_APP_URL = os.environ.get('GAS_WEB_APP_URL', 'https://script.google.com/macros/s/xxxxxxxxxxxxxxxxxxx/exec')

@app.route('/quiz-api', methods=['POST'])
def handle_quiz_api():
    # GPTsから送られてくるx-api-keyを検証
    client_internal_api_key = request.headers.get('x-api-key')
    if not client_internal_api_key or client_internal_api_key != INTERNAL_API_KEY:
        return jsonify({
            "status": "error",
            "message": "Authentication failed for intermediate API. Invalid or missing x-api-key."
        }), 401

    try:
        # GPTsからのリクエストボディを取得
        request_data = request.json

        # Google Apps Script Web Appへ転送するためのヘッダーを設定
        # Apps Script側のAPI_KEY (123) と一致させる必要があります
        gas_headers = {'Content-Type': 'application/json', 'x-api-key': '123'} # <--- この行です

        # Google Apps Script Web AppへPOSTリクエストを送信
        # タイムアウトは30秒に設定
        gas_response = requests.post(GAS_WEB_APP_URL, json=request_data, headers=gas_headers, timeout=30)
        
        # HTTPステータスコードが2xx以外の場合、例外を発生させる
        gas_response.raise_for_status()

        # Apps Scriptからの応答をそのまま返す
        return jsonify(gas_response.json()), gas_response.status_code

    except requests.exceptions.Timeout:
        # タイムアウトエラーのハンドリング
        return jsonify({
            "status": "error",
            "message": "Timeout connecting to Google Apps Script Web App."
        })
    except requests.exceptions.RequestException as e:
        # リクエスト関連のその他のエラーハンドリング
        return jsonify({
            "status": "error",
            "message": f"Failed to connect to Google Apps Script Web App: {e}"
        })
    except Exception as e:
        # その他の予期せぬエラーハンドリング
        return jsonify({
            "status": "error",
            "message": f"An unexpected error occurred in intermediate API: {e}"
        })

if __name__ == '__main__':
    # ローカル開発用の設定 (Renderデプロイ時には使用されません)
    app.run(debug=True, host='0.0.0.0', port=5000)
