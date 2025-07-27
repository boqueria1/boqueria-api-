# main.py
from fastapi import FastAPI, HTTPException
import os
import json
import base64
import gspread
import random
from typing import List, Dict, Union

app = FastAPI()

# Google Sheets 認証情報を環境変数から読み込む
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

    available_sheet_names = [ws.title for ws in spreadsheet.worksheets()]
    print(f"利用可能なシート名: {available_sheet_names}")

except Exception as e:
    print(f"Google Sheets APIの初期化エラー: {e}")
    spreadsheet = None 

# スプレッドシートのカラムインデックス定義（0から始まる）
# GASの定義と完全に一致させました
COL_CATEGORY1 = 0           # A列
COL_CATEGORY2 = 1           # B列
COL_QUIZ_ID = 2             # C列
COL_QUESTION_TYPE = 3       # D列 (出題形式)
COL_QUESTION_TEXT = 4       # E列 (設問内容)
COL_CORRECT_ANSWER1 = 5     # F列 (正解1)
COL_CORRECT_ANSWER2 = 6     # G列 (正解2)
COL_CORRECT_ANSWER3 = 7     # H列 (正解3)
COL_CORRECT_ANSWER4 = 8     # I列 (正解4)
COL_MANUAL_DUMMY1 = 9       # J列 (手動ダミー1)
COL_MANUAL_DUMMY2 = 10      # K列 (手動ダミー2)
COL_AUTO_DUMMY_FLAG = 11    # L列 (自動ダミー生成ON/OFF)
COL_AUTO_DUMMY_EXCEPTION = 12 # M列 (ダミー自動生成例外)
COL_EXPLANATION = 13        # N列 (解説)
COL_CONVERSATION_EXAMPLE = 14 # O列 (会話例)

@app.get("/")
async def read_root():
    return {"message": "Hello FastAPI from Render!"}

@app.get("/sheet_data")
async def get_sheet_data(sheet_name: str = "Beginner"):
    if spreadsheet:
        try:
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
    # 利用可能なシート名 (GASコードのQUIZ_SHEET_NAMEではなく、実際のシート名から取得)
    # あなたのGASコードでは QUIZ_SHEET_NAME が固定されていましたが、
    # FastAPIではURLパラメータ `level` で指定されたシートを開きます。
    valid_levels = ["Beginner", "Intermediate", "Advanced", "Drink_recipe", "概要"] # 概要シートも含む
    
    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"無効なクイズレベルです。利用可能なレベル: {', '.join(valid_levels)}")

    if spreadsheet:
        try:
            # 指定されたレベル（シート名）のワークシートを開く
            worksheet = spreadsheet.worksheet(level)
            all_rows = worksheet.get_all_values()

            if not all_rows:
                raise HTTPException(status_code=404, detail=f"'{level}' シートにデータがありません。")

            # ヘッダー行をスキップ
            questions_data = all_rows[1:] 
            
            if not questions_data:
                raise HTTPException(status_code=404, detail=f"'{level}' シートに有効な問題データが見つかりませんでした。")

            # ここでランダムに1問選択
            selected_row = random.choice(questions_data)

            # 設問データを整形する
            # 各カラムが存在するか、インデックス範囲を確認
            question_id = selected_row[COL_QUIZ_ID] if len(selected_row) > COL_QUIZ_ID else ""
            question_type = selected_row[COL_QUESTION_TYPE] if len(selected_row) > COL_QUESTION_TYPE else ""
            question_content = selected_row[COL_QUESTION_TEXT] if len(selected_row) > COL_QUESTION_TEXT else ""
            explanation = selected_row[COL_EXPLANATION] if len(selected_row) > COL_EXPLANATION else ""
            category1 = selected_row[COL_CATEGORY1] if len(selected_row) > COL_CATEGORY1 else ""
            category2 = selected_row[COL_CATEGORY2] if len(selected_row) > COL_CATEGORY2 else ""
            auto_dummy_flag = selected_row[COL_AUTO_DUMMY_FLAG] if len(selected_row) > COL_AUTO_DUMMY_FLAG else "OFF"
            auto_dummy_exception = selected_row[COL_AUTO_DUMMY_EXCEPTION] if len(selected_row) > COL_AUTO_DUMMY_EXCEPTION else ""
            conversation_example = selected_row[COL_CONVERSATION_EXAMPLE] if len(selected_row) > COL_CONVERSATION_EXAMPLE else ""


            # 正解のリストを作成 (空でないものを格納)
            correct_answers = []
            for col_idx in range(COL_CORRECT_ANSWER1, COL_CORRECT_ANSWER4 + 1):
                if len(selected_row) > col_idx and selected_row[col_idx].strip():
                    correct_answers.append(selected_row[col_idx].strip())

            # ダミー選択肢のリストを作成 (空でないものを格納)
            dummy_choices = []
            for col_idx in range(COL_DUMMY_1, COL_DUMMY_2 + 1):
                if len(selected_row) > col_idx and selected_row[col_idx].strip():
                    dummy_choices.append(selected_row[col_idx].strip())

            # すべての選択肢をまとめる（正解 + 手動ダミー）
            all_choices_for_display = correct_answers + dummy_choices
            # 重複を排除し、ランダムに並べ替える
            unique_choices = list(dict.fromkeys(all_choices_for_display)) # 順序を保持しつつ重複排除
            random.shuffle(unique_choices) # シャッフル

            # クライアントに返す問題オブジェクトの形式
            question_object = {
                "category1": category1,
                "category2": category2,
                "question_id": question_id,
                "question_type": question_type, # 出題形式
                "question_content": question_content,
                "choices": unique_choices, # 表示用の選択肢（シャッフル済み）
                "correct_answers": correct_answers, # 正解のリスト
                "explanation": explanation,
                "conversation_example": conversation_example,
                "auto_dummy_generation": auto_dummy_flag.upper(), # 'ON'/'OFF'
                "auto_dummy_exception": auto_dummy_exception
            }
            
            return {"status": "success", "level": level, "question": question_object}

        except gspread.exceptions.WorksheetNotFound:
            raise HTTPException(status_code=404, detail=f"シート名 '{level}' が見つかりません。スプレッドシートのシート名と一致しているか確認してください。")
        except IndexError as e:
            raise HTTPException(status_code=500, detail=f"スプレッドシートの列のインデックスエラーが発生しました。スプレッドシートの構造と COL_定数を確認してください。詳細: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"クイズの開始中にエラーが発生しました: {e}")
    else:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。Renderのログを確認してください。")

# --- 回答判定のエンドポイント（GASの submitAnswer を参考に実装）---
from pydantic import BaseModel # POSTリクエストのボディを定義するために必要

class AnswerPayload(BaseModel):
    level: str # 回答したクイズのレベル（シート名）
    question_id: str # 回答した設問のID
    user_answer: str # ユーザーの回答テキスト

@app.post("/submit_answer")
async def submit_answer(payload: AnswerPayload):
    level = payload.level
    question_id = payload.question_id
    user_answer = payload.user_answer

    # 利用可能なシート名 (GASコードのQUIZ_SHEET_NAMEではなく、実際のシート名から取得)
    valid_levels = ["Beginner", "Intermediate", "Advanced", "Drink_recipe", "概要"] 

    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"無効なクイズレベルです。利用可能なレベル: {', '.join(valid_levels)}")

    if spreadsheet:
        try:
            worksheet = spreadsheet.worksheet(level)
            all_rows = worksheet.get_all_values()

            if not all_rows:
                raise HTTPException(status_code=404, detail=f"'{level}' シートにデータがありません。")

            questions_data = all_rows[1:] # ヘッダー行をスキップ

            # 設問IDを使って該当する問題を探す
            current_quiz_data = None
            for row in questions_data:
                if len(row) > COL_QUIZ_ID and row[COL_QUIZ_ID].strip() == question_id.strip():
                    current_quiz_data = row
                    break
            
            if not current_quiz_data:
                raise HTTPException(status_code=404, detail=f"設問ID '{question_id}' がシート '{level}' に見つかりません。")

            # 正解のリストを取得 (空でないものを格納)
            correct_answers = []
            for col_idx in range(COL_CORRECT_ANSWER1, COL_CORRECT_ANSWER4 + 1):
                if len(current_quiz_data) > col_idx and current_quiz_data[col_idx].strip():
                    correct_answers.append(current_quiz_data[col_idx].strip())

            # 回答判定 (大文字小文字、前後の空白を無視)
            is_correct = any(ans.lower() == user_answer.strip().lower() for ans in correct_answers)
            
            explanation = current_quiz_data[COL_EXPLANATION] if len(current_quiz_data) > COL_EXPLANATION else ""

            return {
                "status": "answer_result",
                "is_correct": is_correct,
                "correct_answers": correct_answers, # 複数正解を返す
                "explanation": explanation
            }

        except gspread.exceptions.WorksheetNotFound:
            raise HTTPException(status_code=404, detail=f"シート名 '{level}' が見つかりません。")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"回答の判定中にエラーが発生しました: {e}")
    else:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。")
