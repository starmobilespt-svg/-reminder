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

if not TOKEN:
    print("❌ ERROR: BOT_TOKEN မတွေ့ပါ။ Render Dashboard > Environment ထဲမှာ BOT_TOKEN ကို သေချာထည့်ပေးပါ။")
    exit(1) # Token မရှိရင် Bot ကို ရပ်လိုက်ပါမယ်

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- Database ---
DB_FILE = "tasks.db"

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Database Table တည်ဆောက်ခြင်း
conn = get_db()
conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, chat_id INTEGER, task_name TEXT, frequency TEXT, time TEXT)')
conn.commit()
conn.close()

# --- Flask (Keep-Alive) ---
@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- Scheduler ---
def check_tasks():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz).strftime("%H:%M")
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (now,)).fetchall()
    conn.close()
    for t in tasks:
        bot.send_message(t['chat_id'], f"⏰ Reminder: {t['task_name']} ({t['frequency']})")

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_tasks, 'cron', minute='*')
scheduler.start()

# --- Bot UI ---
def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Task", "📋 View Tasks")
    kb.add("🗑 Delete Task", "📥 Backup DB", "📤 Restore DB")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "👋 မင်္ဂလာပါ! Reminder Bot အသင့်ဖြစ်ပါပြီ။", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "➕ Add Task")
def add_task(m):
    msg = bot.send_message(m.chat.id, "အလုပ်အမည် ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, lambda m2: save_task(m2, m.chat.id))

def save_task(m, chat_id):
    task_name = m.text
    # ရိုးရှင်းအောင် အချိန်ကို တစ်ခါတည်း တောင်းလိုက်ပါမယ် (သင်စိတ်ကြိုက်ပြင်နိုင်ပါတယ်)
    msg = bot.send_message(m.chat.id, "အချိန်ကို (08:30) ပုံစံမျိုး ရိုက်ထည့်ပါ။")
    bot.register_next_step_handler(msg, lambda m2: finalize_task(m2, chat_id, task_name))

def finalize_task(m, chat_id, name):
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time) VALUES (?, ?, ?, ?)', (chat_id, name, "Daily", m.text))
    conn.commit()
    conn.close()
    bot.send_message(chat_id, "✅ သိမ်းဆည်းပြီးပါပြီ။", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "📋 View Tasks")
def view_tasks(m):
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (m.chat.id,)).fetchall()
    conn.close()
    if not tasks: bot.send_message(m.chat.id, "ဘာမှ မရှိသေးပါ။")
    else: bot.send_message(m.chat.id, "\n".join([f"{t['task_name']} - {t['time']}" for t in tasks]))

# --- Run ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
