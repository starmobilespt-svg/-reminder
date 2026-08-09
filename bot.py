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
user_steps = {}

# --- Timezone Utility ---
MYT = pytz.timezone('Asia/Yangon')

# --- Database Setup ---
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS tasks 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, task_name TEXT, 
                     frequency TEXT, time TEXT, task_date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Flask Keep-Alive ---
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- Scheduler ---
def check_tasks():
    now = datetime.datetime.now(MYT) # မြန်မာစံတော်ချိန်ကို သုံးခြင်း
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
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("✅ Done / Dismiss", callback_data=f"done|{t['id']}|{t['frequency']}"))
            bot.send_message(t['chat_id'], f"🚨⏰ **ALARM!** ⏰🚨\n\n📌 **Task:** {t['task_name']}", reply_markup=kb)
    conn.close()

scheduler = BackgroundScheduler(timezone=MYT)
scheduler.add_job(check_tasks, 'cron', minute='*')
scheduler.start()

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start(m):
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Task", "📋 View Tasks")
    kb.add("🗑 Delete Task", "📥 Backup DB", "📤 Restore DB")
    bot.send_message(m.chat.id, "👋 Reminder Bot အသင့်ဖြစ်ပါပြီ။", reply_markup=kb)

@bot.message_handler(commands=['time'])
def show_time(m):
    now = datetime.datetime.now(MYT)
    bot.reply_to(m, f"⏰ လက်ရှိမြန်မာစံတော်ချိန်: {now.strftime('%Y-%m-%d %H:%M:%S')}")

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
    if freq == 'monthly': bot.send_message(call.message.chat.id, "လစဉ် ဘယ်ရက်မှာလဲ? (01-31):")
    elif freq == 'yearly': bot.send_message(call.message.chat.id, "နှစ်တိုင်း ဘယ်နေ့လဲ? (လ-ရက်, ဥပမာ 08-09):")
    else: bot.send_message(call.message.chat.id, "အချိန်ကို (08:30) ပုံစံမျိုး ရိုက်ပေးပါ:")
    bot.register_next_step_handler(call.message, handle_time)

def handle_time(m):
    uid = m.chat.id
    freq, name = user_steps[uid]['freq'], user_steps[uid]['name']
    if freq in ['monthly', 'yearly']:
        date_val = m.text
        msg = bot.send_message(m.chat.id, "အချိန်ကို (08:30) ပုံစံမျိုး ရိုက်ပေးပါ:")
        bot.register_next_step_handler(msg, lambda m2: save_task(m2, freq, name, date_val))
    else: save_task(m, freq, name, datetime.datetime.now(MYT).strftime("%Y-%m-%d") if freq == 'once' else None)

def save_task(m, freq, name, date_val):
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, m.text, date_val))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ သိမ်းဆည်းပြီးပါပြီ!\n\n📌 {name}\n🔁 {freq}\n⏰ {m.text}")

@bot.message_handler(func=lambda m: m.text == "📋 View Tasks")
def view(m):
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (m.chat.id,)).fetchall()
    conn.close()
    if not tasks: bot.send_message(m.chat.id, "ဘာမှ မရှိပါ။")
    else: bot.send_message(m.chat.id, "\n".join([f"📌 {t['task_name']} ({t['frequency']}) - ⏰ {t['time']}" for t in tasks]))

@bot.message_handler(func=lambda m: m.text == "🗑 Delete Task")
def del_task(m):
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (m.chat.id,)).fetchall()
    conn.close()
    kb = telebot.types.InlineKeyboardMarkup()
    for t in tasks: kb.add(telebot.types.InlineKeyboardButton(f"❌ {t['task_name']}", callback_data=f"del|{t['id']}"))
    bot.send_message(m.chat.id, "ဖျက်မယ့်တစ်ခုကို ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del|"))
def handle_del(call):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (call.data.split("|")[1],))
    conn.commit()
    conn.close()
    bot.edit_message_text("✅ ဖျက်လိုက်ပါပြီ။", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("done|"))
def handle_done(call):
    _, tid, freq = call.data.split("|")
    bot.edit_message_text("✅ Task ပြီးဆုံးသွားပါပြီ။", call.message.chat.id, call.message.message_id)
    if freq == 'once':
        conn = get_db()
        conn.execute('DELETE FROM tasks WHERE id = ?', (tid,))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
