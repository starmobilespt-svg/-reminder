import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz
import os

# --- Configuration ---
# Render Environment Variable ထဲက BOT_TOKEN ကို ခေါ်ယူခြင်း
TOKEN = os.environ.get('8800884469:AAFraD3vphlEw-umzb6qpDpqjempWIofPu4')

# Error မတက်အောင် Token စစ်ဆေးခြင်း
if not TOKEN:
    print("❌ ERROR: BOT_TOKEN မတွေ့ပါ။ Render Dashboard > Environment ထဲမှာ BOT_TOKEN ကို သေချာထည့်ပေးပါ။")
    # အကယ်၍ Token မရှိရင် Bot ကို ရပ်လိုက်ပါမယ်
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- Database Setup ---
DB_FILE = "tasks.db"

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Database Table (Date field ထပ်ထည့်ထားပါတယ်)
conn = get_db()
conn.execute('''CREATE TABLE IF NOT EXISTS tasks 
                (id INTEGER PRIMARY KEY, chat_id INTEGER, task_name TEXT, 
                 frequency TEXT, time TEXT, task_date TEXT)''')
conn.commit()
conn.close()

# --- Flask (Keep-Alive) ---
@app.route('/')
def home():
    return "Bot is awake!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- Reminder Logic ---
def check_tasks():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz)
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")
    
    conn = get_db()
    # နေ့စဉ် အလုပ်များ
    daily_tasks = conn.execute('SELECT * FROM tasks WHERE frequency = "daily" AND time = ?', (current_time,)).fetchall()
    # တစ်ကြိမ်သာ အလုပ်များ
    once_tasks = conn.execute('SELECT * FROM tasks WHERE frequency = "once" AND time = ? AND task_date = ?', (current_time, current_date)).fetchall()
    
    # သတိပေးခြင်း
    for t in daily_tasks + once_tasks:
        bot.send_message(t['chat_id'], f"🚨⏰ **ALARM! ALARM!** ⏰🚨\n\n📌 **Task:** {t['task_name']}\n📅 **Type:** {t['frequency'].upper()}")
    
    # တစ်ကြိမ်သာ အလုပ်များကို ဖျက်ခြင်း
    conn.execute('DELETE FROM tasks WHERE frequency = "once" AND time = ? AND task_date = ?', (current_time, current_date))
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
    msg = bot.send_message(m.chat.id, "Task အမည်ကို ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, lambda m2: ask_frequency(m2, m2.text))

def ask_frequency(m, task_name):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("နေ့စဉ် (Daily)", callback_data=f"freq|daily|{task_name}"))
    kb.add(InlineKeyboardButton("တစ်ကြိမ်သာ (One-time)", callback_data=f"freq|once|{task_name}"))
    bot.send_message(m.chat.id, "ဘယ်လိုပုံစံလဲ ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freq|"))
def handle_freq(call):
    _, freq, name = call.data.split("|")
    msg = bot.send_message(call.message.chat.id, "အချိန်ကို (08:30) ပုံစံမျိုး ရိုက်ပေးပါ:")
    bot.register_next_step_handler(msg, lambda m: save_task(m, freq, name))

def save_task(m, freq, name):
    time = m.text
    date = datetime.datetime.now().strftime("%Y-%m-%d") if freq == 'once' else None
    
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, time, date))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ သိမ်းဆည်းပြီးပါပြီ ({freq})။")

# [View/Delete/Backup/Restore ဟန်ဒလာများကို ယခင်ကအတိုင်းထားပါ]

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
