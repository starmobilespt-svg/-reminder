import telebot
import os
import sqlite3
import threading
import re
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz

TOKEN = "8800884469:AAH3KgR1vVAjlkwHq81civRvt9xSgvYS5Vg"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
DB_FILE = "tasks.db"
user_steps = {}
MYT = pytz.timezone('Asia/Yangon')

# --- Helper Functions (Smart Parsers) ---
def parse_smart_time(t_str):
    """ '8 30 am', '8:30', '20:00' စတာတွေကို 'HH:MM' အဖြစ်ပြောင်းပေးတယ် """
    t_str = t_str.lower().replace('.', ':').replace(' ', ':')
    match = re.search(r'(\d{1,2})[:]?(\d{0,2})?\s?(am|pm)?', t_str)
    if not match: return None
    h, m, period = match.groups()
    h = int(h)
    m = int(m) if m else 0
    if period == 'pm' and h < 12: h += 12
    if period == 'am' and h == 12: h = 0
    return f"{h:02d}:{m:02d}"

# --- Database Setup ---
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- Flask & Scheduler ---
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# (check_tasks, start, handlers အပိုင်းများကို ယခင်အတိုင်း ထားပါ)
# အရေးကြီးတဲ့ save_task ကို အောက်ပါအတိုင်း ပြင်ထားပါတယ်

def save_task(m, freq, name, date_val):
    # Smart Parse
    clean_time = parse_smart_time(m.text)
    if not clean_time:
        bot.send_message(m.chat.id, "❌ အချိန်ပုံစံ မမှန်ပါ။ (ဥပမာ: 8:30 am သို့မဟုတ် 20:00)")
        return
        
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, clean_time, date_val))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ သိမ်းဆည်းပြီးပါပြီ!\n📌 {name}\n🔁 {freq}\n⏰ {clean_time}")

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start(m):
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Task", "📋 View Tasks")
    kb.add("🗑 Delete Task", "📥 Backup DB", "📤 Restore DB")
    bot.send_message(m.chat.id, "👋 Reminder Bot အသင့်ဖြစ်ပါပြီ။", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "➕ Add Task")
def add_task(m):
    msg = bot.send_message(m.chat.id, "အလုပ်အမည် ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, lambda m2: ask_freq(m2, m2.text))

def ask_freq(m, name):
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("နေ့စဉ်", callback_data=f"freq|daily|{name}"),
           telebot.types.InlineKeyboardButton("တစ်ကြိမ်", callback_data=f"freq|once|{name}"))
    kb.add(telebot.types.InlineKeyboardButton("လစဉ်", callback_data=f"freq|monthly|{name}"),
           telebot.types.InlineKeyboardButton("နှစ်စဉ်", callback_data=f"freq|yearly|{name}"))
    bot.send_message(m.chat.id, "ဘယ်လိုပုံစံလဲ ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freq|"))
def handle_freq(call):
    _, freq, name = call.data.split("|")
    user_steps[call.message.chat.id] = {'freq': freq, 'name': name}
    if freq == 'monthly': bot.send_message(call.message.chat.id, "လစဉ် ဘယ်ရက်မှာလဲ? (ဥပမာ: 5 သို့မဟုတ် 05):")
    elif freq == 'yearly': bot.send_message(call.message.chat.id, "နှစ်စဉ် ဘယ်နေ့လဲ? (ဥပမာ: Aug 9 သို့မဟုတ် 08-09):")
    else: bot.send_message(call.message.chat.id, "အချိန်ကို ရိုက်ပေးပါ (ဥပမာ: 8:30am သို့မဟုတ် 20:30):")
    bot.register_next_step_handler(call.message, handle_time)

def handle_time(m):
    uid = m.chat.id
    freq, name = user_steps[uid]['freq'], user_steps[uid]['name']
    
    # ရက်စွဲကိုလည်း အဆင်ပြေသလို ရိုက်လို့ရအောင် (လိုအပ်ရင် ဒီမှာ ထပ်ဖြည့်နိုင်ပါတယ်)
    date_val = m.text if freq in ['monthly', 'yearly'] else None
    
    if freq in ['monthly', 'yearly']:
        msg = bot.send_message(m.chat.id, "အချိန်ကို ရိုက်ပေးပါ (ဥပမာ: 8:30 am):")
        bot.register_next_step_handler(msg, lambda m2: save_task(m2, freq, name, date_val))
    else:
        save_task(m, freq, name, datetime.datetime.now(MYT).strftime("%Y-%m-%d"))

# (ကျန်တဲ့ view, delete, callback handlers များကို ယခင်ကအတိုင်းထားပါ)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
