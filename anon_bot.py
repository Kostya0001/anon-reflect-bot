import json
import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

participants = {}  # user_id: {'nick': str, 'role': 'asker' or 'answerer', 'answered': False}
asker_id = None
current_question = None
DATA_FILE = "users.json"
ANSWER_TIMEOUT = 300  # 5 минут
answer_tasks = {}  # user_id: asyncio.Task

# 📁 Загрузка
def load_participants():
    global participants
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            participants = json.load(f)
            for uid in list(participants.keys()):
                participants[int(uid)] = participants.pop(uid)

# 💾 Сохранение
def save_participants():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, ensure_ascii=False, indent=2)

# 🟢 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in participants or not participants[user_id].get("nick"):
        participants[user_id] = {"nick": None, "role": None, "answered": False}
        await update.message.reply_text("👤 Представься, Аноним:")
    else:
        await update.message.reply_text(f"С возвращением, {participants[user_id]['nick']}!")

# 👤 Ник
async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if participants[user_id]["nick"] is None:
        participants[user_id]["nick"] = update.message.text.strip()
        save_participants()
        await update.message.reply_text(
            "Кем хочешь быть?",
            reply_markup=ReplyKeyboardMarkup([["🔸 Задающий"], ["🔹 Отвечающий"]],
                                             resize_keyboard=True, one_time_keyboard=True)
        )
    else:
        await handle_role_selection(update, context)

# 🎭 Роль
async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global asker_id
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "🔸 Задающий":
        if asker_id is not None:
            await update.message.reply_text("Уже есть задающий. Дождись следующего раунда.")
            return
        participants[user_id]["role"] = "asker"
        asker_id = user_id
        await update.message.reply_text("Ты задающий. Напиши свой вопрос:")
    elif text == "🔹 Отвечающий":
        participants[user_id]["role"] = "answerer"
        await update.message.reply_text("Ты отвечающий. Жди вопрос.")
    else:
        await handle_message(update, context)

# ❓ Вопрос / ответ
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_question
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if participants[user_id]["role"] == "asker" and current_question is None:
        current_question = text
        for uid, info in participants.items():
            if info["role"] == "answerer":
                await context.bot.send_message(chat_id=uid, text=f"❓ Вопрос от {participants[user_id]['nick']}:\n{text}")
                participants[uid]["answered"] = False
                # ⏳ Запускаем таймер
                task = asyncio.create_task(answer_timer(uid, context))
                answer_tasks[uid] = task
        await update.message.reply_text("Вопрос отправлен. Жди ответы.")
    elif participants[user_id]["role"] == "answerer" and current_question:
        if not participants[user_id]["answered"]:
            participants[user_id]["answered"] = True
            if user_id in answer_tasks:
                answer_tasks[user_id].cancel()
            await context.bot.send_message(chat_id=asker_id,
                                           text=f"💬 Ответ от {participants[user_id]['nick']}:\n{text}")
        else:
            await update.message.reply_text("Ты уже отвечал.")
    elif participants[user_id]["role"] == "asker" and text in [p["nick"] for uid, p in participants.items() if uid != user_id]:
        # Выбор победителя
        winner_id = next(uid for uid, p in participants.items() if p["nick"] == text)
        for uid in participants:
            await context.bot.send_message(chat_id=uid,
                                           text=f"🏆 Ответ {participants[winner_id]['nick']} выбран как лучший!")
        await new_round(update, context)
    else:
        await update.message.reply_text("Подожди своей очереди или выбери роль.")

# ⏰ Таймер ответа
async def answer_timer(uid, context):
    await asyncio.sleep(ANSWER_TIMEOUT)
    if not participants[uid]["answered"]:
        await context.bot.send_message(chat_id=uid, text="⏳ Время ответа вышло. Ты выбываешь.")
        participants[uid]["role"] = None

# 🔁 /newround
async def new_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global asker_id, current_question, answer_tasks
    asker_id = None
    current_question = None
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

# ▶️ Запуск
def main():
    load_participants()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newround", new_round))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname))
    app.run_polling()

if __name__ == "__main__":
    main()

