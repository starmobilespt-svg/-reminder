import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz
import os

TOKEN = "8800884469:AAFraD3vphlEw-umzb6qpDpqjempWIofPu4"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

DB_FILE = "tasks.db"

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

conn = get_db()
conn.execute('''CREATE TABLE IF NOT EXISTS tasks 
                (id INTEGER PRIMARY KEY, chat_id INTEGER, task_name TEXT, 
                 frequency TEXT, time TEXT, task_date TEXT)''')
conn.commit()
conn.close()

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- Reminder Logic ---
def check_tasks():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz)
    current_time = now.strftime("%H:%M")
    today_date = now.strftime("%Y-%m-%d")
    today_day = now.strftime("%d")       # လစဉ်အတွက်
    today_month_day = now.strftime("%m-%d") # နှစ်စဉ်အတွက်
    
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (current_time,)).fetchall()
    
    for t in tasks:
        should_alert = False
        if t['frequency'] == 'daily': should_alert = True
        elif t['frequency'] == 'once' and t['task_date'] == today_date: should_alert = True
        elif t['frequency'] == 'monthly' and t['task_date'] == today_day: should_alert = True
        elif t['frequency'] == 'yearly' and t['task_date'] == today_month_day: should_alert = True
        
        if should_alert:
            bot.send_message(t['chat_id'], f"🚨⏰ **ALARM!** ⏰🚨\n\n📌 **Task:** {t['task_name']}\n📅 **Type:** {t['frequency'].upper()}")
            # တစ်ကြိမ်သာဆိုရင် ဖျက်မယ်
            if t['frequency'] == 'once':
                conn.execute('DELETE FROM tasks WHERE id = ?', (t['id'],))
    conn.commit()
    conn.close()

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_tasks, 'cron', minute='*')
scheduler.start()

# --- UI ---
def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Task", "📋 View Tasks")
    kb.add("🗑 Delete Task", "📥 Backup DB", "📤 Restore DB")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "👋 Reminder Bot အသင့်ဖြစ်ပါပြီ။", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "➕ Add Task")
def add_task(m):
    msg = bot.send_message(m.chat.id, "အလုပ်အမည် ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, lambda m2: ask_frequency(m2, m2.text))

def ask_frequency(m, name):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("နေ့စဉ် (Daily)", callback_data=f"freq|daily|{name}"),
           InlineKeyboardButton("တစ်ကြိမ် (Once)", callback_data=f"freq|once|{name}"))
    kb.add(InlineKeyboardButton("လစဉ် (Monthly)", callback_data=f"freq|monthly|{name}"),
           InlineKeyboardButton("နှစ်စဉ် (Yearly)", callback_data=f"freq|yearly|{name}"))
    bot.send_message(m.chat.id, "ဘယ်လိုပုံစံလဲ ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freq|"))
def handle_freq(call):
    _, freq, name = call.data.split("|")
    # အချိန်မတောင်းခင် နေ့စွဲရွေးခိုင်းမယ်
    if freq == 'monthly':
        msg = bot.send_message(call.message.chat.id, "လတိုင်းရဲ့ ဘယ်နေ့မှာ သတိပေးရမလဲ? (၁ မှ ၃၁ ထိ ထည့်ပေးပါ)")
        bot.register_next_step_handler(msg, lambda m: ask_time(m, freq, name, m.text))
    elif freq == 'yearly':
        msg = bot.send_message(call.message.chat.id, "နှစ်တိုင်းရဲ့ ဘယ်နေ့မှာ သတိပေးရမလဲ? (လ-ရက် ပုံစံ - ဥပမာ 08-09)")
        bot.register_next_step_handler(msg, lambda m: ask_time(m, freq, name, m.text))
    else:
        ask_time(call.message, freq, name, None)

def ask_time(m, freq, name, date_val):
    msg = bot.send_message(m.chat.id, "အချိန်ကို (08:30) ပုံစံမျိုး ရိုက်ပေးပါ:")
    bot.register_next_step_handler(msg, lambda m2: save_task(m2, freq, name, date_val))

def save_task(m, freq, name, date_val):
    time = m.text
    # Once ဆိုရင် ဒီနေ့ရက်စွဲကို ယူမယ်
    date = datetime.datetime.now().strftime("%Y-%m-%d") if freq == 'once' else date_val
    
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, time, date))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ သိမ်းဆည်းပြီးပါပြီ ({freq})။", reply_markup=main_kb())

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
