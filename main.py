# main.py

from fastapi import FastAPI, HTTPException, Depends, Header, status, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import gspread
import pandas as pd
import json
import base64
import os
import random

# --- アプリケーション設定 ---
app = FastAPI(title="BOQUERIA 接客トレーニングAPI", description="BOQUERIAの接客トレーニングをサポートするAPIです。", version="1.0.0")

# --- 環境変数からGoogle認証情報を取得 ---
try:
    credentials_base64 = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_BASE64")
    if not credentials_base64:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_BASE64 環境変数が設定されていません。")
    
    credentials_json = base64.b64decode(credentials_base64).decode("utf-8")
    credentials_info = json.loads(credentials_json)
    
    gc = gspread.service_account_from_dict(credentials_info)
    SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1wWpLpD35606-dKkF-dO0mC_cE9gB0F5tM1bJ9E9tUaE") # デフォルトID
    training_spreadsheet = gc.open_by_key(SPREADSHEET_ID)
except Exception as e:
    print(f"Google Sheets APIの初期化エラー: {e}")
    gc = None
    training_spreadsheet = None

# --- グローバル変数とデータベース代替 ---
# リアルなDBの代わりにメモリ内でセッションを保持
session_db: Dict[str, Any] = {}

def get_session_db():
    return session_db

# --- スプレッドシートデータの取得とキャッシュ ---
sheet_data_cache = {}

def get_all_questions_df():
    """スプレッドシートの全設問データをDataFrameとして取得し、キャッシュする"""
    if 'all_questions_df' in sheet_data_cache:
        return sheet_data_cache['all_questions_df']
    
    if training_spreadsheet is None:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。")

    all_data = []
    available_sheet_names = [ws.title for ws in training_spreadsheet.worksheets()]
    print(f"利用可能なシート名: {available_sheet_names}")
    
    # 初級トレーニング専用のため、'Beginner'シートのみを処理
    if 'Beginner' not in available_sheet_names:
        raise HTTPException(status_code=500, detail="スプレッドシートに 'Beginner' という名前のシートが見つかりません。")

    worksheet = training_spreadsheet.worksheet('Beginner')
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    
    # 必須カラムのチェック
    required_columns = ['sheet_name', 'question_id', 'question_content', 'Category1', 'correct_answer', 'choices', 'explanation', 'auto_dummy_generation']
    if not all(col in df.columns for col in required_columns):
        missing_cols = [col for col in required_columns if col not in df.columns]
        raise HTTPException(status_code=500, detail=f"シートに必須のカラムがありません: {', '.join(missing_cols)}")

    df['sheet_name'] = 'Beginner'
    all_data.append(df)
    
    all_questions_df = pd.concat(all_data, ignore_index=True)
    sheet_data_cache['all_questions_df'] = all_questions_df
    return all_questions_df

# --- ヘルパー関数 ---
def _get_question_from_row(row):
    """データフレームの行から設問情報を抽出するヘルパー関数"""
    return {
        "sheet_name": row['sheet_name'],
        "question_id": row['question_id'],
        "question_content": row['question_content'],
        "Category1": row['Category1'],
        "correct_answer": row['correct_answer'],
        "choices": [c.strip() for c in row['choices'].split(',') if c.strip()],
        "explanation": row['explanation'],
        "auto_dummy_generation": row['auto_dummy_generation']
    }

# --- APIスキーマ定義 ---
class StartTrainingRequest(BaseModel):
    user_name: str
    category: Optional[str] = Field("Beginner", example="Beginner")
    start_category_index: Optional[int] = None
    start_col_category1_value: Optional[str] = None
    # ↓↓↓ 新しいパラメータを追加 ↓↓↓
    start_question_id: Optional[str] = None
    # ↑↑↑ 新しいパラメータを追加 ↑↑↑

class StartTrainingResponse(BaseModel):
    status: str
    message: str

class GetCategoryListRequest(BaseModel):
    user_name: str
    purpose: Optional[str] = "initial"

class CategoryItem(BaseModel):
    category_name: str
    index: int

class GetCategoryListResponse(BaseModel):
    status: str
    categories: List[CategoryItem]

class GetQuestionRequest(BaseModel):
    user_name: str

class GetQuestionResponse(BaseModel):
    status: str
    question_data: Dict[str, Any]
    progress_rate: Optional[int] = None

class SubmitAnswerRequest(BaseModel):
    user_name: str
    question_id: str
    user_answer: str

class SubmitAnswerResponse(BaseModel):
    status: str
    is_correct: bool
    explanation: str
    progress_rate: int
    message: str

class ResetTrainingRequest(BaseModel):
    user_name: str

class ResetTrainingResponse(BaseModel):
    status: str
    message: str

# --- APIエンドポイント ---
@app.post("/sheet_data")
def sheet_data(sheet_name: str):
    """デバッグ用に指定されたシートの生データを返す"""
    if training_spreadsheet is None:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。")
    try:
        worksheet = training_spreadsheet.worksheet(sheet_name)
        return {"sheet_name": sheet_name, "data": worksheet.get_all_records()}
    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"Worksheet '{sheet_name}' not found.")

@app.post("/start_training")
def start_training(request: StartTrainingRequest, db: Dict[str, Any] = Depends(get_session_db)):
    """トレーニングを開始または再開する"""
    user_name = request.user_name
    category = request.category

    if user_name not in db:
        db[user_name] = {"progress": {}, "quiz_order": [], "current_question_index": -1}
    session_data = db[user_name]
    
    try:
        all_questions_df = get_all_questions_df()
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"status": "error", "message": e.detail})

    # デバッグ用にstart_question_idが指定された場合
    if request.start_question_id:
        target_question_row = all_questions_df.loc[all_questions_df['question_id'] == request.start_question_id]
        if target_question_row.empty:
            raise HTTPException(status_code=404, detail="指定された設問IDが見つかりませんでした。")
        
        target_category = target_question_row['sheet_name'].iloc[0]
        if target_category != "Beginner":
            raise HTTPException(status_code=400, detail="このGPTはBeginnerカテゴリの設問からのみ開始できます。")
            
        target_category1_value = target_question_row['Category1'].iloc[0]

        filtered_df = all_questions_df[(all_questions_df['sheet_name'] == target_category) & (all_questions_df['Category1'] == target_category1_value)]
        shuffled_questions = filtered_df.sample(frac=1, random_state=42).to_dict('records')
        
        session_data["quiz_order"] = [_get_question_from_row(pd.Series(q)) for q in shuffled_questions]
        
        try:
            start_index = [q['question_id'] for q in session_data["quiz_order"]].index(request.start_question_id)
            session_data["current_question_index"] = start_index - 1
            return StartTrainingResponse(status="success", message=f"設問ID '{request.start_question_id}'からトレーニングを開始します。")
        except ValueError:
            raise HTTPException(status_code=500, detail="設問IDの特定に失敗しました。")

    # デバッグ用にstart_col_category1_valueが指定された場合
    if request.start_col_category1_value:
        filtered_df = all_questions_df[(all_questions_df['sheet_name'] == 'Beginner') & (all_questions_df['Category1'] == request.start_col_category1_value)]
        if filtered_df.empty:
            raise HTTPException(status_code=404, detail=f"Category1の値 '{request.start_col_category1_value}'が見つかりませんでした。")
            
        shuffled_questions = filtered_df.sample(frac=1, random_state=42).to_dict('records')
        session_data["quiz_order"] = [_get_question_from_row(pd.Series(q)) for q in shuffled_questions]
        session_data["current_question_index"] = -1
        return StartTrainingResponse(status="success", message=f"Category1の値 '{request.start_col_category1_value}'からトレーニングを開始します。")

    # 通常のトレーニング開始または再開
    # ... （以下、既存のロジック）

    return StartTrainingResponse(status="success", message="トレーニングを開始します。")

@app.post("/get_question")
def get_question(request: GetQuestionRequest, db: Dict[str, Any] = Depends(get_session_db)):
    """次の設問を取得する"""
    user_name = request.user_name

    if user_name not in db or "quiz_order" not in db[user_name] or not db[user_name]["quiz_order"]:
        raise HTTPException(status_code=404, detail="トレーニングが開始されていません。")
    
    session_data = db[user_name]
    questions = session_data["quiz_order"]
    current_index = session_data["current_question_index"] + 1

    if current_index >= len(questions):
        # トレーニング完了
        return GetQuestionResponse(status="end", question_data={}, progress_rate=100)

    session_data["current_question_index"] = current_index
    question_data = questions[current_index]

    # プログレスバーの計算（質問数に基づいて計算）
    progress_rate = int(((current_index + 1) / len(questions)) * 100)
    
    return GetQuestionResponse(
        status="next",
        question_data=question_data,
        progress_rate=progress_rate
    )

@app.post("/submit_answer")
def submit_answer(request: SubmitAnswerRequest, db: Dict[str, Any] = Depends(get_session_db)):
    """ユーザーの回答を判定する"""
    user_name = request.user_name

    if user_name not in db or "quiz_order" not in db[user_name] or not db[user_name]["quiz_order"]:
        raise HTTPException(status_code=404, detail="トレーニングが開始されていません。")

    session_data = db[user_name]
    current_index = session_data["current_question_index"]
    questions = session_data["quiz_order"]

    if current_index >= len(questions) or questions[current_index]['question_id'] != request.question_id:
        raise HTTPException(status_code=400, detail="不正な質問IDまたはセッションエラーです。")
    
    current_question = questions[current_index]
    is_correct = (request.user_answer == current_question['correct_answer'])
    
    if is_correct:
        session_data["progress"].setdefault("correct", 0)
        session_data["progress"]["correct"] += 1
    
    progress_rate = int(((current_index + 1) / len(questions)) * 100)
    
    return SubmitAnswerResponse(
        status="answer_result",
        is_correct=is_correct,
        explanation=current_question['explanation'],
        progress_rate=progress_rate,
        message="回答を受け付けました。"
    )

@app.post("/get_category_list")
def get_category_list(request: GetCategoryListRequest):
    """カテゴリリストを取得する"""
    try:
        all_questions_df = get_all_questions_df()
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"status": "error", "message": e.detail})
        
    categories = [{'category_name': 'Beginner', 'index': 0}] # 初級専用のため固定

    return GetCategoryListResponse(status="success", categories=categories)

@app.post("/reset_training")
def reset_training(request: ResetTrainingRequest, db: Dict[str, Any] = Depends(get_session_db)):
    """ユーザーのトレーニング状態をリセットする"""
    if request.user_name in db:
        del db[request.user_name]
        return ResetTrainingResponse(status="success", message="トレーニング状態をリセットしました。")
    return ResetTrainingResponse(status="success", message="リセットするトレーニング状態はありませんでした。")

# ... （以下、試験関連のエンドポイントも同様に実装）
# ... start_exam, submit_exam_answerなど
