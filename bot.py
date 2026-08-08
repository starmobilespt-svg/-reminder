import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz
import os

# ----------------- Configurations -----------------
# Token ကို Code ထဲမှာ မထည့်ပါနဲ့။ Render Environment Variable မှာသာ ထည့်ပါ။
BOT_TOKEN = os.environ.get('8800884469:AAFraD3vphlEw-umzb6qpDpqjempWIofPu4')
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ----------------- Database Setup (SQLite) -----------------
DB_FILE = "tasks.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS tasks
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     chat_id INTEGER,
                     task_name TEXT,
                     frequency TEXT,
                     time TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ----------------- State Management -----------------
user_steps = {}

# ----------------- Flask Web Server (For Render Keep-Alive) -----------------
@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ----------------- Scheduler -----------------
def check_reminders():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz)
    current_time = now.strftime("%H:%M")
    
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (current_time,)).fetchall()
    conn.close()

    for task in tasks:
        bot.send_message(
            task['chat_id'], 
            f"⏰ **Reminder Alert!**\n\n📌 **Task:** {task['task_name']}\n🔁 **Type:** {task['frequency'].capitalize()}",
            parse_mode="Markdown"
        )

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_reminders, 'cron', minute='*')
scheduler.start()

# ----------------- Buttons Setup -----------------
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("➕ Add Task"), KeyboardButton("📋 View Tasks"))
    markup.add(KeyboardButton("🗑 Delete Task"), KeyboardButton("📥 Backup DB"), KeyboardButton("📤 Restore DB"))
    return markup

# ----------------- Bot Handlers -----------------

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id, 
        "👋 မင်္ဂလာပါ! Reminder Bot အသင့်ဖြစ်ပါပြီ။", 
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add Task")
def handle_add_task(message):
    msg = bot.send_message(message.chat.id, "✍️ အလုပ် (Task) အမည်ကို ရိုက်ထည့်ပါ-")
    bot.register_next_step_handler(msg, process_task_name)

@bot.message_handler(func=lambda message: message.text == "📋 View Tasks")
def handle_view_tasks(message):
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (message.chat.id,)).fetchall()
    conn.close()
    if not tasks:
        bot.send_message(message.chat.id, "🤷‍♂️ မှတ်ထားသော Task များ မရှိသေးပါ။")
        return
    reply = "📋 **သင့်၏ Tasks များ:**\n\n"
    for idx, t in enumerate(tasks, 1):
        reply += f"{idx}. {t['task_name']} ({t['frequency']}) - ⏰ {t['time']}\n"
    bot.send_message(message.chat.id, reply, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🗑 Delete Task")
def handle_delete_task(message):
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (message.chat.id,)).fetchall()
    conn.close()
    if not tasks:
        bot.send_message(message.chat.id, "🤷‍♂️ ဖျက်ရန် Task များ မရှိသေးပါ။")
        return
    markup = InlineKeyboardMarkup()
    for t in tasks:
        markup.add(InlineKeyboardButton(f"❌ {t['task_name']}", callback_data=f"del_{t['id']}"))
    bot.send_message(message.chat.id, "ဖျက်လိုသော Task ကို ရွေးချယ်ပါ-", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📥 Backup DB")
def handle_backup(message):
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as file:
            bot.send_document(message.chat.id, file, caption="📦 Database Backup ဖိုင်ပါ။")
    else:
        bot.send_message(message.chat.id, "❌ Database ဖိုင် မရှိသေးပါ။")

@bot.message_handler(func=lambda message: message.text == "📤 Restore DB")
def handle_restore(message):
    msg = bot.send_message(message.chat.id, "📤 Restore လုပ်ရန် **tasks.db** ဖိုင်ကို ပေးပို့ပါ။")
    bot.register_next_step_handler(msg, process_restore)

# Process Steps
def process_task_name(message):
    user_steps[message.chat.id] = {'task_name': message.text}
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("နေ့စဉ် (Daily)", callback_data="freq_daily"),
               InlineKeyboardButton("အပတ်စဉ် (Weekly)", callback_data="freq_weekly"),
               InlineKeyboardButton("လစဉ် (Monthly)", callback_data="freq_monthly"),
               InlineKeyboardButton("နှစ်စဉ် (Yearly)", callback_data="freq_yearly"))
    bot.send_message(message.chat.id, "ဘယ်လိုပုံစံ သတိပေးရမလဲ-", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freq_"))
def process_frequency(call):
    user_steps[call.message.chat.id]['frequency'] = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "⏰ အချိန်ကို (ဥပမာ 08:30) ဖြင့် ရိုက်ထည့်ပါ။")
    bot.register_next_step_handler(msg, process_time)

def process_time(message):
    time_str = message.text
    try:
        datetime.datetime.strptime(time_str, '%H:%M')
    except:
        bot.send_message(message.chat.id, "❌ အချိန်ပုံစံမှားနေသည်။ (08:30) ပုံစံမျိုး ရိုက်ပေးပါ။")
        return
    conn = get_db_connection()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time) VALUES (?, ?, ?, ?)',
                 (message.chat.id, user_steps[message.chat.id]['task_name'], user_steps[message.chat.id]['frequency'], time_str))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ အောင်မြင်စွာ မှတ်သားလိုက်ပါပြီ!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def delete_callback(call):
    conn = get_db_connection()
    conn.execute('DELETE FROM tasks WHERE id = ?', (call.data.split("_")[1],))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "ဖျက်ပြီးပါပြီ။")
    bot.send_message(call.message.chat.id, "✅ ဖျက်လိုက်ပါပြီ။")

def process_restore(message):
    if message.document:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(DB_FILE, 'wb') as new_file: new_file.write(downloaded_file)
        bot.send_message(message.chat.id, "✅ Restore လုပ်ပြီးပါပြီ။")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
