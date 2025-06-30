import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- 設定変数 ---
# お客様のGASウェブアプリの新しいURL
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbwB6BmqqN9Wpa8CrjAjrC0rBb3yFCggQ3GyQfLHn1w9ne3F52QRM3rnaHAK-J-Q2IpEVw/exec"

# GASコードのEXPECTED_INTERNAL_API_KEYと一致する秘密のキー
INTERNAL_API_KEY = "QUIZ_APP_INTERNAL_API_SECRET_2025" 
INTERNAL_API_KEY_HEADER_NAME = "X-Internal-API-Key"

# --- ヘルパー関数 ---
def send_to_gas(json_payload):
    """
    GASウェブアプリにデータを転送し、レスポンスを取得する
    """
    try:
        headers = {'Content-Type': 'application/json'}
        # ここでカスタムヘッダーを追加
        headers[INTERNAL_API_KEY_HEADER_NAME] = INTERNAL_API_KEY # ヘッダー名はそのままの大文字小文字で渡す

        # GASへのリクエスト
        gas_response = requests.post(GAS_WEB_APP_URL, json=json_payload, headers=headers, timeout=30)
        gas_response.raise_for_status() # HTTPエラーが発生した場合に例外を発生させる
        
        return gas_response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error communicating with GAS: {e}")
        return {"status": "error", "message": f"GASとの通信エラー: {e}"}
    except ValueError as e:
        app.logger.error(f"Error parsing GAS response JSON: {e}, Response text: {gas_response.text if 'gas_response' in locals() else 'N/A'}")
        return {"status": "error", "message": f"GASからのレスポンス解析エラー: {e}"}

# --- APIエンドポイント ---
# GPTスキーマのエンドポイント名に合わせてパスを修正
@app.route('/processQuizAction', methods=['POST']) 
def handle_request():
    """
    GPTsからのPOSTリクエストを受け取り、GASに転送して結果を返すメインエンドポイント
    """
    if not request.is_json:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    gpt_request_payload = request.get_json()
    app.logger.info(f"Received request from GPTs: {gpt_request_payload}")

    # GASにリクエストを転送
    gas_result = send_to_gas(gpt_request_payload)
    
    app.logger.info(f"Response from GAS: {gas_result}")
    
    return jsonify(gas_result), 200

# --- アプリケーションの実行 ---
if __name__ == '__main__':
    # Flask開発サーバーはデバッグ用途。本番環境ではGunicornなどを使用
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
