import os
import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters
)

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

participants = {}  # user_id: {nick, role, answered, wins}
asker_id = None
current_question = None
answers = {}
DATA_FILE = "users.json"
ANSWER_TIMEOUT = 300  # 5 минут
answer_tasks = {}

def load_data():
    global participants
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            participants = json.load(f)
            participants = {int(k): v for k, v in participants.items()}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    load_data()

    if user_id not in participants:
        participants[user_id] = {"nick": None, "role": None, "answered": False, "wins": 0}
        save_data()
        await update.message.reply_text("👤 Представься, Аноним:")
    else:
        nick = participants[user_id].get("nick")
        if nick:
            await update.message.reply_text(f"👋 С возвращением, {nick}!")
        else:
            await update.message.reply_text("👤 Представься, Аноним:")

async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global asker_id, current_question, answers

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in participants or participants[user_id]["nick"] is None:
        if text in ["🔸 Задающий", "🔹 Отвечающий"]:
            await update.message.reply_text("⛔ Это кнопка, а не имя! Напиши уникальный ник.")
            return
        participants[user_id] = {"nick": text, "role": None, "answered": False, "wins": 0}
        save_data()
        await update.message.reply_text(
            f"Приятно познакомиться, {text}!\nКем хочешь быть?",
            reply_markup=ReplyKeyboardMarkup([["🔸 Задающий"], ["🔹 Отвечающий"]],
            one_time_keyboard=True, resize_keyboard=True)
        )
        return

    if current_question and participants[user_id]["role"] is not None and text in ["🔸 Задающий", "🔹 Отвечающий"]:
        await update.message.reply_text("⛔ Роли уже распределены. Ты не можешь менять роль в этом раунде.")
        return

    if text == "🔸 Задающий":
        load_data()
        if any(p.get("role") == "asker" for p in participants.values()):
            await update.message.reply_text("⛔ В этом раунде уже есть задающий.")
            return
        participants[user_id]["role"] = "asker"
        asker_id = user_id
        save_data()
        await update.message.reply_text("✅ Ты стал задающим. Напиши свой вопрос:")
        return

    if text == "🔹 Отвечающий":
        if participants[user_id].get("role") != "answerer":
            participants[user_id]["role"] = "answerer"
            participants[user_id]["answered"] = False
            save_data()
            await update.message.reply_text("Ты Отвечающий.")
            if current_question:
                asker_nick = participants.get(asker_id, {}).get("nick", "Задающий")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Ответь на вопрос от {asker_nick}:\n❓ {current_question}"
                )
                task = asyncio.create_task(drop_if_silent(user_id, context))
                answer_tasks[user_id] = task
            else:
                await update.message.reply_text("Жди вопрос.")
        else:
            await update.message.reply_text("Ты уже Отвечающий.")
        return

    if current_question is None and participants.get(user_id, {}).get("role") == "asker":
        current_question = text
        answers = {}
        save_data()

        question_text = f"❓ Вопрос от {participants[user_id]['nick']}:\n{text}"
        for uid, info in participants.items():
            if info.get("role") == "answerer":
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"Ответь на вопрос от {participants[user_id]['nick']}:\n{question_text}"
                )
        await context.bot.send_message(chat_id=user_id, text=question_text)

        for uid, info in participants.items():
            if info.get("role") == "answerer":
                task = asyncio.create_task(drop_if_silent(uid, context))
                answer_tasks[uid] = task
        return

    if participants[user_id].get("role") == "answerer" and current_question:
        if participants[user_id]["answered"]:
            await update.message.reply_text("Ты уже ответил.")
            return
        participants[user_id]["answered"] = True
        answers[user_id] = text
        save_data()

        answer_text = f"💬 Ответ от {participants[user_id]['nick']}:\n{text}"
        for uid in participants:
            await context.bot.send_message(chat_id=uid, text=answer_text)

        if asker_id and asker_id in participants:
            buttons = [
                [InlineKeyboardButton(participants[uid]["nick"], callback_data=f"choose_{uid}")]
                for uid in answers
            ]
            markup = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(
                chat_id=asker_id,
                text="💡 Выбери лучший ответ:",
                reply_markup=markup
            )
        return

    await update.message.reply_text("Не понял. Пожалуйста, следуй инструкциям.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global answers
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if participants.get(user_id, {}).get("role") != "asker":
        await query.edit_message_text("⛔ Только задающий может выбирать лучший ответ.")
        return

    data = query.data
    if data.startswith("choose_"):
        chosen_id = int(data.replace("choose_", ""))
        chosen_nick = participants.get(chosen_id, {}).get("nick", "неизвестный")

        participants[chosen_id]["wins"] = participants[chosen_id].get("wins", 0) + 1
        save_data()

        win_count = participants[chosen_id]["wins"]

        for uid in participants:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"✅ {chosen_nick} дал лучший ответ! 🏆 Побед: {win_count}"
                )
            except:
                pass

        await new_round(context)

async def drop_if_silent(user_id, context):
    await asyncio.sleep(ANSWER_TIMEOUT)
    if not participants[user_id]["answered"]:
        participants[user_id]["role"] = None
        await context.bot.send_message(chat_id=user_id, text="⏰ Время вышло, ты выбыл из раунда.")
    else:
        if current_question and asker_id == user_id:
            await context.bot.send_message(chat_id=user_id, text="⏰ Время вышло для выбора победителя, раунд завершён!")
            await new_round(context)

async def new_round(context):
    global asker_id, current_question, answers, answer_tasks
    asker_id = None
    current_question = None
    answers = {}
    answer_tasks = {}

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
    save_data()

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_webhook(
        listen="0.0.0.0",
        port=10000,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
















