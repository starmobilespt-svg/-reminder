import telebot
import os
import sqlite3
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz

# --- 1. CONFIGURATION ---
# Token ကို code ထဲမှာ မရေးပါနဲ့
TOKEN = os.environ.get('8800884469:AAFraD3vphlEw-umzb6qpDpqjempWIofPu4')

if not TOKEN:
    print("❌ ERROR: BOT_TOKEN ကို Render Dashboard > Environment ထဲမှာ ထည့်ဖို့ မေ့နေပါတယ်။")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- 2. DATABASE ---
DB_FILE = "tasks.db"
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Table တည်ဆောက်ခြင်း
conn = get_db()
conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, chat_id INTEGER, task_name TEXT, frequency TEXT, time TEXT, task_date TEXT)')
conn.commit()
conn.close()

# --- 3. FLASK & SCHEDULER ---
@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# Reminder Logic
def check_tasks():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz)
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")
    
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (current_time,)).fetchall()
    
    for t in tasks:
        # နေ့စဉ်ဆိုရင် အမြဲပို့၊ တစ်ကြိမ်သာဆိုရင် ရက်စစ်ပြီးမှပို့
        if t['frequency'] == 'daily' or (t['frequency'] == 'once' and t['task_date'] == current_date):
            bot.send_message(t['chat_id'], f"🚨⏰ **ALARM!** ⏰🚨\n\n📌 {t['task_name']}")
    
    # တစ်ကြိမ်သာ အလုပ်များကို ဖျက်ခြင်း
    conn.execute('DELETE FROM tasks WHERE frequency = "once" AND task_date = ?', (current_date,))
    conn.commit()
    conn.close()

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_tasks, 'cron', minute='*')
scheduler.start()

# --- 4. BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "👋 Bot အသင့်ဖြစ်ပါပြီ။")

@bot.message_handler(func=lambda m: True)
def echo(m):
    # ဒီနေရာမှာ Button တွေကို ဆက်လက်ထည့်သွင်းပါ (ယခင် Code အတိုင်း)
    bot.send_message(m.chat.id, "အလုပ်လုပ်နေပါတယ်။")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
