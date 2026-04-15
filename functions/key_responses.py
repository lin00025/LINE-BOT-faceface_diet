"""
key_responses.py
All zero-cost response builders (no Gemini API calls).

Contains:
  - Intent phrase lists for review detection
  - build_profile_msg()    → PROFILE command
  - build_keys_msg()       → KEYS command
  - build_review_msg()     → today's log review (phrase-triggered)
  - build_summary_flex()   → Flex Message summary card (after DB updates)
"""

from linebot.models import TextSendMessage, FlexSendMessage

# ---------------------------------------------------------------------------
# Intent detection — phrase list for "show me today's log" intent
# Zero API cost: Python string matching only
# ---------------------------------------------------------------------------
REVIEW_TRIGGERS = [
    "回顧", "今天紀錄了", "我吃了什麼", "今日記錄",
    "今天吃什麼", "紀錄了什麼", "查看紀錄",
     "今天喝了什麼", "今天的紀錄", "總結", "統計", "SUMMARY"
]


def is_review_intent(message: str) -> bool:
    """Return True if the message matches any review trigger phrase."""
    return any(phrase in message.upper() for phrase in REVIEW_TRIGGERS)


# ---------------------------------------------------------------------------
# PROFILE command response
# ---------------------------------------------------------------------------
def build_profile_msg(profile) -> TextSendMessage:
    updated_str = (
        profile.updated_at.strftime("%Y-%m-%d %H:%M")
        if profile.updated_at
        else "剛剛"
    )
    text = (
        f"─── 👤 您的個人檔案 ───\n\n"
        f"👤 姓名: {profile.name}\n"
        f"🎂 年齡: {profile.age} 歲\n"
        f"📏 身高: {profile.height_cm} cm\n"
        f"⚖️ 體重: {profile.weight_kg} kg\n"
        f"🍟 體脂: {profile.body_fat_percentage} %\n\n"
        f"📍 時區: {profile.timezone}\n\n"
        f"🎯 TDEE代謝量: {profile.target_calories} 大卡\n"
        f"🥚 蛋白質目標: {profile.target_protein_multiplier}g × 體重(kg)\n"
        f"🕒 最後更新: {updated_str}"
    )
    return TextSendMessage(text=text)


# ---------------------------------------------------------------------------
# KEYS command response
# ---------------------------------------------------------------------------
def build_keys_msg() -> TextSendMessage:
    text = (
        "─── 🐻 臉臉的指令說明 ───\n\n"
        "🔹 [直接輸入] 臉臉會隨便猜測您的意思！\n\n"
        "📌 可用指令：\n\n"
        "1️⃣ FOOD [描述]\n"
        "   強制記錄飲食或運動\n"
        "   例:「FOOD 偷喝了一杯手搖飲」\n\n"
        "2️⃣ AI [問題]\n"
        "   強制知識問答，不影響熱量庫存\n"
        "   例:「AI 早餐吃什麼比較好？」\n\n"
        "3️⃣ PROFILE\n"
        "   查看您的生理數據與 TDEE\n\n"
        "4️⃣ KEYS\n"
        "   顯示此說明頁面\n\n"
        "💡 自動觸發 (免指令！)：\n"
        "   輸入「回顧」或「今天吃了什麼」\n"
        "   臉臉自動整理今日飲食紀錄 🐾\n\n"
        "🔒 隱私保證：本機器人絕不儲存照片\n"
        "   或精確位置等敏感資料。"
    )
    return TextSendMessage(text=text)


# ---------------------------------------------------------------------------
# Review intent response — reads DB logs, returns formatted text (zero LLM)
# ---------------------------------------------------------------------------
def build_review_msg(today_logs, profile) -> TextSendMessage:
    if not today_logs:
        return TextSendMessage(
            text="臉臉摸摸看紀錄本…\n沒有，今天還沒有任何飲食或運動紀錄！\n快去吃雞腿吧 🐻"
        )

    food_lines, exercise_lines, body_lines = [], [], []

    import zoneinfo
    import datetime
    try:
        user_tz = zoneinfo.ZoneInfo(profile.timezone)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("Asia/Taipei")

    visible_id = 1
    for log in today_logs:
        dt_utc = log.timestamp.replace(tzinfo=datetime.timezone.utc)
        t = dt_utc.astimezone(user_tz).strftime("%H:%M")
        
        if log.record_type == "FOOD":
            food_lines.append(
                f"  [ {visible_id} ] {t}  {log.description}\n"
                f"         ({int(log.calories)} 卡｜蛋白質 {int(log.protein)}g)"
            )
            visible_id += 1
        elif log.record_type == "EXERCISE":
            exercise_lines.append(
                f"  [ {visible_id} ] {t}  {log.description}\n"
                f"         (-{int(log.calories)} 卡)"
            )
            visible_id += 1
        elif log.record_type == "PENDING":
            visible_id += 1
        elif log.record_type == "BODY_UPDATE":
            body_lines.append(f"  · {t}  體重 {log.weight_kg} kg")

    lines = ["─── 📋 今日飲食回顧 ───"]
    if food_lines:
        lines.append("\n🍽️ 飲食紀錄:")
        lines.extend(food_lines)
    if exercise_lines:
        lines.append("\n🏃 運動紀錄:")
        lines.extend(exercise_lines)
    if body_lines:
        lines.append("\n⚖️ 體重紀錄:")
        lines.extend(body_lines)
    lines.append("\n🐻 給你捏臉臉的手手")

    return TextSendMessage(text="\n".join(lines))


# ---------------------------------------------------------------------------
# Summary Flex Message — shown after any FOOD / EXERCISE / BODY_UPDATE
# ---------------------------------------------------------------------------
def build_summary_flex(
    net_cal: float,
    net_pro: float,
    target_calories: int,
    daily_protein_goal: float,
) -> FlexSendMessage:
    """
    Build a LINE Flex Message bubble showing today's nutrition summary table.
    Columns: 項目 | 目標 | 今日 | 剩餘
    Color coding: green = on track, red/orange = over/under
    """
    cals_left = int(target_calories - net_cal)
    pro_left = int(daily_protein_goal - net_pro)

    # Green if still within limit, red if over
    cal_color = "#27AE60" if cals_left >= 0 else "#E74C3C"
    # Orange if protein goal not yet met, green if met/exceeded
    pro_color = "#27AE60" if pro_left <= 0 else "#E67E22"

    def header_cell(text):
        return {"type": "text", "text": text, "size": "xs", "color": "#95A5A6",
                "flex": 2, "align": "center"}

    def data_cell(text, color="#34495E", bold=False, flex=2):
        cell = {"type": "text", "text": str(text), "size": "sm",
                "color": color, "flex": flex, "align": "center"}
        if bold:
            cell["weight"] = "bold"
        return cell

    contents = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#2C3E50",
            "paddingAll": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "📊 今日總結",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "md",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": [
                # ── Column header row ──────────────────────────────────────
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "項目", "size": "xs",
                         "color": "#95A5A6", "flex": 3},
                        header_cell("目標"),
                        header_cell("今日"),
                        header_cell("剩餘"),
                    ],
                },
                {"type": "separator", "margin": "sm"},
                # ── Calories row ───────────────────────────────────────────
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {"type": "text", "text": "🔥 熱量",
                         "size": "sm", "flex": 3},
                        data_cell(f"{target_calories}"),
                        data_cell(f"{int(net_cal)}"),
                        data_cell(f"{cals_left}", color=cal_color, bold=True),
                    ],
                },
                # ── Protein row ────────────────────────────────────────────
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": "🥩 蛋白質",
                         "size": "sm", "flex": 3},
                        data_cell(f"{int(daily_protein_goal)}g"),
                        data_cell(f"{int(net_pro)}g"),
                        data_cell(f"{abs(pro_left)}g", color=pro_color, bold=True),
                    ],
                },
                {"type": "separator", "margin": "sm"},
                # ── Unit note ──────────────────────────────────────────────
                {
                    "type": "text",
                    "text": "單位: 大卡 / 公克",
                    "size": "xxs",
                    "color": "#BDC3C7",
                    "align": "end",
                    "margin": "sm",
                },
            ],
        },
    }

    return FlexSendMessage(alt_text="📊 今日總結", contents=contents)
