import os
from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# 環境変数からAPIキーとGAS WebアプリのURLを取得
# デフォルト値は開発用のため、Renderデプロイ時には環境変数が優先されます
# 提供いただいたURLに更新済み
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'your_gpts_internal_api_key')
# ★★★ 最新のGAS WebアプリのURLに更新済み ★★★
GAS_WEB_APP_URL = os.environ.get('GAS_WEB_APP_URL', 'https://script.google.com/macros/s/AKfycbz68HMbQ1My2_cbruWCd0M4tGkYOSxC0VugBWPgFzYxXsDIZjg40XpSzfQKYBkBP1mB4g/exec') 

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
        
        # Google Apps Script Web AppへPOSTリクエストを送信
        # Content-Type: application/json で json= パラメータを使用
        gas_response = requests.post(GAS_WEB_APP_URL, json=request_data, timeout=30)
        
        # HTTPステータスコードが2xx以外の場合、例外を発生させる
        gas_response.raise_for_status()

        # Apps Scriptからの応答をJSONとしてパースして返す
        # GASからのレスポンスがJSON形式でない場合のハンドリングを強化
        try:
            return jsonify(gas_response.json()), gas_response.status_code
        except json.JSONDecodeError:
            # GASが有効なJSONを返さなかった場合
            print(f"GAS responded with non-JSON content: {gas_response.text}")
            return jsonify({
                "status": "error",
                "message": "GAS response was not valid JSON.",
                "gas_response_text": gas_response.text # デバッグ用にGASの生レスポンスを含める
            }), 500 # 500 Internal Server Error として返すのが適切かもしれません

    except requests.exceptions.Timeout:
        # タイムアウトエラーのハンドリング
        return jsonify({
            "status": "error",
            "message": "Timeout connecting to Google Apps Script Web App."
        })
    except requests.exceptions.RequestException as e:
        # リクエスト関連のその他のエラーハンドリング（例：ネットワークエラー、GASが5xxを返したなど）
        error_message = f"Failed to connect to Google Apps Script Web App: {e}"
        gas_response_text = "No response text available"
        if 'gas_response' in locals():
            gas_response_text = gas_response.text
        
        print(f"RequestException caught: {e}")
        print(f"GAS Response content: {gas_response_text}")

        return jsonify({
            "status": "error",
            "message": error_message,
            "gas_response_text": gas_response_text
        }), 500 # 適切なステータスコードで返す

    except Exception as e:
        # その他の予期せぬエラーハンドリング
        print(f"An unexpected error occurred in intermediate API: {e}")
        return jsonify({
            "status": "error",
            "message": f"An unexpected error occurred in intermediate API: {e}"
        }), 500 # 適切なステータスコードで返す

if __name__ == '__main__':
    # ローカル開発用の設定 (Renderデプロイ時には使用されません)
    app.run(debug=True, host='0.0.0.0', port=5000)
