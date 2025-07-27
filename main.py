# main.py
from fastapi import FastAPI, HTTPException
import os
import json
import base64
import gspread

app = FastAPI()

# Google Sheets 認証情報を環境変数から読み込む
# アプリケーション起動時に一度だけ実行
gc = None
SPREADSHEET_ID = "1ZriaRf5UAzzz8q4biKcfr0MxCkOkzf33GyQLCEKngnA" # あなたのスプレッドシートID

try:
    base64_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
    if not base64_credentials:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_BASE64 environment variable not set.")

    decoded_credentials_json = base64.b64decode(base64_credentials).decode('utf-8')
    credentials = json.loads(decoded_credentials_json)
    
    gc = gspread.service_account_from_dict(credentials)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # アプリケーション起動時に、利用可能なシート名をすべて取得し、ログに出力
    available_sheet_names = [ws.title for ws in spreadsheet.worksheets()]
    print(f"利用可能なシート名: {available_sheet_names}")

except Exception as e:
    print(f"Google Sheets APIの初期化エラー: {e}")
    spreadsheet = None # エラー時はNoneを設定

@app.get("/")
async def read_root():
    return {"message": "Hello FastAPI from Render!"}

@app.get("/sheet_data")
async def get_sheet_data(sheet_name: str = "Beginner"): # デフォルトをBeginnerに設定
    if spreadsheet:
        try:
            # 指定されたシート名でワークシートを開く
            worksheet = spreadsheet.worksheet(sheet_name)
            data = worksheet.get_all_values()
            return {"status": "success", "sheet_name": sheet_name, "data": data}
        except gspread.exceptions.WorksheetNotFound:
            raise HTTPException(status_code=404, detail=f"シート名 '{sheet_name}' が見つかりません。利用可能なシートを確認してください。")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"スプレッドシートの読み込み中にエラーが発生しました: {e}")
    else:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。Renderのログを確認してください。")


@app.get("/start_quiz")
async def start_quiz(level: str = "Beginner"):
    # 利用可能なシート名として認識しているもの
    valid_levels = ["Beginner", "Intermediate", "Advanced", "Drink_recipe"] # スプレッドシートのシート名と一致させる

    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"無効なクイズレベルです。利用可能なレベル: {', '.join(valid_levels)}")

    if spreadsheet:
        try:
            # 指定されたレベル（シート名）のワークシートを開く
            worksheet = spreadsheet.worksheet(level)
            all_questions = worksheet.get_all_values()

            # ヘッダー行をスキップする（最初の行が質問や回答のラベルなら）
            if len(all_questions) > 1:
                questions_data = all_questions[1:] # 最初の行をスキップ
            else:
                return {"status": "error", "message": f"'{level}' シートに問題データがありません。"}

            # ここで最初の問題を選択し、整形して返すロジックを実装
            # 仮の例: 最初の問題をそのまま返す
            if questions_data:
                first_question = questions_data[0]
                # ここでfirst_questionをクイズアプリで扱いやすい形式に整形します
                # 例: {"question": first_question[0], "choices": [first_question[1], ...]}
                
                # ここでは単純に最初の問題の行を返すだけ
                return {"status": "success", "level": level, "first_question": first_question, "total_questions": len(questions_data)}
            else:
                return {"status": "error", "message": f"'{level}' シートに有効な問題データが見つかりませんでした。"}

        except gspread.exceptions.WorksheetNotFound:
            raise HTTPException(status_code=404, detail=f"シート名 '{level}' が見つかりません。スプレッドシートのシート名と一致しているか確認してください。")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"クイズの開始中にエラーが発生しました: {e}")
    else:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。Renderのログを確認してください。")
