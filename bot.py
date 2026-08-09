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

# --- Helper Logic ---
def parse_time(t_str):
    t_str = t_str.lower().replace('.', ':').replace(' ', ':')
    m = re.search(r'(\d{1,2}):?(\d{0,2})?\s?(am|pm)?', t_str)
    if not m: return None
    h, mn, p = m.groups()
    h, mn = int(h), int(mn or 0)
    if p == 'pm' and h < 12: h += 12
    if p == 'am' and h == 12: h = 0
    return f"{h:02d}:{mn:02d}"

def parse_date(d_str, freq):
    # MM-DD သို့မဟုတ် DD ပုံစံပြောင်းခြင်း
    nums = re.findall(r'\d+', d_str)
    if freq == 'monthly': return f"{int(nums[0]):02d}"
    if freq == 'yearly': return f"{int(nums[0]):02d}-{int(nums[1]):02d}"
    return None

# --- Database Setup ---
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- Flask & Scheduler ---
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def check_tasks():
    now = datetime.datetime.now(MYT)
    ct = now.strftime("%H:%M")
    td = now.strftime("%Y-%m-%d")
    t_day = now.strftime("%d")
    t_md = now.strftime("%m-%d")
    
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE time = ?', (ct,)).fetchall()
    for t in tasks:
        alert = False
        if t['frequency'] == 'daily': alert = True
        elif t['frequency'] == 'once' and t['task_date'] == td: alert = True
        elif t['frequency'] == 'monthly' and t['task_date'] == t_day: alert = True
        elif t['frequency'] == 'yearly' and t['task_date'] == t_md: alert = True
        
        if alert:
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("✅ Done / Dismiss", callback_data=f"done|{t['id']}|{t['frequency']}"))
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
    if freq == 'monthly': bot.send_message(call.message.chat.id, "လစဉ် ဘယ်ရက်လဲ? (ဥပမာ: 05):")
    elif freq == 'yearly': bot.send_message(call.message.chat.id, "နှစ်စဉ် ဘယ်နေ့လဲ? (လ-ရက်, ဥပမာ 08-09):")
    else: bot.send_message(call.message.chat.id, "အချိန်ကို ရိုက်ပါ (ဥပမာ 8:30 am):")
    bot.register_next_step_handler(call.message, handle_input)

def handle_input(m):
    uid = m.chat.id
    freq, name = user_steps[uid]['freq'], user_steps[uid]['name']
    
    if freq in ['monthly', 'yearly']:
        date_val = parse_date(m.text, freq)
        if not date_val:
            bot.send_message(m.chat.id, "❌ ရက်စွဲပုံစံ မမှန်ပါ။ ပြန်ကြိုးစားပါ။")
            return
        user_steps[uid]['date_val'] = date_val
        msg = bot.send_message(m.chat.id, "အချိန်ကို ရိုက်ပါ (ဥပမာ 8:30 am):")
        bot.register_next_step_handler(msg, lambda m2: save_task(m2, freq, name, date_val))
    else:
        save_task(m, freq, name, datetime.datetime.now(MYT).strftime("%Y-%m-%d"))

def save_task(m, freq, name, date_val):
    clean_time = parse_time(m.text)
    if not clean_time:
        bot.send_message(m.chat.id, "❌ အချိန်ပုံစံ မမှန်ပါ။")
        return
    conn = get_db()
    conn.execute('INSERT INTO tasks (chat_id, task_name, frequency, time, task_date) VALUES (?, ?, ?, ?, ?)', 
                 (m.chat.id, name, freq, clean_time, date_val))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ သိမ်းဆည်းပြီးပါပြီ!\n📌 {name} ({freq})\n⏰ {clean_time} {f'📅 {date_val}' if date_val else ''}")

@bot.message_handler(func=lambda m: m.text == "📋 View Tasks")
def view(m):
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE chat_id = ?', (m.chat.id,)).fetchall()
    conn.close()
    if not tasks: bot.send_message(m.chat.id, "ဘာမှ မရှိပါ။")
    else:
        text = "\n".join([f"📌 {t['task_name']} ({t['frequency']}) - ⏰ {t['time']} {f'[{t['task_date']}]' if t['task_date'] else ''}" for t in tasks])
        bot.send_message(m.chat.id, f"📋 သင့်ရဲ့ Task များ:\n{text}")

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
