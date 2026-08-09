import telebot
import os
import sqlite3
import threading
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz

TOKEN = "8800884469:AAFraD3vphlEw-umzb6qpDpqjempWIofPu4"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
DB_FILE = "tasks.db"

# --- Database & Setup ---
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

conn = get_db()
conn.execute('''CREATE TABLE IF NOT EXISTS tasks 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, task_name TEXT, 
                 frequency TEXT, time TEXT, task_date TEXT)''')
conn.commit()
conn.close()

# --- Flask & Scheduler ---
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def check_tasks():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz)
    current_time = now.strftime("%H:%M")
    today_date = now.strftime("%Y-%m-%d")
    today_day = now.strftime("%d")
    today_month_day = now.strftime("%m-%d")
    
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (current_time,)).fetchall()
    for t in tasks:
        alert = False
        if t['frequency'] == 'daily': alert = True
        elif t['frequency'] == 'once' and t['task_date'] == today_date: alert = True
        elif t['frequency'] == 'monthly' and t['task_date'] == today_day: alert = True
        elif t['frequency'] == 'yearly' and t['task_date'] == today_month_day: alert = True
        
        if alert:
            bot.send_message(t['chat_id'], f"🚨⏰ **ALARM!** ⏰🚨\n\n📌 {t['task_name']}")
            if t['frequency'] == 'once': conn.execute('DELETE FROM tasks WHERE id = ?', (t['id'],))
    conn.commit()
    conn.close()

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_tasks, 'cron', minute='*')
scheduler.start()

# --- UI & Handlers ---
def main_kb():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Task", "📋 View Tasks")
    kb.add("🗑 Delete Task", "📥 Backup DB", "📤 Restore DB")
    return kb

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id, "👋 Reminder Bot အသင့်ဖြစ်ပါပြီ။", reply_markup=main_kb())

# Add Task Logic
@bot.message_handler(func=lambda m: m.text == "➕ Add Task")
def add_task(m):
    msg = bot.send_message(m.chat.id, "အလုပ်အမည် ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, lambda m2: ask_frequency(m2, m2.text))

def ask_frequency(m, name):
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("နေ့စဉ်", callback_data=f"freq|daily|{name}"),
           telebot.types.InlineKeyboardButton("တစ်ကြိမ်", callback_data=f"freq|once|{name}"))
    kb.add(telebot.types.InlineKeyboardButton("လစဉ်", callback_data=f"freq|monthly|{name}"),
           telebot.types.InlineKeyboardButton("နှစ်စဉ်", callback_data=f"freq|yearly|{name}"))
    bot.send_message(m.chat.id, "ဘယ်လိုပုံစံလဲ ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freq|"))
def handle_freq(call):
    _, freq, name = call.data.split("|")
    if freq == 'monthly':
        msg = bot.send_message(call.message.chat.id, "လတိုင်းရဲ့ ဘယ်ရက်မှာလဲ? (01-31):")
        bot.register_next_step_handler(msg, lambda m: ask_time(m, freq, name, m.text))
    elif freq == 'yearly':
        msg = bot.send_message(call.message.chat.id, "နှစ်တိုင်းရဲ့ ဘယ်နေ့လဲ? (လ-ရက်, ဥပမာ 08-09):")
        bot.register_next_step_handler(msg, lambda m: ask_time(m, freq, name, m.text))
    else:
        ask_time(call.message, freq, name, None)

def ask_time(m, freq, name, date_val):
    msg = bot.send_message(m.chat.id, "အချိန်ကို (08:30) ပုံစံမျိုး ရိုက်ပေးပါ:")
    bot.register_next_step_handler(msg, lambda m2: save_task(m2, freq, name, date_val))

def save_task(m, freq, name, date_val):
    date = datetime.datetime.now().strftime("%Y-%m-%d") if freq == 'once' else date_val
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, m.text, date))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "✅ သိမ်းဆည်းပြီးပါပြီ။", reply_markup=main_kb())

# View Tasks
@bot.message_handler(func=lambda m: m.text == "📋 View Tasks")
def view_tasks(m):
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (m.chat.id,)).fetchall()
    conn.close()
    if not tasks: bot.send_message(m.chat.id, "ဘာမှ မရှိသေးပါ။")
    else:
        text = "\n".join([f"📌 {t['task_name']} ({t['frequency']}) - ⏰ {t['time']}" for t in tasks])
        bot.send_message(m.chat.id, f"📋 သင့်ရဲ့ Task များ:\n{text}")

# Delete Tasks
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Task")
def del_task(m):
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (m.chat.id,)).fetchall()
    conn.close()
    if not tasks: bot.send_message(m.chat.id, "ဖျက်စရာ မရှိပါ။")
    else:
        kb = telebot.types.InlineKeyboardMarkup()
        for t in tasks: kb.add(telebot.types.InlineKeyboardButton(f"❌ {t['task_name']}", callback_data=f"del|{t['id']}"))
        bot.send_message(m.chat.id, "ဖျက်မယ့်တစ်ခုကို ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del|"))
def handle_del(call):
    task_id = call.data.split("|")[1]
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "ဖျက်ပြီးပါပြီ။")
    bot.send_message(call.message.chat.id, "✅ ဖျက်လိုက်ပါပြီ။")

# Backup/Restore
@bot.message_handler(func=lambda m: m.text == "📥 Backup DB")
def backup(m):
    with open(DB_FILE, "rb") as f: bot.send_document(m.chat.id, f)

@bot.message_handler(func=lambda m: m.text == "📤 Restore DB")
def restore(m):
    msg = bot.send_message(m.chat.id, "tasks.db ဖိုင်ကို ပို့ပေးပါ:")
    bot.register_next_step_handler(msg, lambda m2: process_restore(m2))

def process_restore(m):
    if m.document:
        f_id = m.document.file_id
        path = bot.get_file(f_id).file_path
        with open(DB_FILE, 'wb') as f: f.write(bot.download_file(path))
        bot.send_message(m.chat.id, "✅ Restore လုပ်ပြီးပါပြီ။")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
