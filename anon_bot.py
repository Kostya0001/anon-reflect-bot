import os
import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

participants = {}  # user_id: {nick, role, answered}
asker_id = None
current_question = None
answers = {}
DATA_FILE = "users.json"
ANSWER_TIMEOUT = 300  # 5 minutes timeout
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
    participants[user_id] = {"nick": None, "role": None, "answered": False}
    save_data()
    await update.message.reply_text("👤 Представься, Аноним:")

async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global asker_id, current_question, answers

    user_id = update.effective_user.id
    text = update.message.text.strip()

    # представление
    if user_id not in participants or participants[user_id]["nick"] is None:
        if text in ["🔸 Задающий", "🔹 Отвечающий"]:
            await update.message.reply_text("⛔ Это кнопка, а не имя! Напиши уникальный ник.")
            return
        participants[user_id] = {"nick": text, "role": None, "answered": False}
        save_data()
        await update.message.reply_text(f"Приятно познакомиться, {text}!\nКем хочешь быть?",
            reply_markup=ReplyKeyboardMarkup([["🔸 Задающий"], ["🔹 Отвечающий"]],
            one_time_keyboard=True, resize_keyboard=True))
        return

    # выбор роли
    if text == "🔸 Задающий":
        load_data()
        if any(p.get("role") == "asker" for p in participants.values()):
            await update.message.reply_text("⛔ В этом раунде уже есть задающий.")
            return
        participants[user_id]["role"] = "asker"
        global asker_id
        asker_id = user_id
        save_data()
        await update.message.reply_text("✅ Ты стал задающим. Напиши свой вопрос:")
        return

    if text == "🔹 Отвечающий":
        if participants[user_id].get("role") != "answerer":
            participants[user_id]["role"] = "answerer"
            participants[user_id]["answered"] = False
            save_data()
        await update.message.reply_text("Ты Отвечающий. Жди вопрос.")
        return

    # задающий пишет вопрос
    if current_question is None and participants.get(user_id, {}).get("role") == "asker":
        current_question = text
        answers = {}
        save_data()

        question_text = f"❓ Вопрос от {participants[user_id]['nick']}:\n{text}"
        # отправляем вопрос всем ответчикам с просьбой ответить
        for uid, info in participants.items():
            if info.get("role") == "answerer":
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"Ответь на вопрос от {participants[user_id]['nick']}:\n{question_text}"
                )
        # задающему тоже отправим для подтверждения
        await context.bot.send_message(chat_id=user_id, text=question_text)

        # запускаем таймер
        for uid, info in participants.items():
            if info.get("role") == "answerer":
                task = asyncio.create_task(drop_if_silent(uid, context))
                answer_tasks[uid] = task
        return

    # отвечающий пишет ответ
    if participants[user_id].get("role") == "answerer" and current_question:
        if participants[user_id]["answered"]:
            await update.message.reply_text("Ты уже ответил.")
            return
        participants[user_id]["answered"] = True
        answers[user_id] = text
        save_data()

        # Отправляем ответ всем участникам, чтобы все видели
        answer_text = f"💬 Ответ от {participants[user_id]['nick']}:\n{text}"
        for uid, info in participants.items():
            await context.bot.send_message(chat_id=uid, text=answer_text)
        return

    # задающий выбирает ответ
    if participants[user_id].get("role") == "asker" and current_question and text in [participants[uid]['nick'] for uid in answers]:
        chosen_id = [uid for uid, data in participants.items() if data['nick'] == text][0]
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text=f"✅ {participants[chosen_id]['nick']} дал лучший ответ!")
        await new_round(context)
        return

    await update.message.reply_text("Не понял. Пожалуйста, следуй инструкциям.")

async def drop_if_silent(user_id, context):
    await asyncio.sleep(ANSWER_TIMEOUT)  # 5 минут
    if not participants[user_id]["answered"]:
        participants[user_id]["role"] = None
        await context.bot.send_message(chat_id=user_id, text="⏰ Время вышло, ты выбыл из раунда.")
    else:
        # автоматически завершение раунда после 5 минут без выбора победителя
        if current_question and asker_id == user_id:  # если мы ещё в процессе
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
    app.run_webhook(
        listen="0.0.0.0",
        port=10000,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()










