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
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
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
    return "Bot is awake and running with Bottom Buttons!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ----------------- Scheduler (အချိန်ကိုက် သတိပေးစနစ်) -----------------
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

# ----------------- Bottom Buttons (Reply Keyboard) Setup -----------------
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_add = KeyboardButton("➕ Add Task")
    btn_view = KeyboardButton("📋 View Tasks")
    btn_delete = KeyboardButton("🗑 Delete Task")
    btn_backup = KeyboardButton("📥 Backup DB")
    btn_restore = KeyboardButton("📤 Restore DB")
    markup.add(btn_add, btn_view, btn_delete, btn_backup, btn_restore)
    return markup

# ----------------- Bot Handlers -----------------

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id, 
        "👋 မင်္ဂလာပါ! Bottom Buttons သုံး Reminder Bot ပါ။\n\nအောက်ပါခလုတ်များကို နှိပ်၍ အသုံးပြုနိုင်ပါသည်။", 
        reply_markup=get_main_keyboard()
    )

# Bottom Button များကို နှိပ်လိုက်သည့်အခါ အလုပ်လုပ်ပုံများ
@bot.message_handler(func=lambda message: message.text == "➕ Add Task")
def handle_add_task(message):
    msg = bot.send_message(message.chat.id, "✍️ မှတ်သားလိုသော အလုပ် (Task) အမည်ကို ရိုက်ထည့်ပါ-", reply_markup=get_main_keyboard())
    bot.register_next_step_handler(msg, process_task_name)

@bot.message_handler(func=lambda message: message.text == "📋 View Tasks")
def handle_view_tasks(message):
    chat_id = message.chat.id
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (chat_id,)).fetchall()
    conn.close()
    
    if not tasks:
        bot.send_message(chat_id, "🤷‍♂️ မှတ်ထားသော Task များ မရှိသေးပါ။", reply_markup=get_main_keyboard())
        return
    
    reply = "📋 **သင့်၏ Tasks များ:**\n\n"
    for idx, t in enumerate(tasks, 1):
        reply += f"{idx}. {t['task_name']} ({t['frequency']}) - ⏰ {t['time']}\n"
    bot.send_message(chat_id, reply, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "🗑 Delete Task")
def handle_delete_task(message):
    chat_id = message.chat.id
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (chat_id,)).fetchall()
    conn.close()
    
    if not tasks:
        bot.send_message(chat_id, "🤷‍♂️ ဖျက်ရန် Task များ မရှိသေးပါ။", reply_markup=get_main_keyboard())
        return
        
    markup = InlineKeyboardMarkup(row_width=1)
    for t in tasks:
        markup.add(InlineKeyboardButton(f"❌ {t['task_name']}", callback_data=f"del_{t['id']}"))
    bot.send_message(chat_id, "ဖျက်လိုသော Task ကို ရွေးချယ်ပါ-", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📥 Backup DB")
def handle_backup(message):
    chat_id = message.chat.id
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as file:
            bot.send_document(chat_id, file, caption="📦 သင့်ရဲ့ Local Database (.db) ဖိုင်ပါ။", reply_markup=get_main_keyboard())
    else:
        bot.send_message(chat_id, "❌ Database ဖိုင် မရှိသေးပါ။", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📤 Restore DB")
def handle_restore(message):
    msg = bot.send_message(message.chat.id, "📤 Restore လုပ်ရန် သင့်ထံတွင် သိမ်းဆည်းထားသော **tasks.db** ဖိုင်ကို ဤနေရာသို့ ပေးပို့ပါ။", reply_markup=get_main_keyboard())
    bot.register_next_step_handler(msg, process_restore)

# Task အမည် တောင်းခြင်း
def process_task_name(message):
    chat_id = message.chat.id
    user_steps[chat_id] = {'task_name': message.text}
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("နေ့စဉ် (Daily)", callback_data="freq_daily"),
        InlineKeyboardButton("အပတ်စဉ် (Weekly)", callback_data="freq_weekly"),
        InlineKeyboardButton("လစဉ် (Monthly)", callback_data="freq_monthly"),
        InlineKeyboardButton("နှစ်စဉ် (Yearly)", callback_data="freq_yearly")
    )
    bot.send_message(chat_id, "ဘယ်လိုပုံစံ သတိပေးရမလဲ ရွေးချယ်ပါ-", reply_markup=markup)

# အချိန် (Frequency) ရွေးချယ်ခြင်း
@bot.callback_query_handler(func=lambda call: call.data.startswith("freq_"))
def process_frequency(call):
    chat_id = call.message.chat.id
    freq = call.data.split("_")[1]
    
    if chat_id in user_steps:
        user_steps[chat_id]['frequency'] = freq
        msg = bot.send_message(chat_id, "⏰ သတိပေးရမည့်အချိန်ကို (24 နာရီပုံစံ) ဖြင့် ရိုက်ထည့်ပါ။\n(ဥပမာ - 08:30, 14:00, 20:15)")
        bot.register_next_step_handler(msg, process_time)

# အချိန် သတ်မှတ်ပြီး Database သို့ သိမ်းခြင်း
def process_time(message):
    chat_id = message.chat.id
    time_str = message.text
    
    try:
        datetime.datetime.strptime(time_str, '%H:%M')
    except ValueError:
        msg = bot.send_message(chat_id, "❌ အချိန်ပုံစံမှားယွင်းနေပါသည်။ (ဥပမာ - 14:30) ဟု ပြန်ရိုက်ပါ။")
        bot.register_next_step_handler(msg, process_time)
        return

    if chat_id in user_steps:
        conn = get_db_connection()
        conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time) VALUES (?, ?, ?, ?)',
                     (chat_id, user_steps[chat_id]['task_name'], user_steps[chat_id]['frequency'], time_str))
        conn.commit()
        conn.close()
        
        task_name = user_steps[chat_id]['task_name']
        del user_steps[chat_id]
        bot.send_message(chat_id, f"✅ အောင်မြင်စွာ မှတ်သားလိုက်ပါပြီ!\n\n📌 {task_name}\n⏰ နေ့စဉ် {time_str} အချိန်တွင် သတိပေးပါမည်။", reply_markup=get_main_keyboard())

# Task ဖျက်ခြင်း (Inline Button ဖြင့်)
@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def process_delete_callback(call):
    chat_id = call.message.chat.id
    task_id = call.data.split("_")[1]
    conn = get_db_connection()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    bot.send_message(chat_id, "✅ Task ကို အောင်မြင်စွာ ဖျက်လိုက်ပါပြီ။", reply_markup=get_main_keyboard())

# Restore ပြုလုပ်ခြင်း
def process_restore(message):
    chat_id = message.chat.id
    if message.document:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            with open(DB_FILE, 'wb') as new_file:
                new_file.write(downloaded_file)
                
            bot.send_message(chat_id, "✅ Database ကို အောင်မြင်စွာ Restore လုပ်ပြီးပါပြီ။", reply_markup=get_main_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ Restore လုပ်ရာတွင် အမှားအယွင်းဖြစ်ပေါ်ခဲ့ပါသည်။\nError: {e}", reply_markup=get_main_keyboard())
    else:
        bot.send_message(chat_id, "❌ မှန်ကန်သော Database Document ဖိုင် မဟုတ်ပါ။", reply_markup=get_main_keyboard())

# ----------------- Start Application -----------------
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    print("Bot is running with Bottom Buttons and SQLite...")
    bot.infinity_polling()
