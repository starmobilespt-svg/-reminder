import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz
import os

# ----------------- Configurations -----------------
# သင်၏ Telegram Bot Token နှင့် MongoDB URI ကို ဤနေရာတွင် ထည့်ပါ။
# Render Environment Variables မှတစ်ဆင့် ခေါ်သုံးခြင်းဖြစ်ပါသည်။
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
MONGO_URI = os.environ.get('MONGO_URI', 'YOUR_MONGODB_URI_HERE')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ----------------- Database Setup -----------------
# MongoDB သို့ ချိတ်ဆက်ခြင်း
client = MongoClient(MONGO_URI)
db = client['ReminderBotDB']
tasks_col = db['tasks']

# ----------------- State Management -----------------
# User တွေ အချက်အလက်ဖြည့်နေစဉ် ခေတ္တမှတ်ထားမည့် နေရာ
user_steps = {}

# ----------------- Flask Web Server (For Render Keep-Alive) -----------------
@app.route('/')
def home():
    return "Bot is awake and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ----------------- Scheduler (အချိန်ကိုက် သတိပေးစနစ်) -----------------
def check_reminders():
    tz = pytz.timezone('Asia/Yangon')
    now = datetime.datetime.now(tz)
    current_time = now.strftime("%H:%M")
    
    # Database ထဲမှ ယခုအချိန်နှင့် ကိုက်ညီသော Task များကို ရှာခြင်း
    tasks = tasks_col.find({"time": current_time})
    for task in tasks:
        bot.send_message(
            task['chat_id'], 
            f"⏰ **Reminder Alert!**\n\n📌 **Task:** {task['task_name']}\n🔁 **Type:** {task['frequency'].capitalize()}",
            parse_mode="Markdown"
        )

# မိနစ်တိုင်း စစ်ဆေးမည့် Scheduler စတင်ခြင်း
scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yangon'))
scheduler.add_job(check_reminders, 'cron', minute='*')
scheduler.start()

# ----------------- Bot Handlers (Bot အလုပ်လုပ်ပုံများ) -----------------

# /start နှိပ်လျှင် ပေါ်မည့် Main Menu (Bottom Buttons)
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup(row_width=2)
    btn_add = InlineKeyboardButton("➕ Add Task", callback_data="add_task")
    btn_view = InlineKeyboardButton("📋 View Tasks", callback_data="view_tasks")
    btn_delete = InlineKeyboardButton("🗑 Delete Task", callback_data="delete_task")
    markup.add(btn_add, btn_view, btn_delete)
    
    bot.send_message(message.chat.id, "👋 မင်္ဂလာပါ! ကျွန်တော်က သင့်ရဲ့ ကိုယ်ပိုင် Reminder Bot ပါ။\n\nအောက်ပါခလုတ်များကိုနှိပ်၍ အသုံးပြုနိုင်ပါသည်။", reply_markup=markup)

# ခလုတ်များကို နှိပ်လိုက်လျှင် အလုပ်လုပ်မည့် အပိုင်း
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    
    if call.data == "add_task":
        msg = bot.send_message(chat_id, "✍️ မှတ်သားလိုသော အလုပ် (Task) အမည်ကို ရိုက်ထည့်ပါ-")
        bot.register_next_step_handler(msg, process_task_name)
        
    elif call.data == "view_tasks":
        tasks = list(tasks_col.find({"chat_id": chat_id}))
        if not tasks:
            bot.send_message(chat_id, "🤷‍♂️ မှတ်ထားသော Task များ မရှိသေးပါ။")
            return
        
        reply = "📋 **သင့်၏ Tasks များ:**\n\n"
        for idx, t in enumerate(tasks, 1):
            reply += f"{idx}. {t['task_name']} ({t['frequency']}) - ⏰ {t['time']}\n"
        bot.send_message(chat_id, reply, parse_mode="Markdown")
        
    elif call.data == "delete_task":
        tasks = list(tasks_col.find({"chat_id": chat_id}))
        if not tasks:
            bot.send_message(chat_id, "🤷‍♂️ ဖျက်ရန် Task များ မရှိသေးပါ။")
            return
            
        markup = InlineKeyboardMarkup(row_width=1)
        for t in tasks:
            markup.add(InlineKeyboardButton(f"❌ {t['task_name']}", callback_data=f"del_{t['_id']}"))
        bot.send_message(chat_id, "ဖျက်လိုသော Task ကို ရွေးချယ်ပါ-", reply_markup=markup)
        
    elif call.data.startswith("del_"):
        task_id = call.data.split("_")[1]
        from bson.objectid import ObjectId
        tasks_col.delete_one({"_id": ObjectId(task_id)})
        bot.send_message(chat_id, "✅ Task ကို အောင်မြင်စွာ ဖျက်လိုက်ပါပြီ။")

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
    
    # အချိန်ပုံစံ မှန်မမှန် စစ်ဆေးခြင်း
    try:
        datetime.datetime.strptime(time_str, '%H:%M')
    except ValueError:
        msg = bot.send_message(chat_id, "❌ အချိန်ပုံစံမှားယွင်းနေပါသည်။ (ဥပမာ - 14:30) ဟု ပြန်ရိုက်ပါ။")
        bot.register_next_step_handler(msg, process_time)
        return

    if chat_id in user_steps:
        task_data = {
            "chat_id": chat_id,
            "task_name": user_steps[chat_id]['task_name'],
            "frequency": user_steps[chat_id]['frequency'],
            "time": time_str
        }
        # Database ထဲသို့ ထည့်ခြင်း
        tasks_col.insert_one(task_data)
        del user_steps[chat_id]
        
        bot.send_message(chat_id, f"✅ အောင်မြင်စွာ မှတ်သားလိုက်ပါပြီ!\n\n📌 {task_data['task_name']}\n⏰ နေ့စဉ် {time_str} အချိန်တွင် သတိပေးပါမည်။")

# ----------------- Start Application -----------------
if __name__ == "__main__":
    # Flask Server ကို နောက်ကွယ် (Background Thread) မှ Run ခြင်း
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Telegram Bot ကို Run ခြင်း
    print("Bot is running...")
    bot.infinity_polling()
