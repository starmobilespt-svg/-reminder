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

# --- Database Setup ---
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- Flask & Scheduler ---
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- Notification Logic (Button ပါဝင်သည်) ---
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
            # Dismiss လုပ်ဖို့ခလုတ် ထည့်ပေးခြင်း
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("✅ Done / Dismiss", callback_data=f"done|{t['id']}|{t['frequency']}"))
            
            bot.send_message(t['chat_id'], f"🚨⏰ **ALARM!** ⏰🚨\n\n📌 **Task:** {t['task_name']}", reply_markup=kb)
    conn.close()

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_tasks, 'cron', minute='*')
scheduler.start()

# --- Callback Handler (နှိပ်လိုက်ရင် ပျောက်သွားအောင်) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("done|"))
def handle_done(call):
    _, task_id, freq = call.data.split("|")
    
    # Message ကို ပြင်လိုက်ခြင်း
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=f"✅ Task ပြီးဆုံးသွားပါပြီ။")
    
    # တစ်ကြိမ်သာ အလုပ်ဆိုရင် Database ကနေ ဖျက်ထုတ်မယ်
    if freq == 'once':
        conn = get_db()
        conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

# --- UI & Handlers (ယခင်အတိုင်း) ---
def main_kb():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Task", "📋 View Tasks")
    kb.add("🗑 Delete Task", "📥 Backup DB", "📤 Restore DB")
    return kb

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id, "👋 Reminder Bot အသင့်ဖြစ်ပါပြီ။", reply_markup=main_kb())

# (Add/View/Delete/Backup/Restore လုပ်ဆောင်ချက်များကို ယခင်အတိုင်း ထည့်သွင်းထားပါ)
# ... [Add/View/Delete/Backup/Restore code များ] ...
# သင့်မှာရှိပြီးသား ကုဒ်များကို ဒီအောက်မှာ ဆက်ထည့်ပေးလိုက်ပါ။

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
