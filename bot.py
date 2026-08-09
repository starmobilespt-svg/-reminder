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
user_steps = {} # အဆင့်ဆင့်မှတ်သားရန်
MYT = pytz.timezone('Asia/Yangon')

# --- Database & Setup ---
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

# --- Parsing Logic (အချိန်နှင့်ရက်စွဲ ပုံစံမျိုးစုံ လက်ခံပေးခြင်း) ---
def parse_time(time_str):
    # 8:30, 8.30, 8 30, 0830, 8am, 8pm အကုန်ရ
    time_str = time_str.lower().strip().replace('.', ':').replace(' ', ':')
    match = re.search(r'(\d{1,2}):?(\d{0,2})?\s?(am|pm)?', time_str)
    if not match: return None
    h, m, p = match.groups()
    h, m = int(h), int(m or 0)
    if p == 'pm' and h < 12: h += 12
    if p == 'am' and h == 12: h = 0
    if h > 23 or m > 59: return None
    return f"{h:02d}:{m:02d}"

# --- Flask Keep-Alive ---
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- Scheduler ---
def check_tasks():
    now = datetime.datetime.now(MYT)
    ct = now.strftime("%H:%M")
    td = now.strftime("%Y-%m-%d")
    t_day = now.strftime("%d")
    t_md = now.strftime("%m-%d")
    
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (ct,)).fetchall()
    for t in tasks:
        alert = (t['frequency'] == 'daily') or \
                (t['frequency'] == 'once' and t['task_date'] == td) or \
                (t['frequency'] == 'monthly' and t['task_date'] == t_day) or \
                (t['frequency'] == 'yearly' and t['task_date'] == t_md)
        if alert:
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("✅ Done", callback_data=f"done|{t['id']}|{t['frequency']}"))
            bot.send_message(t['chat_id'], f"🚨⏰ **ALARM!**\n📌 **{t['task_name']}**", reply_markup=kb)
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

# --- Add Task Logic ---
@bot.message_handler(func=lambda m: m.text == "➕ Add Task")
def add_task(m):
    msg = bot.send_message(m.chat.id, "အလုပ်အမည် ရိုက်ထည့်ပါ:")
    bot.register_next_step_handler(msg, lambda msg2: ask_freq(msg2, msg2.text))

def ask_freq(m, name):
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("နေ့စဉ်", callback_data=f"freq|daily|{name}"),
           telebot.types.InlineKeyboardButton("တစ်ကြိမ်", callback_data=f"freq|once|{name}"))
    kb.add(telebot.types.InlineKeyboardButton("လစဉ်", callback_data=f"freq|monthly|{name}"),
           telebot.types.InlineKeyboardButton("နှစ်စဉ်", callback_data=f"freq|yearly|{name}"))
    bot.send_message(m.chat.id, "ပုံစံ ရွေးပါ:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("freq|"))
def freq_callback(call):
    _, freq, name = call.data.split("|")
    user_steps[call.message.chat.id] = {'freq': freq, 'name': name}
    if freq == 'monthly': bot.send_message(call.message.chat.id, "လစဉ် ဘယ်ရက်လဲ? (01-31):")
    elif freq == 'yearly': bot.send_message(call.message.chat.id, "နှစ်စဉ် ဘယ်နေ့လဲ? (လ-ရက်, ဥပမာ 08-09):")
    else: bot.send_message(call.message.chat.id, "အချိန်ကို ရိုက်ပါ (ဥပမာ 8:30 am):")
    bot.register_next_step_handler(call.message, handle_input)

def handle_input(m):
    uid = m.chat.id
    freq, name = user_steps[uid]['freq'], user_steps[uid]['name']
    
    # Validation Logic
    if freq in ['monthly', 'yearly']:
        date_val = m.text
        # ရိုးရှင်းသော ရက်စွဲစစ်ဆေးခြင်း
        if len(date_val) > 5: 
            bot.send_message(m.chat.id, "❌ ပုံစံမမှန်ပါ။ ပြန်ကြိုးစားပါ။")
            return
        msg = bot.send_message(m.chat.id, "အချိန်ကို ရိုက်ပါ (ဥပမာ 8:30 am):")
        bot.register_next_step_handler(msg, lambda msg2: save_task(msg2, freq, name, date_val))
    else:
        save_task(m, freq, name, datetime.datetime.now(MYT).strftime("%Y-%m-%d"))

def save_task(m, freq, name, date_val):
    clean_time = parse_time(m.text)
    if not clean_time:
        bot.send_message(m.chat.id, "❌ အချိန်ပုံစံ မမှန်ပါ။ (ဥပမာ: 8:30 am သို့မဟုတ် 20:00)")
        return
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, clean_time, date_val))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ သိမ်းဆည်းပြီးပါပြီ!\n📌 {name} ({freq})\n⏰ {clean_time}")

# --- View / Delete / Dismiss ---
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
    if not tasks: bot.send_message(m.chat.id, "ဖျက်စရာ မရှိပါ။")
    else:
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

# Backup/Restore (ယခင်ကအတိုင်း...)
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
