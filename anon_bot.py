import os
import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

participants = {}
asker_id = None
current_question = None
answers = {}
answer_tasks = {}
DATA_FILE = "users.json"
ANSWER_TIMEOUT = 300  # 5 минут

def load_participants():
    global participants
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            participants = json.load(f)
            for uid in list(participants.keys()):
                participants[int(uid)] = participants.pop(uid)

def save_participants():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in participants or not participants[user_id].get("nick"):
        participants[user_id] = {"nick": None, "role": None, "answered": False}
        await update.message.reply_text("👤 Представься, Аноним:")
    else:
        await update.message.reply_text(f"С возвращением, {participants[user_id]['nick']}!")

async def handle_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if participants.get(user_id, {}).get("nick"):
        return
    participants[user_id]["nick"] = update.message.text.strip()
    save_participants()
    await update.message.reply_text(
        "🎭 Кем ты хочешь быть в этом раунде?",
        reply_markup=ReplyKeyboardMarkup([["🔸 Задающий"], ["🔹 Отвечающий"]],
                                         one_time_keyboard=True,
                                         resize_keyboard=True)
    )

async def handle_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global asker_id, current_question, answers
    user_id = update.effective_user.id
    text = update.message.text
    if user_id not in participants or not participants[user_id].get("nick"):
        return
    if participants[user_id]["role"]:
        return
    if text == "🔸 Задающий":
        if asker_id is None:
            participants[user_id]["role"] = "asker"
            asker_id = user_id
            await update.message.reply_text("✍️ Напиши свой вопрос:")
        else:
            await update.message.reply_text("Уже есть задающий. Ты автоматически становишься отвечающим.")
            participants[user_id]["role"] = "answerer"
    elif text == "🔹 Отвечающий":
        participants[user_id]["role"] = "answerer"
        await update.message.reply_text("Ты Отвечающий. Жди вопрос.")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_question, answers
    user_id = update.effective_user.id
    text = update.message.text
    if user_id == asker_id and not current_question:
        current_question = text
        answers = {}
        for uid, info in participants.items():
            if info.get("role") == "answerer":
                await context.bot.send_message(chat_id=uid, text=f"❓ Вопрос от {participants[asker_id]['nick']}:\n{text}")
                task = asyncio.create_task(answer_timer(uid, context))
                answer_tasks[uid] = task
        await update.message.reply_text("Вопрос отправлен! Ждём ответы.")

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if current_question and participants.get(user_id, {}).get("role") == "answerer":
        answers[user_id] = text
        participants[user_id]["answered"] = True
        if user_id in answer_tasks:
            answer_tasks[user_id].cancel()
        await context.bot.send_message(chat_id=asker_id,
                                       text=f"💬 Ответ от {participants[user_id]['nick']}:\n{text}",
                                       reply_markup=InlineKeyboardMarkup([[
                                           InlineKeyboardButton(f"Выбрать ответ от {participants[user_id]['nick']}",
                                                                callback_data=f"select_{user_id}")
                                       ]]))

async def answer_timer(uid, context):
    try:
        await asyncio.sleep(ANSWER_TIMEOUT)
        if uid not in answers:
            await context.bot.send_message(chat_id=uid, text="⏰ Время вышло! Ты выбыл из раунда.")
    except asyncio.CancelledError:
        pass

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global asker_id, current_question, answers, answer_tasks
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != asker_id:
        await query.edit_message_text("Только задающий может выбирать ответ.")
        return
    selected_uid = int(query.data.replace("select_", ""))
    winner_nick = participants[selected_uid]["nick"]
    await context.bot.send_message(chat_id=asker_id, text=f"🎉 Ты выбрал ответ от {winner_nick}!")
    for uid in participants:
        if uid != asker_id:
            try:
                await context.bot.send_message(chat_id=uid, text=f"🎉 Победил ответ от {winner_nick}!")
            except:
                pass
    await new_round(context)

async def new_round(context: ContextTypes.DEFAULT_TYPE):
    global asker_id, current_question, answers, answer_tasks
    asker_id = None
    current_question = None
    answers = {}
    answer_tasks.clear()
    for uid in participants:
        participants[uid]["role"] = None
        participants[uid]["answered"] = False
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="🎲 Новый раунд начался! Кем хочешь быть?",
                reply_markup=ReplyKeyboardMarkup(
                    [["🔸 Задающий"], ["🔹 Отвечающий"]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
        except:
            pass

def main():
    load_participants()
    app = ApplicationBuilder().token(TOKEN).webhook_url(WEBHOOK_URL).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nick))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_role))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))
    app.run_webhook()

if __name__ == "__main__":
    main()



