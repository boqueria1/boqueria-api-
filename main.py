# main.py
from fastapi import FastAPI
import os
import json
import base64 # 追加: Base64デコードのために必要
import gspread # 追加

app = FastAPI()

# Google Sheets 認証情報を環境変数から読み込む
# JSONキーファイルの中身をBase64デコードして使用
# Renderの環境変数に設定した GOOGLE_APPLICATION_CREDENTIALS_BASE64 を使用
try:
    # Base64エンコードされた文字列を取得
    base64_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
    if not base64_credentials:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_BASE64 environment variable not set.")

    # Base64デコード
    decoded_credentials_json = base64.b64decode(base64_credentials).decode('utf-8')
    
    # JSON文字列をPythonの辞書に変換
    credentials = json.loads(decoded_credentials_json)

    # gspreadで認証
    gc = gspread.service_account_from_dict(credentials)

    # ここにあなたのスプレッドシートのIDを記述してください
    # スプレッドシートのURL例: https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit
    # 'YOUR_SPREADSHEET_ID' の部分を置き換える
    SPREADSHEET_ID = "1ZriaRf5UAzzz8q4biKcfr0MxCkOkzf33GyQLCEKngnA" # ここをあなたのスプレッドシートIDに置き換えました
    
    # スプレッドシートを開く
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.sheet1 # 最初のシート（Sheet1）を開く

    # スプレッドシートからデータを読み込むテスト（例）
    # アプリケーション起動時に、このデータがRenderのログに出力されます
    sample_data = worksheet.get_all_values()
    print("スプレッドシートから読み込んだデータ（初期ロード時）:", sample_data)

except Exception as e:
    print(f"Google Sheets APIの初期化エラー: {e}")
    # エラー時は gspread のオブジェクトを None に設定
    # これにより、後続のAPIエンドポイントでエラー処理が可能になります
    gc = None 
    spreadsheet = None
    worksheet = None
    sample_data = "Google Sheets APIの初期化に失敗しました。詳細はRenderのログを確認してください。"


@app.get("/")
async def read_root():
    return {"message": "Hello FastAPI from Render!"}

@app.get("/sheet_data")
async def get_sheet_data():
    if worksheet:
        try:
            # 最新のデータを取得
            data = worksheet.get_all_values()
            return {"status": "success", "data": data}
        except Exception as e:
            # スプレッドシート読み込み時のエラーを返す
            return {"status": "error", "message": f"スプレッドシートの読み込み中にエラーが発生しました: {e}"}
    else:
        # Google Sheets APIが初期化されていない場合のエラー
        return {"status": "error", "message": "Google Sheets APIが初期化されていません。Renderのログを確認してください。"}
