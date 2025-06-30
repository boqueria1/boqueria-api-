import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- 設定変数 ---
# GASウェブアプリのURLを環境変数から取得
GAS_WEB_APP_URL = os.environ.get("GAS_WEB_APP_URL", "") # <- ここで環境変数から読み込む

# GASコードのEXPECTED_INTERNAL_API_KEYと一致する秘密のキー
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "") # <- ここで環境変数から読み込む

INTERNAL_API_KEY_HEADER_NAME = "X-Internal-API-Key"

# --- ヘルパー関数 ---
def send_to_gas(json_payload):
    # ... (省略) ...
    # app.logger.info(f"Attempting to send request to GAS URL: {GAS_WEB_APP_URL}") # <-- このログで実際に使われているURLが表示されます

    # ... (省略) ...
