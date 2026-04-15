"""
main.py  —  LINE Bot orchestrator
Routing order (cheapest first):
  1. Exact keyword match  → PROFILE, KEYS          (zero cost)
  2. Phrase-list match    → review/回顧 intent      (zero cost)
  3. Gemini API call      → everything else         (uses quota)
"""
import os
import datetime
import zoneinfo
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from dotenv import load_dotenv

from database import get_db, init_db
from models import UserProfile, LogEntry
from functions.key_responses import (
    is_review_intent,
    build_profile_msg,
    build_keys_msg,
    build_review_msg,
    build_summary_flex,
)
from functions.gemini_client import build_prompt, call_gemini
from functions.dialogue_bank import (
    get_offline_script,
    get_reminder_no_exercise,
    get_reminder_exceed_tdee,
)

load_dotenv()

app = FastAPI()
# Ensure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
init_db()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
else:
    line_bot_api = None
    handler = None


# ─────────────────────────────────────────────────────────────────────────────
# DB helper functions
# ─────────────────────────────────────────────────────────────────────────────

def calculate_tdee(weight_kg, body_fat_percentage, age, height_cm):
    """
    Calculates BMR by averaging Mifflin-St Jeor and Katch-McArdle if both are available.
    """
    bmr_results = []

    # 1. Mifflin-St Jeor (Unisex average)
    if weight_kg and age and height_cm:
        msj = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 78
        bmr_results.append(msj)
    
    # 2. Katch-McArdle (Lean Body Mass based)
    if weight_kg and body_fat_percentage:
        katch = 370 + 21.6 * (1 - (body_fat_percentage / 100)) * weight_kg
        bmr_results.append(katch)

    if bmr_results:
        bmr = sum(bmr_results) / len(bmr_results)
    elif weight_kg:
        bmr = weight_kg * 24 # Crude fallback
    else:
        return 2000
        
    return int(bmr * 1.2)


def get_or_create_profile(db, user_id: str) -> tuple[UserProfile, bool]:
    """Fetch existing profile or create one with sensible defaults."""
    profile = db.query(UserProfile).filter_by(line_user_id=user_id).first()
    is_new = False
    if not profile:
        is_new = True
        try:
            profile_name = line_bot_api.get_profile(user_id).display_name
        except Exception:
            profile_name = "User"
        initial_weight, initial_bf = 60.0, 25.0
        profile = UserProfile(
            line_user_id=user_id,
            name=profile_name,
            gender="M",
            age=30,
            height_cm=160.0,
            weight_kg=initial_weight,
            body_fat_percentage=initial_bf,
            target_protein_multiplier=1.2,
            target_calories=calculate_tdee(initial_weight, initial_bf, 30, 160.0),
            timezone="Asia/Taipei",
        )
        db.add(profile)
        db.commit()
    return profile, is_new


def get_today_logs(db, user_id: str, timezone_str: str = "Asia/Taipei") -> list:
    """Return all LogEntry rows for today, ordered by timestamp."""
    try:
        user_tz = zoneinfo.ZoneInfo(timezone_str)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("Asia/Taipei")
        
    now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    now_local = now_utc.astimezone(user_tz)
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = midnight_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    
    return (
        db.query(LogEntry)
        .filter(
            LogEntry.line_user_id == user_id,
            LogEntry.timestamp >= today_start,
        )
        .order_by(LogEntry.timestamp)
        .all()
    )


def get_today_summary(db, user_id: str, timezone_str: str = "Asia/Taipei") -> tuple[float, float]:
    """Return (net_calories, net_protein) for today."""
    logs = get_today_logs(db, user_id, timezone_str)
    net_cal, net_pro = 0.0, 0.0
    for row in logs:
        if row.record_type == "FOOD":
            net_cal += row.calories
            net_pro += row.protein
        elif row.record_type == "EXERCISE":
            net_cal -= row.calories   # Exercise burns calories → subtract
    return net_cal, net_pro


# ─────────────────────────────────────────────────────────────────────────────
# Webhook endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return JSONResponse(content={"message": "OK"})


# ─────────────────────────────────────────────────────────────────────────────
# Message handler
# ─────────────────────────────────────────────────────────────────────────────

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    if not GEMINI_API_KEY:
        return

    db = next(get_db())
    user_id = event.source.user_id

    try:
        profile, is_new = get_or_create_profile(db, user_id)
        
        if is_new:
            welcome_text = (
                f"初次見面，{profile.name}！🐻\n"
                "臉臉需要您的「年齡、身高、體重」才能正確幫您計算一天的代基礎謝率喔！\n"
                "請告訴我：「我 25歲 160公分 50公斤」🐾"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))
            return
            
        user_message = event.message.text.strip()
        msg_upper = user_message.upper()

        # ── Stage 0: Direct database deletion ────────────────────────────────
        if msg_upper in ["刪除今天", "刪除全部", "DELETE ALL", "DELETE TODAY"]:
            try:
                user_tz = zoneinfo.ZoneInfo(profile.timezone)
            except Exception:
                user_tz = zoneinfo.ZoneInfo("Asia/Taipei")
            now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            now_local = now_utc.astimezone(user_tz)
            midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start = midnight_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)

            logs_to_delete = db.query(LogEntry).filter(
                LogEntry.line_user_id == user_id, 
                LogEntry.timestamp >= today_start
            ).all()
            count = len(logs_to_delete)
            for lg in logs_to_delete:
                db.delete(lg)
            db.commit()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"沒有！已清空今日 {count} 筆紀錄！沒有！"))
            return

        if any(msg_upper.startswith(keyword) for keyword in ("刪除", "錯誤", "刪掉")):
            parts = user_message.split()
            if len(parts) > 1 and parts[-1].isdigit():
                local_id = int(parts[-1])
                visible_logs = [log for log in get_today_logs(db, user_id, profile.timezone) if log.record_type != "BODY_UPDATE"]
                if 1 <= local_id <= len(visible_logs):
                    log_to_delete = visible_logs[local_id - 1]
                    db.delete(log_to_delete)
                    db.commit()
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ 已成功刪除紀錄 [ {local_id} ]"))
                    return
                else:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"找不到今日紀錄為 [ {local_id} ] 的項目！無法刪除。"))
                    return

        # ── Stage 1: Zero-cost exact keyword routing ─────────────────────────
        if msg_upper == "PROFILE":
            line_bot_api.reply_message(event.reply_token, build_profile_msg(profile))
            return

        if msg_upper == "KEYS":
            line_bot_api.reply_message(event.reply_token, build_keys_msg())
            return

        # Fetch today's logs — needed for both review and Gemini context
        today_logs = get_today_logs(db, user_id, profile.timezone)

        # ── Stage 2: Zero-cost phrase-list intent routing ────────────────────
        if is_review_intent(user_message):
            messages = [build_review_msg(today_logs, profile)]
            daily_protein_goal = profile.weight_kg * profile.target_protein_multiplier
            net_cal, net_pro = get_today_summary(db, user_id, profile.timezone)
            messages.append(
                build_summary_flex(net_cal, net_pro, profile.target_calories, daily_protein_goal)
            )
            line_bot_api.reply_message(event.reply_token, messages)
            return

        # ── Stage 3: Gemini API routing ──────────────────────────────────────
        # Determine mode and strip command prefix
        if msg_upper.startswith("AI"):
            mode, clean_msg = "chat", user_message[2:].strip()
        elif msg_upper.startswith("FOOD"):
            mode, clean_msg = "food", user_message[4:].strip()
        else:
            mode, clean_msg = "auto", user_message

        # ── Stage 2.5: Script Bank Offline Routing ───────────────────────────
        if mode == "auto":
            offline_reply = get_offline_script(user_message)
            if offline_reply:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=offline_reply))
                return

        prompt = build_prompt(profile, today_logs, clean_msg, mode)

        try:
            data_list = call_gemini(prompt, GEMINI_API_KEY)
        except Exception as api_err:
            err_str = str(api_err)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                reply_text = "臉臉沒有AI 了，臉臉要冬眠了"
            else:
                reply_text = "臉臉要逃跑了，臉臉要去日本了"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return

        # ── Process Gemini response & persist to DB ──────────────────────────
        combined_replies = []
        has_updates = False

        for data in data_list:
            record_type = data.get("type", "CHAT")
            combined_replies.append(data.get("reply_msg", ""))

            if record_type == "DELETE":
                target_id = data.get("target_id")
                visible_logs = [log for log in today_logs if log.record_type != "BODY_UPDATE"]
                if isinstance(target_id, int) and 1 <= target_id <= len(visible_logs):
                    log_to_delete = visible_logs[target_id - 1]
                    real_log_to_delete = db.query(LogEntry).filter_by(id=log_to_delete.id).first()
                    if real_log_to_delete:
                        db.delete(real_log_to_delete)
                        has_updates = True

            elif record_type == "PENDING":
                log_entry = LogEntry(
                    line_user_id=user_id,
                    record_type=record_type,
                    description=data.get("description", "待定營養資訊"),
                )
                db.add(log_entry)

            elif record_type in ["FOOD", "EXERCISE", "BODY_UPDATE"]:
                has_updates = True
                log_entry = LogEntry(
                    line_user_id=user_id,
                    record_type=record_type,
                    description=data.get("description", event.message.text[:50]),
                )

                if record_type in ["FOOD", "EXERCISE"]:
                    log_entry.calories = data.get("calories", 0)
                    log_entry.protein = data.get("protein", 0)
                    log_entry.fat = data.get("fat", 0)
                    log_entry.carbs = data.get("carbs", 0)

                elif record_type == "BODY_UPDATE":
                    w = data.get("weight_kg")
                    bf = data.get("body_fat_percentage")
                    age = data.get("age")
                    h = data.get("height_cm")
                    tz = data.get("timezone")
                    
                    if w is not None:
                        log_entry.weight_kg = w
                    if bf is not None:
                        log_entry.body_fat_percentage = bf
                    if h is not None:
                        log_entry.height_cm = h
                        
                    # Update live profile snapshot → re-calculate TDEE
                    if w: profile.weight_kg = w
                    if bf: profile.body_fat_percentage = bf
                    if age: profile.age = age
                    if h: profile.height_cm = h
                    if tz: profile.timezone = tz
                    
                    profile.target_calories = calculate_tdee(
                        profile.weight_kg, profile.body_fat_percentage, profile.age, profile.height_cm
                    )

                db.add(log_entry)

        db.commit()

        # ── Build reply message list ──────────────────────────────────────────
        header_text = "\n\n".join([r for r in combined_replies if r])
        messages = []

        if header_text:
            messages.append(TextSendMessage(text=header_text))

        # Append Flex summary card only when something was actually logged
        if has_updates:
            daily_protein_goal = profile.weight_kg * profile.target_protein_multiplier
            net_cal, net_pro = get_today_summary(db, user_id, profile.timezone)
            messages.append(
                build_summary_flex(
                    net_cal, net_pro, profile.target_calories, daily_protein_goal
                )
            )

            # --- Reminder Logic ---
            # Re-fetch today_logs to include whatever we just added
            updated_logs = get_today_logs(db, user_id, profile.timezone)
            has_exercised = any(l.record_type == "EXERCISE" for l in updated_logs)
            
            # Re-evaluate if the user just logged a food
            just_logged_food = any(r.get("type") == "FOOD" for r in data_list)

            if just_logged_food:
                # Rule 1: > 1500 cals and no exercise
                if net_cal > 1500 and not has_exercised:
                    messages.append(TextSendMessage(text=get_reminder_no_exercise()))
                # Rule 2: > TDEE
                elif net_cal > profile.target_calories:
                    exceed = net_cal - profile.target_calories
                    messages.append(TextSendMessage(text=get_reminder_exceed_tdee(exceed, profile.weight_kg)))

        if messages:
            # LINE SDK accepts a list for multiple messages (max 5)
            # Ensure we don't exceed max 5 messages by slicing if necessary
            line_bot_api.reply_message(
                event.reply_token,
                messages[:5] if len(messages) > 1 else messages[0],
            )

    except Exception as e:
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"系統錯誤：{str(e)}"),
            )
        except Exception:
            pass
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Image Message handler (Multimodal Vision)
# ─────────────────────────────────────────────────────────────────────────────
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    if not GEMINI_API_KEY:
        return

    db = next(get_db())
    user_id = event.source.user_id

    try:
        profile, is_new = get_or_create_profile(db, user_id)
        
        if is_new:
            welcome_text = (
                f"初次見面，{profile.name}！🐻\n"
                "臉臉需要您的「年齡、身高、體重」才能正確幫您計算一天的代基礎謝率喔！\n"
                "請告訴我：「我 25歲 160公分 50公斤」🐾"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))
            return
        
        # Download image bytes from LINE
        message_content = line_bot_api.get_message_content(event.message.id)
        image_bytes = b"".join([chunk for chunk in message_content.iter_content()])

        today_logs = get_today_logs(db, user_id, profile.timezone)
        prompt = build_prompt(profile, today_logs, "請分析圖片中的食物熱量或營養標示並記錄", "food")

        try:
            data_list = call_gemini(prompt, GEMINI_API_KEY, image_bytes=image_bytes)
        except Exception as api_err:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"圖片 API 回應失敗: {api_err}"),
            )
            return

        # ── Process Gemini response & persist to DB ──────────────────────────
        combined_replies = []
        has_updates = False

        for data in data_list:
            record_type = data.get("type", "CHAT")
            combined_replies.append(data.get("reply_msg", ""))

            if record_type == "PENDING":
                log_entry = LogEntry(
                    line_user_id=user_id,
                    record_type=record_type,
                    description=data.get("description", "照片營養標示(待補全)"),
                )
                db.add(log_entry)

            elif record_type in ["FOOD", "EXERCISE", "BODY_UPDATE"]:
                has_updates = True
                log_entry = LogEntry(
                    line_user_id=user_id,
                    record_type=record_type,
                    description=data.get("description", "照片紀錄"),
                )

                if record_type in ["FOOD", "EXERCISE"]:
                    log_entry.calories = data.get("calories", 0)
                    log_entry.protein = data.get("protein", 0)
                    log_entry.fat = data.get("fat", 0)
                    log_entry.carbs = data.get("carbs", 0)

                db.add(log_entry)

        db.commit()

        # ── Build reply message list ──────────────────────────────────────────
        header_text = "\n\n".join([r for r in combined_replies if r])
        messages = []

        if header_text:
            messages.append(TextSendMessage(text=header_text))

        # Append Flex summary card only when something was actually logged
        if has_updates:
            daily_protein_goal = profile.weight_kg * profile.target_protein_multiplier
            net_cal, net_pro = get_today_summary(db, user_id, profile.timezone)
            messages.append(
                build_summary_flex(
                    net_cal, net_pro, profile.target_calories, daily_protein_goal
                )
            )

        if messages:
            line_bot_api.reply_message(
                event.reply_token,
                messages if len(messages) > 1 else messages[0],
            )

    except Exception as e:
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"圖片處理系統錯誤：{str(e)}"),
            )
        except Exception:
            pass
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
