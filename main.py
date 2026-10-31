from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
import json
import os
from datetime import datetime, timezone

TOKEN = "9199911982:AAFFq49hIXqIZQVPCgWSoeya-CHNd2wkk8M"
FOOTBALL_API_KEY = "f6f1acb1e82646bc8f6890ae908bd9fb"
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

SUBSCRIBERS_FILE = "subscribers.json"
SENT_REMINDERS_FILE = "sent_reminders.json"

CATEGORIES = {
    "continental": {
        "title": "🏆 البطولات القارية",
        "items": {"دوري أبطال أوروبا": "CL"},
    },
    "european": {
        "title": "🌍 الدوريات الأوروبية الكبرى",
        "items": {
            "🏴 الدوري الإنجليزي": "PL",
            "🇪🇸 الدوري الإسباني": "PD",
            "🇮🇹 الدوري الإيطالي": "SA",
            "🇩🇪 الدوري الألماني": "BL1",
            "🇫🇷 الدوري الفرنسي": "FL1",
        },
    },
}

ALL_COMPETITIONS = {}
for cat in CATEGORIES.values():
    ALL_COMPETITIONS.update(cat["items"])

# علامات عزل الاتجاه لمنع تشتت النصوص اللاتينية داخل جملة عربية
LRI = "\u2066"   # بداية عزل اتجاه من اليسار لليمين
PDI = "\u2069"   # نهاية العزل

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def esc(text):
    text = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"{LRI}{text}{PDI}"  # عزل اتجاه النص

def box(title):
    return f"┏━━━━━━━━━━━━━━━┓\n   {title}\n┗━━━━━━━━━━━━━━━┛\n\n"

# ===================== القوائم =====================

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚡ أقرب المباريات (كل الدوريات)", callback_data="quick_matches")],
        [InlineKeyboardButton("📅 مباريات حسب الدوري", callback_data="menu_matches")],
        [InlineKeyboardButton("📊 ترتيب الدوريات", callback_data="menu_standings")],
        [InlineKeyboardButton("🔔 تفعيل / إيقاف التذكيرات", callback_data="toggle_remind")],
    ]
    return InlineKeyboardMarkup(keyboard)

def categories_keyboard(prefix):
    keyboard = []
    for cat_key, cat in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat["title"], callback_data=f"cat_{prefix}_{cat_key}")])
    keyboard.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def leagues_in_category_keyboard(prefix, cat_key):
    keyboard = []
    for name, code in CATEGORIES[cat_key]["items"].items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"{prefix}_{code}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع للتصنيفات", callback_data=f"menu_{prefix}")])
    keyboard.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def result_keyboard(prefix, code):
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث", callback_data=f"{prefix}_{code}")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_main_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")]])

def get_competition_name(code):
    for name, c in ALL_COMPETITIONS.items():
        if c == code:
            return name
    return ""

# ===================== الأوامر =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = box("⚽ بوت متابعة المباريات") + "مرحباً بك! اختر خدمة من القائمة:"
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        text = box("⚽ القائمة الرئيسية") + "اختر خدمة من القائمة:"
        await query.edit_message_text(text, reply_markup=main_menu_keyboard())
        return

    if data == "menu_matches":
        text = box("📅 مباريات حسب الدوري") + "اختر تصنيف البطولة:"
        await query.edit_message_text(text, reply_markup=categories_keyboard("matches"))
        return

    if data == "menu_standings":
        text = box("📊 ترتيب الدوريات") + "اختر تصنيف البطولة:"
        await query.edit_message_text(text, reply_markup=categories_keyboard("standings"))
        return

    if data.startswith("cat_"):
        _, prefix, cat_key = data.split("_", 2)
        text = box(CATEGORIES[cat_key]["title"]) + "اختر البطولة:"
        await query.edit_message_text(text, reply_markup=leagues_in_category_keyboard(prefix, cat_key))
        return

    if data.startswith("matches_"):
        code = data.split("_")[1]
        await query.edit_message_text("⏳ جاري تحميل المباريات...")
        await send_matches(query, code)
        return

    if data.startswith("standings_"):
        code = data.split("_")[1]
        await query.edit_message_text("⏳ جاري تحميل الترتيب...")
        await send_standings(query, code)
        return

    if data == "quick_matches":
        await query.edit_message_text("⏳ جاري البحث عن أقرب المباريات في كل الدوريات...")
        await send_quick_matches(query)
        return

    if data == "toggle_remind":
        subs = load_json(SUBSCRIBERS_FILE)
        chat_id = query.message.chat.id
        if chat_id in subs:
            subs.remove(chat_id)
            save_json(SUBSCRIBERS_FILE, subs)
            await query.answer("🔕 تم إيقاف التذكيرات بنجاح", show_alert=True)
        else:
            subs.append(chat_id)
            save_json(SUBSCRIBERS_FILE, subs)
            await query.answer("🔔 تم تفعيل التذكيرات!\nستصلك رسالة قبل 30 دقيقة من كل مباراة", show_alert=True)

# ===================== عرض المباريات =====================

async def send_matches(query, code):
    comp_name = get_competition_name(code)
    try:
        r = requests.get(f"{BASE_URL}/competitions/{code}/matches?status=SCHEDULED,LIVE,FINISHED", headers=HEADERS, timeout=10)
        matches = r.json().get("matches", [])[:8]

        text = box(f"⚽ {comp_name}")

        if not matches:
            text += "لا توجد مباريات متاحة حالياً."
        else:
            for i, m in enumerate(matches, 1):
                home, away = esc(m["homeTeam"]["name"]), esc(m["awayTeam"]["name"])
                status = m["status"]

                if status == "FINISHED":
                    hs, aws = m['score']['fullTime']['home'], m['score']['fullTime']['away']
                    text += f"✅ النتيجة النهائية\n{home}  {hs} - {aws}  {away}\n"
                elif status in ("LIVE", "IN_PLAY"):
                    hs, aws = m['score']['fullTime']['home'], m['score']['fullTime']['away']
                    text += f"🔴 مباشر الآن\n{home}  {hs} - {aws}  {away}\n"
                else:
                    d = m["utcDate"]
                    text += f"🕐 الموعد: {d[8:10]}/{d[5:7]} — {d[11:16]}\n{home}  ضد  {away}\n"

                if i < len(matches):
                    text += "┄┄┄┄┄┄┄┄┄┄┄┄┄\n"

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=result_keyboard("matches", code))
    except Exception:
        text = box(f"⚽ {comp_name}") + "❌ تعذّر جلب البيانات، حاول لاحقاً."
        await query.edit_message_text(text, reply_markup=result_keyboard("matches", code))

async def send_quick_matches(query):
    text = box("⚡ أقرب المباريات القادمة")
    found_any = False

    try:
        for name, code in ALL_COMPETITIONS.items():
            r = requests.get(f"{BASE_URL}/competitions/{code}/matches?status=SCHEDULED", headers=HEADERS, timeout=8)
            matches = r.json().get("matches", [])[:2]
            if not matches:
                continue
            found_any = True
            text += f"🏆 {esc(name)}\n"
            for m in matches:
                home, away = esc(m["homeTeam"]["name"]), esc(m["awayTeam"]["name"])
                d = m["utcDate"]
                text += f"🕐 {d[8:10]}/{d[5:7]} {d[11:16]}\n{home}  ضد  {away}\n"
            text += "┄┄┄┄┄┄┄┄┄┄┄┄┄\n"

        if not found_any:
            text += "لا توجد مباريات مجدولة قريباً."

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_main_keyboard())
    except Exception:
        text = box("⚡ أقرب المباريات") + "❌ تعذّر جلب البيانات، حاول لاحقاً."
        await query.edit_message_text(text, reply_markup=back_main_keyboard())

# ===================== عرض الترتيب =====================

async def send_standings(query, code):
    comp_name = get_competition_name(code)
    try:
        r = requests.get(f"{BASE_URL}/competitions/{code}/standings", headers=HEADERS, timeout=10)
        table = r.json()["standings"][0]["table"][:10]

        text = box(f"📊 ترتيب {comp_name}")
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        for team in table:
            pos = team["position"]
            name = esc(team["team"]["name"])
            points = team["points"]
            played = team["playedGames"]
            w, d, l = team["won"], team["draw"], team["lost"]
            icon = medals.get(pos, f"#{pos}")

            text += f"{icon}  {name}\n"
            text += f"      النقاط: {points}  |  المباريات: {played}\n"
            text += f"      فوز: {w}  تعادل: {d}  خسارة: {l}\n"
            text += "┄┄┄┄┄┄┄┄┄┄┄┄┄\n"

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=result_keyboard("standings", code))
    except Exception:
        text = box(f"📊 ترتيب {comp_name}") + "❌ تعذّر جلب البيانات، حاول لاحقاً."
        await query.edit_message_text(text, reply_markup=result_keyboard("standings", code))

# ===================== التذكيرات =====================

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    subs = load_json(SUBSCRIBERS_FILE)
    if not subs:
        return
    sent = load_json(SENT_REMINDERS_FILE)

    for name, code in ALL_COMPETITIONS.items():
        try:
            r = requests.get(f"{BASE_URL}/competitions/{code}/matches?status=TIMED", headers=HEADERS, timeout=10)
            matches = r.json().get("matches", [])
            for m in matches[:10]:
                match_id = m["id"]
                if match_id in sent:
                    continue
                match_time = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                minutes_left = (match_time - datetime.now(timezone.utc)).total_seconds() / 60

                if 0 < minutes_left <= 30:
                    home, away = esc(m["homeTeam"]["name"]), esc(m["awayTeam"]["name"])
                    text = (
                        box("⏰ تذكير بمباراة قريبة") +
                        f"🏆 البطولة: {esc(name)}\n"
                        f"⚽ {home}  ضد  {away}\n"
                        f"⏳ تبدأ بعد {int(minutes_left)} دقيقة"
                    )
                    for chat_id in subs:
                        try:
                            await context.bot.send_message(chat_id, text, parse_mode="HTML")
                        except Exception:
                            pass
                    sent.append(match_id)
            save_json(SENT_REMINDERS_FILE, sent)
        except Exception:
            continue

# ===================== تشغيل =====================

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_buttons))

if app.job_queue is not None:
    app.job_queue.run_repeating(check_reminders, interval=300, first=10)
    print("✅ نظام التذكيرات مفعّل")
else:
    print("⚠️ تحذير: job_queue غير متاح! ثبّت مكتبة APScheduler ثم أعد التشغيل")

app.run_polling()