from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import json
import base64
import gspread
import random
from typing import List, Dict, Union, Optional

app = FastAPI()

# Google Sheets 認証情報を環境変数から読み込む
gc = None
# ★★ 重要: あなたのスプレッドシートIDに置き換えてください ★★
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


# --- インメモリセッション管理 ---
# 注意: これはサーバーが再起動すると失われる一時的なデータです
user_sessions: Dict[str, Dict] = {}

# --- ヘルパー関数群 ---

def _get_spreadsheet_data(sheet_name: str) -> List[List[str]]:
    """指定されたシート名からデータを取得するヘルパー関数"""
    if not spreadsheet:
        raise HTTPException(status_code=500, detail="Google Sheets APIが初期化されていません。")
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        data = worksheet.get_all_values()
        if not data:
            return []
        return data[1:] # ヘッダー行をスキップ
    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"シート名 '{sheet_name}' が見つかりません。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"スプレッドシートの読み込み中にエラーが発生しました: {e}")

def _get_question_from_row(row_data: List[str]) -> Dict[str, Union[str, List[str]]]:
    """スプレッドシートの1行データから問題オブジェクトを整形する"""
    question_id = row_data[COL_QUIZ_ID] if len(row_data) > COL_QUIZ_ID else ""
    question_type = row_data[COL_QUESTION_TYPE] if len(row_data) > COL_QUESTION_TYPE else ""
    question_content = row_data[COL_QUESTION_TEXT] if len(row_data) > COL_QUESTION_TEXT else ""
    explanation = row_data[COL_EXPLANATION] if len(row_data) > COL_EXPLANATION else ""
    category1 = row_data[COL_CATEGORY1] if len(row_data) > COL_CATEGORY1 else ""
    category2 = row_data[COL_CATEGORY2] if len(row_data) > COL_CATEGORY2 else ""
    auto_dummy_flag = row_data[COL_AUTO_DUMMY_FLAG] if len(row_data) > COL_AUTO_DUMMY_FLAG else "OFF"
    auto_dummy_exception = row_data[COL_AUTO_DUMMY_EXCEPTION] if len(row_data) > COL_AUTO_DUMMY_EXCEPTION else ""
    conversation_example = row_data[COL_CONVERSATION_EXAMPLE] if len(row_data) > COL_CONVERSATION_EXAMPLE else ""

    correct_answers = []
    for col_idx in range(COL_CORRECT_ANSWER1, COL_CORRECT_ANSWER4 + 1): # FからI列まで
        if len(row_data) > col_idx and row_data[col_idx].strip():
            correct_answers.append(row_data[col_idx].strip())

    dummy_choices = []
    for col_idx in range(COL_MANUAL_DUMMY1, COL_MANUAL_DUMMY2 + 1):
        if len(row_data) > col_idx and row_data[col_idx].strip():
            dummy_choices.append(row_data[col_idx].strip())

    # ★★ここから修正★★ 選択肢のシャッフルロジックを改善
    all_potential_choices = correct_answers + dummy_choices
    
    # 重複を削除しつつ、順序は保たれないため、一旦セットにしてからリストに戻す
    # ただし、選択肢の順序自体をシャッフルするので、ここでは単に重複を排除する
    unique_all_choices = list(dict.fromkeys(all_potential_choices)) 
    
    print(f"DEBUG: _get_question_from_row - Before final shuffle, unique_all_choices: {unique_all_choices}")
    random.shuffle(unique_all_choices) # ここで全体をランダムにシャッフル
    print(f"DEBUG: _get_question_from_row - After final shuffle, unique_all_choices: {unique_all_choices}")
    # ★★ここまで修正★★

    return {
        "category1": category1,
        "category2": category2,
        "question_id": question_id,
        "question_type": question_type,
        "question_content": question_content,
        "choices": unique_all_choices, # GPTに渡す選択肢は完全にシャッフルされたもの
        "correct_answers": correct_answers, # 正解判定のために正しい答えのリストを返す
        "explanation": explanation,
        "conversation_example": conversation_example,
        "auto_dummy_generation": auto_dummy_flag.upper(),
        "auto_dummy_exception": auto_dummy_exception
    }

def _get_all_category_names() -> List[str]:
    """定義されたトレーニングレベルの順序を返す"""
    return ["Beginner", "Intermediate", "Advanced", "Drink_recipe"]


# --- FastAPI エンドポイント ---

@app.get("/")
async def read_root():
    return {"message": "Hello FastAPI from Render!"}

@app.get("/sheet_data")
async def get_sheet_data(sheet_name: str = "Beginner"):
    """特定のシートの生データを取得する（デバッグ用）"""
    data = _get_spreadsheet_data(sheet_name)
    header_row = spreadsheet.worksheet(sheet_name).row_values(1)
    return {"status": "success", "sheet_name": sheet_name, "header": header_row, "data": data}


class StartTrainingPayload(BaseModel):
    user_name: str
    category: Optional[str] = None
    start_category_index: Optional[int] = None
    start_col_category1_value: Optional[str] = None

@app.post("/start_training")
async def start_training(payload: StartTrainingPayload):
    """トレーニングを開始または再開する"""
    user_name = payload.user_name
    target_category = payload.category
    
    debug_start_category_idx = payload.start_category_index
    debug_start_col_category1_value = payload.start_col_category1_value

    session = {
        "current_level": None,
        "quiz_order": [],
        "current_quiz_index": -1,
        "completed_levels": user_sessions.get(user_name, {}).get("completed_levels", []),
        "is_exam_mode": False,
        "exam_score": 0,
        "total_exam_questions": 0,
        "exam_quiz_order": [],
        "current_exam_quiz_index": -1
    }

    all_levels = _get_all_category_names()
    if not all_levels:
        raise HTTPException(status_code=500, detail="利用可能なクイズレベルが見つかりません。")

    if debug_start_category_idx is not None and 0 <= debug_start_category_idx < len(all_levels):
        level_to_start = all_levels[debug_start_category_idx]
        print(f"DEBUG: Starting from category index {debug_start_category_idx} ({level_to_start})")
    elif target_category:
        if target_category not in all_levels:
            raise HTTPException(status_code=404, detail=f"指定されたカテゴリ「{target_category}」が見つかりません。利用可能なカテゴリ: {all_levels}")
        level_to_start = target_category
    else:
        level_to_start = all_levels[0]
    
    questions_data_raw = _get_spreadsheet_data(level_to_start)
    if not questions_data_raw:
        raise HTTPException(status_code=404, detail=f"選択されたカテゴリ/レベル「{level_to_start}」に設問がありません。")

    session["current_level"] = level_to_start
    
    grouped_by_category1: Dict[str, Dict[str, List[Dict]]] = {}
    ordered_category2_keys_by_cat1: Dict[str, List[str]] = {}

    for idx, row in enumerate(questions_data_raw):
        if len(row) > COL_QUIZ_ID and row[COL_QUIZ_ID].strip() and \
           len(row) > COL_CATEGORY1 and row[COL_CATEGORY1].strip() and \
           len(row) > COL_CATEGORY2 and row[COL_CATEGORY2].strip():
            
            cat1 = row[COL_CATEGORY1].strip()
            cat2 = row[COL_CATEGORY2].strip()
            quiz_id = row[COL_QUIZ_ID].strip()
            
            if cat1 not in grouped_by_category1:
                grouped_by_category1[cat1] = {}
                ordered_category2_keys_by_cat1[cat1] = []
            
            if cat2 not in grouped_by_category1[cat1]:
                grouped_by_category1[cat1][cat2] = []
                ordered_category2_keys_by_cat1[cat1].append(cat2)
            
            grouped_by_category1[cat1][cat2].append({
                "quiz_id": quiz_id,
                "original_row_index": idx,
                "category1_value": cat1
            })

    sorted_category1_keys = []
    for row in questions_data_raw:
        if len(row) > COL_CATEGORY1 and row[COL_CATEGORY1].strip() and \
           row[COL_CATEGORY1].strip() not in sorted_category1_keys:
            sorted_category1_keys.append(row[COL_CATEGORY1].strip())

    final_quiz_order = []
    for cat1 in sorted_category1_keys:
        if cat1 in grouped_by_category1:
            category2_keys = ordered_category2_keys_by_cat1.get(cat1, [])
            for cat2 in category2_keys:
                current_group_quizzes = grouped_by_category1[cat1][cat2]
                random.shuffle(current_group_quizzes)
                final_quiz_order.extend(current_group_quizzes)

    session["quiz_order"] = final_quiz_order
    session["current_quiz_index"] = -1

    if debug_start_col_category1_value:
        found_index = -1
        for i, quiz_info in enumerate(final_quiz_order):
            if quiz_info.get("category1_value") == debug_start_col_category1_value:
                found_index = i
                break
        
        if found_index != -1:
            session["current_quiz_index"] = found_index - 1
            print(f"DEBUG: Starting from COL_CATEGORY1 '{debug_start_col_category1_value}' at quiz order index {found_index}")
        else:
            print(f"WARNING: COL_CATEGORY1 '{debug_start_col_category1_value}' not found in current level. Starting from beginning.")
    
    user_sessions[user_name] = session
    print(f"User {user_name} session started/reset for level: {level_to_start}. Quiz order generated based on Category1 & Category2 fixed order, and internal shuffle.")
    print(f"DEBUG: final_quiz_order: {final_quiz_order}")
    
    return {"status": "success", "message": f"トレーニングを開始します。現在のカテゴリ: {level_to_start}"}


class GetQuestionPayload(BaseModel):
    user_name: str

@app.post("/get_question")
async def get_question(payload: GetQuestionPayload):
    """次の設問を取得する"""
    user_name = payload.user_name
    session = user_sessions.get(user_name)

    if not session or session.get("is_exam_mode"):
        raise HTTPException(status_code=400, detail="有効なトレーニングセッションがありません。または試験モード中です。")

    current_level = session["current_level"]
    quiz_order = session["quiz_order"]
    current_quiz_index = session["current_quiz_index"]

    session["current_quiz_index"] += 1

    if session["current_quiz_index"] >= len(quiz_order):
        if current_level and current_level not in session["completed_levels"]:
            session["completed_levels"].append(current_level)

        all_levels = _get_all_category_names()
        current_level_idx = all_levels.index(current_level) if current_level in all_levels else -1

        if current_level_idx < len(all_levels) - 1:
            next_level = all_levels[current_level_idx + 1]
            
            next_questions_data_raw = _get_spreadsheet_data(next_level)
            if not next_questions_data_raw:
                raise HTTPException(status_code=404, detail=f"次のカテゴリ「{next_level}」には設問がありません。")

            session["current_level"] = next_level
            
            grouped_by_category1_next: Dict[str, Dict[str, List[Dict]]] = {}
            ordered_category2_keys_by_cat1_next: Dict[str, List[str]] = {} 

            for idx, row in enumerate(next_questions_data_raw):
                if len(row) > COL_QUIZ_ID and row[COL_QUIZ_ID].strip() and \
                   len(row) > COL_CATEGORY1 and row[COL_CATEGORY1].strip() and \
                   len(row) > COL_CATEGORY2 and row[COL_CATEGORY2].strip():
                    
                    cat1 = row[COL_CATEGORY1].strip()
                    cat2 = row[COL_CATEGORY2].strip()
                    quiz_id = row[COL_QUIZ_ID].strip()
                    
                    if cat1 not in grouped_by_category1_next:
                        grouped_by_category1_next[cat1] = {}
                        ordered_category2_keys_by_cat1_next[cat1] = [] 
                    if cat2 not in grouped_by_category1_next[cat1]:
                        grouped_by_category1_next[cat1][cat2] = []
                        ordered_category2_keys_by_cat1_next[cat1].append(cat2) 
                    
                    grouped_by_category1_next[cat1][cat2].append({
                        "quiz_id": quiz_id,
                        "original_row_index": idx,
                        "category1_value": cat1
                    })
            
            sorted_category1_keys_next = []
            for row in next_questions_data_raw:
                if len(row) > COL_CATEGORY1 and row[COL_CATEGORY1].strip() and \
                   row[COL_CATEGORY1].strip() not in sorted_category1_keys_next:
                    sorted_category1_keys_next.append(row[COL_CATEGORY1].strip())
            
            final_quiz_order_next = []
            for cat1 in sorted_category1_keys_next:
                if cat1 in grouped_by_category1_next:
                    category2_keys_next = ordered_category2_keys_by_cat1_next.get(cat1, [])
                    for cat2 in category2_keys_next:
                        current_group_quizzes_next = grouped_by_category1_next[cat1][cat2]
                        random.shuffle(current_group_quizzes_next)
                        final_quiz_order_next.extend(current_group_quizzes_next)

            session["quiz_order"] = final_quiz_order_next
            session["current_quiz_index"] = 0
            session["progress_rate"] = 0

            user_sessions[user_name] = session
            return {
                "status": "category_end_and_next",
                "message": f"{current_level}カテゴリが完了しました！次は{next_level}カテゴリに進みます。",
                "progress_rate": 100,
                "next_category": next_level
            }
        else:
            session["progress_rate"] = 100
            user_sessions[user_name] = session
            return {
                "status": "end",
                "message": "すべてのカテゴリが完了しました！",
                "progress_rate": 100
            }
    
    current_quiz_info = quiz_order[session["current_quiz_index"]]
    current_quiz_id = current_quiz_info["quiz_id"]
    original_row_index = current_quiz_info["original_row_index"]

    all_questions_for_level = _get_spreadsheet_data(current_level)
    current_row_data = all_questions_for_level[original_row_index]

    question_object = _get_question_from_row(current_row_data)
    
    total_questions_in_level = len(quiz_order)
    progress_rate = 0
    if total_questions_in_level > 0:
        progress_rate = min(100, int(((session["current_quiz_index"] + 1) / total_questions_in_level) * 100))
    session["progress_rate"] = progress_rate
    
    user_sessions[user_name] = session
    print(f"User {user_name} session progress: {progress_rate}%")

    return {
        "status": "next",
        "message": "次の設問です。",
        "question_data": question_object,
        "progress_rate": progress_rate
    }


class SubmitAnswerPayload(BaseModel):
    user_name: str
    question_id: str
    user_answer: str

@app.post("/submit_answer")
async def submit_answer(payload: SubmitAnswerPayload):
    """ユーザーの回答を評価し、結果を返す"""
    user_name = payload.user_name
    question_id = payload.question_id
    user_answer = payload.user_answer

    session = user_sessions.get(user_name)
    if not session or session.get("is_exam_mode"):
        raise HTTPException(status_code=400, detail="有効なトレーニングセッションがありません。または試験モード中です。")

    current_level = session["current_level"]
    quiz_order = session["quiz_order"]
    current_quiz_index = session["current_quiz_index"]

    if current_quiz_index < 0 or current_quiz_index >= len(quiz_order):
        raise HTTPException(status_code=400, detail="不正なクイズインデックスです。")

    current_quiz_info = quiz_order[current_quiz_index]
    if current_quiz_info["quiz_id"] != question_id:
        raise HTTPException(status_code=400, detail="回答された設問IDが現在の設問と一致しません。")

    all_questions_for_level = _get_spreadsheet_data(current_level)
    current_row_data = all_questions_for_level[current_quiz_info["original_row_index"]]

    # ★★ここを修正★★ 複数の正解を全て取得し、いずれか一つと合致すれば正解
    correct_answers = []
    for col_idx in range(COL_CORRECT_ANSWER1, COL_CORRECT_ANSWER4 + 1): # FからI列まで
        if len(current_row_data) > col_idx and current_row_data[col_idx].strip():
            correct_answers.append(current_row_data[col_idx].strip())

    # 回答判定 (大文字小文字、前後の空白を無視)
    is_correct = any(ans.lower() == user_answer.strip().lower() for ans in correct_answers)
    
    explanation = current_row_data[COL_EXPLANATION] if len(current_row_data) > COL_EXPLANATION else ""

    return {
        "status": "answer_result",
        "is_correct": is_correct,
        "correct_answers": correct_answers, # 複数正解を返す
        "explanation": explanation
    }


class GetCategoryListPayload(BaseModel):
    user_name: str
    purpose: str = "training" # "training" (全カテゴリ) または "review" (復習可能なカテゴリ)

@app.post("/get_category_list")
async def get_category_list(payload: GetCategoryListPayload):
    """利用可能なカテゴリリストを返す"""
    user_name = payload.user_name
    purpose = payload.purpose

    all_sheet_names = _get_all_category_names()
    
    categories = [{"id": name, "name": name} for name in all_sheet_names]
    
    if purpose == "review": 
        session = user_sessions.get(user_name)
        if not session or not session.get("completed_levels"):
            return {"status": "success", "categories": [], "message": "現在、復習可能なカテゴリはありません。"}
        
        completed_levels = session["completed_levels"]
        if session.get("current_level") and session["current_level"] not in completed_levels:
             completed_levels.append(session["current_level"])
        
        categories = [cat for cat in categories if cat["id"] in completed_levels]
        
        if not categories:
            return {"status": "success", "categories": [], "message": "現在、復習可能なカテゴリはありません。"}

    return {"status": "success", "categories": categories}


class ResetTrainingPayload(BaseModel):
    user_name: str

@app.post("/reset_training")
async def reset_training(payload: ResetTrainingPayload):
    """ユーザーのトレーニングセッションをリセットする"""
    user_name = payload.user_name
    if user_name in user_sessions:
        del user_sessions[user_name]
        print(f"User {user_name} session reset.")
    return {"status": "success", "message": "トレーニングセッションがリセットされました。"}

# --- 試験モード関連のエンドポイントは今後の実装 ---
# @app.post("/start_exam")
# async def start_exam(payload: StartExamPayload):
#     pass

# @app.post("/submit_exam_answer")
# async def submit_exam_answer(payload: SubmitExamAnswerPayload):
#     pass
