import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- 設定変数（Renderに登録済の値をそのまま使用） ---
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzV_YNiM7ToJI6ucWpQ5S6NBrqd9PHDWB4tcHzEJixNof_OBPHv-nqvldl8GqxE5ISH/exec"
INTERNAL_API_KEY = "QUIZ_APP_INTERNAL_API_SECRET_2025"
INTERNAL_API_KEY_HEADER_NAME = "X-Internal-API-Key"

# --- ヘルパー関数 ---
def send_to_gas(json_payload):
    if not GAS_WEB_APP_URL:
        app.logger.error("GAS_WEB_APP_URL is not set.")
        return {"status": "error", "message": "GASウェブアプリのURLが設定されていません。"}
    if not INTERNAL_API_KEY:
        app.logger.error("INTERNAL_API_KEY is not set.")
        return {"status": "error", "message": "APIキーが設定されていません。"}

    try:
        headers = {
            'Content-Type': 'application/json',
            INTERNAL_API_KEY_HEADER_NAME: INTERNAL_API_KEY
        }

        app.logger.info(f"DEBUG: Headers being sent to GAS: {headers}")
        app.logger.info(f"Attempting to send request to GAS URL: {GAS_WEB_APP_URL}")
        app.logger.info(f"Request payload: {json_payload}")

        gas_response = requests.post(GAS_WEB_APP_URL, json=json_payload, headers=headers, timeout=30)
        gas_response.raise_for_status()

        return gas_response.json()

    except requests.exceptions.HTTPError as http_err:
        app.logger.error(f"HTTP error communicating with GAS: {http_err} - Response: {gas_response.text}")
        return {"status": "error", "message": f"GASとの通信エラー（HTTPエラー）: {http_err}. レスポンス: {gas_response.text}"}
    except requests.exceptions.ConnectionError as conn_err:
        app.logger.error(f"Connection error communicating with GAS: {conn_err}")
        return {"status": "error", "message": f"GASとの接続エラー: {conn_err}"}
    except requests.exceptions.Timeout as timeout_err:
        app.logger.error(f"Timeout error communicating with GAS: {timeout_err}")
        return {"status": "error", "message": f"GASとの通信タイムアウト: {timeout_err}"}
    except requests.exceptions.RequestException as e:
        app.logger.error(f"General error communicating with GAS: {e}")
        return {"status": "error", "message": f"GASとの通信エラー: {e}"}
    except ValueError as e:
        app.logger.error(f"Error parsing GAS response JSON: {e}, Response text: {gas_response.text if 'gas_response' in locals() else 'N/A'}")
        return {"status": "error", "message": f"GASからのレスポンス解析エラー: {e}"}

# --- APIエンドポイント ---
@app.route('/processQuizAction', methods=['POST'])
def handle_request():
    if not request.is_json:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    gpt_request_payload = request.get_json()
    app.logger.info(f"Received request from GPTs: {gpt_request_payload}")

    gas_result = send_to_gas(gpt_request_payload)
    app.logger.info(f"Response from GAS: {gas_result}")

    if gas_result.get("status") == "error":
        if "Unauthorized" in gas_result.get("message", ""):
            return jsonify(gas_result), 401
        return jsonify(gas_result), 500

    return jsonify(gas_result), 200

# --- アプリケーションの実行 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
