import os
from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# 環境変数からAPIキーを取得
# Renderデプロイ時には環境変数が優先されます
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'your_gpts_internal_api_key')

# 更新されたGAS WebアプリのURLを設定
# ここに新しいGASウェブアプリのデプロイURLを正確に貼り付けてください
GAS_WEB_APP_URL = 'https://script.google.com/macros/s/AKfycbwycNDU4v_VLr9mfADHGIbygKmFpkgBYVIjn_F_bgTZtnWneCGbCohLkLnuCMfPclUWzg/exec'

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
        if not request_data:
            return jsonify({
                "status": "error",
                "message": "Request body is empty or not valid JSON."
            }), 400

        # GAS Web Appへリクエストを転送
        # headersは必要に応じて追加・調整してください
        gas_response = requests.post(GAS_WEB_APP_URL, json=request_data)
        gas_response.raise_for_status() # HTTPエラーが発生した場合に例外を発生させる

        # GASからのレスポンスをそのままGPTsに返す
        return jsonify(gas_response.json()), gas_response.status_code

    except requests.exceptions.RequestException as e:
        # requestsライブラリのエラー（ネットワーク問題、GAS側のエラーなど）
        return jsonify({
            "status": "error",
            "message": f"Error communicating with GAS Web App: {str(e)}"
        }), 500
    except json.JSONDecodeError:
        # GASからのレスポンスがJSON形式でない場合
        return jsonify({
            "status": "error",
            "message": "Failed to decode JSON response from GAS Web App."
        }), 500
    except Exception as e:
        # その他の予期せぬエラー
        return jsonify({
            "status": "error",
            "message": f"An unexpected error occurred in intermediate API: {str(e)}"
        }), 500

if __name__ == '__main__':
    # 開発環境での実行用 (Renderデプロイ時は不要)
    # ポートはRenderが自動で割り当てるため、os.environ.get('PORT')を使用
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
