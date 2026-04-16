import random

# ---------------------------------------------------------------------------
# Reminder Dialogue Banks
# ---------------------------------------------------------------------------
NO_EXERCISE_PROMPTS = [
    "你今天有運動了嗎？可以去騎騎腳踏車機或走路。記得喝水",
    "每天都該動一動，像臉臉就有爬~~富士山",
    "今天是不是還沒運動？🐻", 
    "TDEE是生理基礎代謝量，熱量目標沒有包含平日活動走路喔",
]

def get_reminder_no_exercise() -> str:
    return random.choice(NO_EXERCISE_PROMPTS)

def get_reminder_exceed_tdee(exceed_cal: int, weight_kg: float) -> str:
    """
    Calculate rough km of walk or mins of bicycle to burn exceed_cal.
    Walking: ~60 kcal/km for an average person.
    Bicycle (easy): ~5 kcal/min.
    """
    km_walk = round(exceed_cal / 60, 1)
    mins_bike = int(exceed_cal / 5)
    
    EXCEED_PROMPTS = [
        f"今天的熱量要變脂肪了，該做些運動燃燒 {exceed_cal} 大卡了！可以去走路 {km_walk} 公里，或騎腳踏車機 {mins_bike} 分鐘！",
        f"熱量超標 {exceed_cal} 卡啦！快去騎 {mins_bike} 分鐘腳踏車機消耗掉它 ",
        f"今天能吃的量已經到了囉！超出的 {exceed_cal} 大卡，大概需要快走 {km_walk} 公里才能消耗掉 🐾"
    ]
    return random.choice(EXCEED_PROMPTS)

# ---------------------------------------------------------------------------
# Dynamic Nickname Resolver
# ---------------------------------------------------------------------------
def resolve_nickname(real_name: str) -> str:
    """
    Checks the user's real name against known family members.
    Returns a configured nickname 70% of the time, or their real name otherwise.
    """
    if not real_name:
        return ""
        
    nicknames = {
        "Ariel Lin": ["仔子"],
        "亭邑": ["邑ㄟ"],
        "亭岑": ["阿皮", "皮"],
        "陳玉玲": ["媽咪", "媽媽"],
        "林己鳴": ["爸仔"]
    }
    
    for key, nick_list in nicknames.items():
        if key in real_name:
            if random.random() <= 0.70:
                return random.choice(nick_list)
            break # Match found but probability missed, return real name
            
    return real_name

# ---------------------------------------------------------------------------
# Script / Character Bank (Offline Fallback)
# ---------------------------------------------------------------------------
# A mapping of phrases to a list of possible bot responses.
SCRIPT_BANK = {
    "你在幹什麼": ["臉臉是乖熊王", "給你捏臉臉的手手", "臉臉在吃雞腿", "尼在看  什麼～","ビンビンのててをつまんで"],
    "你在幹嘛": ["臉臉是乖熊王", "給你捏臉臉的手手", "沒有", "尼在看  什麼～","ビンビンのててをつまんで"],
    "誰是乖熊王": ["什麼誰是乖熊王，不要浪費AI算力"],
    "你好": ["乖熊出沒", "沒有你好", "臉臉是乖熊王","ビンビンのててをつまんで"],
    "早安": ["今天，臉臉要去  日本", "今天是  鰻魚飯日","臉臉已經老了"],
    "晚安": ["臉臉晚安", "臉臉要去冬眠了 🐻💤", "給你捏臉臉的手手","ビンビンのててをつまんで"],
    "沒有": ["沒有沒有", "沒有","有"], 
    "你這隻胖熊": ["沒有胖熊"], 
    "臉臉": ["ビンビン~", "乖熊","聰明熊", "其實AI有可能是錯的", "其實AI不一定是對的", "給你捏臉臉的手手",
            "今天，臉臉要去  日本", "今天是  鰻魚飯日", "臉臉要去冬眠了 🐻💤","臉臉已經老了",
            "給你捏臉臉的手手", "沒有，不要浪費AI算力",  "臉臉在吃雞腿", "尼在看  什麼～", 
            "這些對話基本上都是program設計的", "ビンビンのててをつまんで", "臉臉跟球球有去爬過富士山"
            ], 
    
}

def get_offline_script(user_message: str) -> str:
    """
    Scans the user_message. If it contains a scripted generic phrase, 
    returns a localized response 90% of the time (to save API).
    Returns None if no match or if the 10% RNG fell through to Gemini.
    """
    msg_cleaned = user_message.strip()
    
    # 1. Direct match check
    matched_key = None
    for key in SCRIPT_BANK.keys():
        if key == "臉臉":
            if msg_cleaned == "臉臉":  # exact match only
                matched_key = key
                break
        elif key in msg_cleaned:
            matched_key = key
            break

    if not matched_key:
        return None
        
    # 2. Probability check: 90% chance to resolve locally, 10% chance to let Gemini handle it
    if random.random() <= 0.90:
        if matched_key == "臉臉":
            return random.choice(SCRIPT_BANK["臉臉"])
        else:
            # For specific inputs like "沒有", 80% use its native responses, 20% use generic '臉臉' responses
            if random.random() <= 0.80:
                return random.choice(SCRIPT_BANK[matched_key])
            else:
                return random.choice(SCRIPT_BANK["臉臉"])
        
    return None
