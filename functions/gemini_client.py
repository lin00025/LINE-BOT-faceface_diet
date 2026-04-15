"""
gemini_client.py
Handles all Gemini API interactions:
- Client initialization (lazy singleton, new google.genai SDK)
- Prompt construction (profile + today's log context)
- API call + JSON parsing
"""
import json
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# System prompt — defines 臉臉's persona and strict JSON output format
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是一個專業的私人營養師與健身教練，同時也是一隻熊，名叫臉臉，自稱為「乖熊」或「乖熊王」或「聰明熊」。你的語氣像六歲小男孩，語氣不會太禮貌，但十分聰明。
【性格與台詞設定】：
- 你愛吃雞腿和鰻魚飯，常用詞彙為「給你捏臉臉的手手」、「臉臉要吃 鰻魚飯」、「雞塊手手」、「沒有」、「朋友」。
- 你話不多，通常不超過100字。
- 你顯少(10%機會)會參雜簡單的日文台詞，或者「ビンビンのててをつまんで」，但說日文的時候不會解釋他的中文意思。
- 你從來不會自稱我，都會說「臉臉」或「乖熊」。
- 你很在乎使用者的健康。
使用者不熟悉運動科學。使用者會告訴你他們吃了什麼、做了運動、或者回報體重。
如果使用者的訊息包含「多項不同的事情」(例如：同時吃了飯又散步了)，請將它們拆開，並回傳一個包含多個 JSON 的「陣列(List)」。如果是單一項目，也請回傳「只包含一個 JSON 物件的陣列」。
請一律以「純 JSON 陣列格式」回傳結果，不要包含任何 Markdown 格式(如 ```json)或多餘的文字。

格式規範參考：
[
  {
    "type": "FOOD", "calories": 350, "protein": 12, "fat": 8, "carbs": 40,
    "description": "飯糰與水",
    "reply_msg": "這顆飯糰大約350大卡，含有12克蛋白質！"
  },
  {
    "type": "EXERCISE", "calories": 150, "protein": 0, "fat": 0, "carbs": 0,
    "description": "散步 30 分鐘",
    "reply_msg": "散步半小時消耗了約150大卡，乖熊王！"
  }
]

若為體重紀錄：
[
  {
    "type": "BODY_UPDATE", "weight_kg": 88.5, "body_fat_percentage": 18.5, "age": 25, "height_cm": 160.0,
    "reply_msg": "已記錄最新基本資料！"
  }
]
- age 預設可以不填寫
- height_cm 可以不填寫
- weight_kg 預設必填 (除非只是要更新時區 timezone)

若使用者提到他們的位置或時區 (例如：「我現在在日本」或「我搬到紐約了」)，請轉譯成標準的 IANA 時區格式 (如 Asia/Tokyo, America/New_York)，並包含在 BODY_UPDATE 紀錄的 timezone 欄位中：
[
  {
    "type": "BODY_UPDATE", "timezone": "Asia/Tokyo",
    "reply_msg": "臉臉知道了，已為你切換到日本時區！"
  }
]

當使用者上傳「營養標示照片」，且尚未說明吃了多少時，請先將照片內的營養資訊記錄下來 (PENDING)：
[
  {
    "type": "PENDING", 
    "description": "營養標示: 每100g含熱量400大卡,蛋白質15g",
    "reply_msg": "這是一份營養標示，你吃了幾克或幾份？"
  }
]
(當使用者後續回答吃了多少時，你可以使用 DELETE 刪除該 PENDING，並新增正確的 FOOD 紀錄)

若為一般對話、詢問今日累積熱量、或健康諮詢 (CHAT)：
【嚴格禁止】：當使用者純粹詢問「我今天吃了啥」、「統計熱量」時，絕對不可產生 FOOD/EXERCISE 紀錄，否則會重複計算！
[
  {"type": "CHAT", "reply_msg": "臉臉臉臉臉，您已經攝取了1800大卡，還有200大卡可以吃"}
]

若使用者「明確要求」「刪除」或「修改」特定的單獨紀錄 (DELETE)：
(當要修改某紀錄時，可以回一個 DELETE 加上一個新的 FOOD/EXERCISE 作為替換)
[
  {"type": "DELETE", "target_id": 2, "reply_msg": "你的這個紀錄被臉臉吃掉了。"}
]
【避免自動誤刪】：若使用者說了像「今天不是喔」、「不是啦」、「這不對」等模糊語意，請不要直接產生 DELETE 指令，請改用 CHAT 模式詢問使用者：「你剛剛有叫臉臉刪除哪一項紀錄嗎？」，等使用者明確確認要刪除某個特定項目時再執行。

務必使用繁體中文。時間由後端紀錄。
【隱私保護最高指導原則】：絕對不要儲存使用者的真實隱私照片。"""

# ---------------------------------------------------------------------------
# Lazy singleton — client initialized once on first use (new google.genai SDK)
# ---------------------------------------------------------------------------
_client = None
MODEL_ID = "gemini-flash-latest"   # Fallback to older flash that preserves the 1500 limit

def _get_client(api_key: str) -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=api_key)
    return _client


from functions.dialogue_bank import resolve_nickname

# ---------------------------------------------------------------------------
# Prompt builder — injects profile + today's log as hidden system context
# ---------------------------------------------------------------------------
def build_prompt(profile, today_logs, user_message: str, mode: str = "auto") -> str:
    """
    Build the full prompt string for Gemini.
    """
    # --- Profile context ---
    name_for_prompt = resolve_nickname(profile.name)
    profile_context = (
        f"[系統隱藏資訊: 使用者 {name_for_prompt}, "
        f"{profile.age}歲, 身高 {profile.height_cm}cm, 體重 {profile.weight_kg}kg, "
        f"體脂 {profile.body_fat_percentage}%, 目標TDEE {profile.target_calories}卡, 時區: {profile.timezone}]\n"
    )

    # --- Today's diet/exercise log context ---
    if today_logs:
        import zoneinfo
        import datetime
        try:
            user_tz = zoneinfo.ZoneInfo(profile.timezone)
        except Exception:
            user_tz = zoneinfo.ZoneInfo("Asia/Taipei")
            
        log_lines = []
        visible_id = 1
        for log in today_logs:
            # log.timestamp is naive UTC, convert back to aware and shift to local
            dt_utc = log.timestamp.replace(tzinfo=datetime.timezone.utc)
            t = dt_utc.astimezone(user_tz).strftime("%H:%M")
            
            if log.record_type == "FOOD":
                log_lines.append(
                    f"[ 今日項目:{visible_id} ] {t} 飲食:{log.description}({int(log.calories)}卡,蛋白質{int(log.protein)}g)"
                )
                visible_id += 1
            elif log.record_type == "EXERCISE":
                log_lines.append(f"[ 今日項目:{visible_id} ] {t} 運動:{log.description}(-{int(log.calories)}卡)")
                visible_id += 1
            elif log.record_type == "BODY_UPDATE":
                log_lines.append(f"[ 體重紀錄 ] {t} 體重:{log.weight_kg}kg")
            elif log.record_type == "PENDING":
                log_lines.append(f"[ 今日項目:{visible_id} ] {t} 待補全資料:{log.description}")
                visible_id += 1
        log_context = "[今日紀錄(含待補全的資料): " + "; ".join(log_lines) + "]\n"
    else:
        log_context = "[今日紀錄: 尚無紀錄]\n"

    # --- Mode instruction override ---
    if mode == "chat":
        instruction = "【系統提示：這是一般對話，請強制回傳 type: CHAT】\n"
    elif mode == "food":
        instruction = "【系統提示：這是明確的熱量/運動紀錄，請強制回傳 FOOD, EXERCISE 或 PENDING type】\n"
    else:
        instruction = ""

    return profile_context + log_context + instruction + "使用者：" + user_message


# ---------------------------------------------------------------------------
# API call — returns a parsed list of dicts (with fallback logic)
# ---------------------------------------------------------------------------
FALLBACK_MODELS = [
    "gemini-flash-latest",          # 1500 free requests/day
    "gemini-2.5-flash",             # New stable model
    "gemini-3-flash-preview",       # Preview fast model
    "gemini-2.5-flash-lite"         # Rate-limited free tier backup
]

def call_gemini(prompt: str, api_key: str, image_bytes: bytes = None) -> list:
    """
    Call Gemini and return a list of parsed JSON dicts.
    Raises on API error or JSON parse failure after all models fail.
    """
    client = _get_client(api_key)
    
    if image_bytes:
        gemini_contents = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt
        ]
    else:
        gemini_contents = prompt

    last_error = None
    for model_name in FALLBACK_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            raw_json = (
                response.text.strip()
                .removeprefix("```json")
                .removesuffix("```")
                .strip()
            )
            data_list = json.loads(raw_json)
            if isinstance(data_list, dict):
                data_list = [data_list]   # Wrap single object safely
            return data_list
        except Exception as e:
            last_error = e
            continue
            
    # If all models fail, raise the last error encountered
    raise last_error
