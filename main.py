# main.py
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
SPREADSHEET_ID = "1ZriaRf5UAzzz8q4biKcfr0MxCkOkzf33GyQLCEKngnA" 

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
COL_CORRECT_ANSWER3 = 7     // H列 (正解3)
COL_CORRECT_ANSWER4 = 8     // I列 (正解4)
COL_MANUAL_DUMMY1 = 9       // J列 (手動ダミー1)
COL_MANUAL_DUMMY2 = 10      // K列 (手動ダミー2)
COL_AUTO_DUMMY_FLAG = 11    // L列 (自動ダミー生成ON/OFF)
COL_AUTO_DUMMY_EXCEPTION = 12 // M列 (ダミー自動生成例外)
COL_EXPLANATION = 13        // N列 (解説)
COL_CONVERSATION_EXAMPLE = 14 // O列 (会話例)


# --- インメモリセッション管理 ---
# 注意: これはサーバーが再起動すると失われる一時的なデータです
user_sessions: Dict[str, Dict] = {}

# セッションデータの型定義 (Pydanticモデルではないが、構造を明確化)
# セッションは辞書として保存される
# {
#   "current_level": "Beginner",
#   "quiz_order": [{"quiz_id": "Q001", "row_index": 1}, ...], # スプレッドシートの行インデックス
#   "current_quiz_index": 0,
#   "completed_levels": ["Beginner", ...],
#   "is_exam_mode": False,
#   "exam_score": 0,
#   "total_exam_questions": 0
# }

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
    for col_idx in range(COL_CORRECT_ANSWER1, COL_CORRECT_ANSWER4 + 1):
        if len(row_data) > col_idx and row_data[col_idx].strip():
            correct_answers.append(row_data[col_idx].strip())

    dummy_choices = []
    for col_idx in range(COL_MANUAL_DUMMY1, COL_MANUAL_DUMMY2 + 1):
        if len(row_data) > col_idx and row_data[col_idx].strip():
            dummy_choices.append(row_data[col_idx].strip())

    all_choices_for_display = correct_answers + dummy_choices
    unique_choices = list(dict.fromkeys(all_choices_for_display)) 
    random.shuffle(unique_choices) 

    return {
        "category1": category1,
        "category2": category2,
        "question_id": question_id,
        "question_type": question_type,
        "question_content": question_content,
        "choices": unique_choices,
        "correct_answers": correct_answers,
        "explanation": explanation,
        "conversation_example": conversation_example,
        "auto_dummy_generation": auto_dummy_flag.upper(),
        "auto_dummy_exception": auto_dummy_exception
    }

def _get_all_category_names() -> List[str]:
    """全シートからユニークなカテゴリ1の名前を取得する"""
    # 現状は "Beginner", "Intermediate", "Advanced", "Drink_recipe" を利用可能なレベルとして定義
    # 将来的には、全シートを読み込んでCOL_CATEGORY1からユニークなカテゴリ名を収集することも可能
    # しかし、現行の Instructions ではシート名をレベルとして扱っているため、シート名リストを返す
    # GASのgetCategoryListでは QUIZ_SHEET_NAME からカテゴリを抽出していたので、それに合わせる
    # ここでは、固定のシート名「Beginner」からカテゴリリストを取得します。
    # GPTsのInstructionsには"Beginner", "Intermediate", "Advanced", "Drink_recipe"
    # がレベルとして記載されているので、ここはそれに合わせるべきか、あるいは全シート名を返すか悩ましい。
    # 一旦、GASのgetCategoryListに合わせ、QUIZ_SHEET_NAME（今回はBeginner固定ではないので、最初のシートのカテゴリとする）
    # からカテゴリを取得するように変更します。しかし、それでは他のレベルシートのカテゴリが取れない。
    # Instructionsに合わせて、ここではシート名をカテゴリとして扱うことにします。
    
    # 実際のスプレッドシートにあるシート名を返すべきだが、今回はGPTsのInstructionsと合わせる
    # "概要" シートはクイズデータを含まない可能性があるので除外
    return ["Beginner", "Intermediate", "Advanced", "Drink_recipe"]


# --- FastAPI エンドポイント ---

@app.get("/")
async def read_root():
    return {"message": "Hello FastAPI from Render!"}

@app.get("/sheet_data")
async def get_sheet_data(sheet_name: str = "Beginner"):
    """特定のシートの生データを取得する（デバッグ用）"""
    data = _get_spreadsheet_data(sheet_name)
    # ヘッダー行を含めて返す
    header_row = spreadsheet.worksheet(sheet_name).row_values(1)
    return {"status": "success", "sheet_name": sheet_name, "header": header_row, "data": data}


class StartTrainingPayload(BaseModel):
    user_name: str
    category: Optional[str] = None # カテゴリ指定がない場合は全体トレーニング

@app.post("/start_training")
async def start_training(payload: StartTrainingPayload):
    """トレーニングを開始または再開する"""
    user_name = payload.user_name
    target_category = payload.category
    
    # ユーザーセッションの初期化またはリセット
    session = {
        "current_level": None, # 現在のトレーニングレベル（シート名）
        "quiz_order": [], # そのレベルの出題順序リスト (quiz_idとスプレッドシートの行インデックスのペア)
        "current_quiz_index": -1, # 現在出題中の設問インデックス
        "completed_levels": user_sessions.get(user_name, {}).get("completed_levels", []), # 以前の完了レベルは引き継ぐ
        "is_exam_mode": False,
        "exam_score": 0,
        "total_exam_questions": 0,
        "exam_quiz_order": [], # 試験モード用
        "current_exam_quiz_index": -1 # 試験モード用
    }

    # トレーニング開始ロジック
    if target_category: # 特定のカテゴリからの開始/復習
        level_to_start = target_category # GPTsのInstructionsではシート名がレベル
    else: # カテゴリ指定なしの場合 (一番最初のカテゴリから開始)
        all_levels = _get_all_category_names() # シート名リスト
        if not all_levels:
            raise HTTPException(status_code=500, detail="利用可能なクイズレベルが見つかりません。")
        level_to_start = sorted(all_levels)[0] # アルファベット順で最初のシート
    
    # 指定されたレベルの設問データを読み込み
    questions_data_raw = _get_spreadsheet_data(level_to_start)
    if not questions_data_raw:
        raise HTTPException(status_code=404, detail=f"選択されたカテゴリ/レベル「{level_to_start}」に設問がありません。")

    # セッションに問題リストと出題順をセット
    session["current_level"] = level_to_start
    session["quiz_order"] = []
    # 各問題にスプレッドシートの行インデックスを付与して保存 (後で元のデータを参照するため)
    # questions_data_raw はヘッダーを除いたデータなので、元のスプレッドシートの行インデックスは +1 される
    for idx, row in enumerate(questions_data_raw):
        if len(row) > COL_QUIZ_ID and row[COL_QUIZ_ID].strip(): # 設問IDが存在するもののみ対象
             session["quiz_order"].append({
                "quiz_id": row[COL_QUIZ_ID].strip(),
                "original_row_index": idx # questions_data_raw 内でのインデックス (0から始まる)
            })
    
    # 出題順序をシャッフル
    random.shuffle(session["quiz_order"])
    session["current_quiz_index"] = -1 # 最初の問題の前に設定

    user_sessions[user_name] = session
    print(f"User {user_name} session started/reset for level: {level_to_start}")
    
    return {"status": "success", "message": f"トレーニングを開始します。現在のカテゴリ: {level_to_start}"}


class GetQuestionPayload(BaseModel):
    user_name: str

@app.post("/get_question")
async def get_question(payload: GetQuestionPayload):
    """次の設問を取得する"""
    user_name = payload.user_name
    session = user_sessions.get(user_name)

    if not session or session.get("is_exam_mode"): # 試験モード中は通常のget_questionは許可しない
        raise HTTPException(status_code=400, detail="有効なトレーニングセッションがありません。または試験モード中です。")

    current_level = session["current_level"]
    quiz_order = session["quiz_order"]
    current_quiz_index = session["current_quiz_index"]

    session["current_quiz_index"] += 1 # 次の設問へ進む

    # カテゴリ内のすべての設問が完了した場合の処理
    if session["current_quiz_index"] >= len(quiz_order):
        # 現在のカテゴリを完了済みにマーク (重複は避ける)
        if current_level and current_level not in session["completed_levels"]:
            session["completed_levels"].append(current_level)

        all_levels_sorted = sorted(_get_all_category_names())
        current_level_idx = all_levels_sorted.index(current_level) if current_level in all_levels_sorted else -1

        if current_level_idx < len(all_levels_sorted) - 1:
            # 次のカテゴリがある場合
            next_level = all_levels_sorted[current_level_idx + 1]
            
            # 次のレベルの設問データを読み込み
            next_questions_data_raw = _get_spreadsheet_data(next_level)
            if not next_questions_data_raw:
                # 次のカテゴリに設問がない場合、さらにその次のカテゴリを探すか、エラーとする
                # ここでは一旦、設問がないことを伝えるエラーとする
                raise HTTPException(status_code=404, detail=f"次のカテゴリ「{next_level}」には設問がありません。")

            session["current_level"] = next_level
            session["quiz_order"] = []
            for idx, row in enumerate(next_questions_data_raw):
                if len(row) > COL_QUIZ_ID and row[COL_QUIZ_ID].strip():
                    session["quiz_order"].append({
                        "quiz_id": row[COL_QUIZ_ID].strip(),
                        "original_row_index": idx
                    })
            random.shuffle(session["quiz_order"])
            session["current_quiz_index"] = 0 # 次のカテゴリの最初の設問へ
            session["progress_rate"] = 0 # 新しいカテゴリの進捗をリセット

            user_sessions[user_name] = session
            return {
                "status": "category_end_and_next",
                "message": f"{current_level}カテゴリが完了しました！次は{next_level}カテゴリに進みます。",
                "progress_rate": 100 # 直前のカテゴリの完了進捗
            }
        else:
            # 全てのカテゴリが終了した場合
            session["progress_rate"] = 100
            user_sessions[user_name] = session
            return {
                "status": "end",
                "message": "すべてのカテゴリが完了しました！",
                "progress_rate": 100
            }
    
    # 通常の設問取得
    current_quiz_info = quiz_order[session["current_quiz_index"]]
    current_quiz_id = current_quiz_info["quiz_id"]
    original_row_index = current_quiz_info["original_row_index"]

    # スプレッドシートから生の行データを再取得（毎回シートから読むのは非効率だが、インメモリではこれが確実）
    all_questions_for_level = _get_spreadsheet_data(current_level)
    current_row_data = all_questions_for_level[original_row_index]

    question_object = _get_question_from_row(current_row_data)
    
    # 進捗率の計算
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

    # 正解のリストを取得 (空でないものを格納)
    correct_answers = []
    for col_idx in range(COL_CORRECT_ANSWER1, COL_CORRECT_ANSWER4 + 1):
        if len(current_row_data) > col_idx and current_row_data[col_idx].strip():
            correct_answers.append(current_row_data[col_idx].strip())

    # 回答判定 (大文字小文字、前後の空白を無視)
    is_correct = any(ans.lower() == user_answer.strip().lower() for ans in correct_answers)
    
    explanation = current_row_data[COL_EXPLANATION] if len(current_row_data) > COL_EXPLANATION else ""

    # セッションの進捗率は get_question で更新されるので、ここでは更新しない（GASのsubmitAnswerも同様）

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

    all_sheet_names = _get_all_category_names() # 現状は固定リスト
    
    categories = [{"id": name, "name": name} for name in all_sheet_names]
    
    if purpose == "review":
        session = user_sessions.get(user_name)
        if not session or not session.get("completed_levels"):
            return {"status": "success", "categories": [], "message": "現在、復習可能なカテゴリはありません。"}
        
        completed_levels = session["completed_levels"]
        # 現在進行中のカテゴリも復習対象に含める（ただし既に完了済みでなければ）
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
