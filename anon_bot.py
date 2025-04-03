
import os
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

users = {}  # user_id: {"nickname": str, "role": "ask" or "reply"}
current_question = None
current_asker = None
answers = {}
question_time = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in users:
        await update.message.reply_text(f"С возвращением, {users[user_id]['nickname']}!")
    else:
        await update.message.reply_text("Представься, Аноним:")
        users[user_id] = {"nickname": None, "role": None}

async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if users[user_id]["nickname"] is None:
        users[user_id]["nickname"] = text
        await update.message.reply_text(
            f"Приятно познакомиться, {text}! Выбери роль:",
            reply_markup=ReplyKeyboardMarkup([["🔸 Задающий", "🔹 Отвечающий"]], resize_keyboard=True)
        )
        return

    if text == "🔸 Задающий":
        if any(u.get("role") == "ask" for u in users.values()):
            await update.message.reply_text("Уже есть задающий. Подожди следующего раунда.")
            return
        users[user_id]["role"] = "ask"
        await update.message.reply_text("Ты Задающий. Напиши свой вопрос:")
    elif text == "🔹 Отвечающий":
        users[user_id]["role"] = "reply"
        await update.message.reply_text("Ты Отвечающий. Жди вопрос.")
    else:
        await handle_game(update, context)

async def handle_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_question, current_asker, question_time, answers

    user_id = update.effective_user.id
    text = update.message.text

    if users[user_id]["role"] == "ask" and not current_question:
        current_question = text
        current_asker = user_id
        question_time = datetime.datetime.now()
        answers = {}
        for uid, info in users.items():
            if info["role"] == "reply":
                await context.bot.send_message(chat_id=uid, text=f"❓ Вопрос от {users[user_id]['nickname']}:
{text}")
        await update.message.reply_text("Вопрос отправлен.")
    elif users[user_id]["role"] == "reply" and current_question:
        answers[user_id] = text
        await context.bot.send_message(chat_id=current_asker, text=f"💬 Ответ от {users[user_id]['nickname']}:
{text}")
    elif user_id == current_asker and text in [users[u]["nickname"] for u in answers]:
        selected_id = next(u for u in answers if users[u]["nickname"] == text)
        for uid in users:
            msg = f"🎉 Выбран ответ {users[selected_id]['nickname']}:
{answers[selected_id]}"
            context.bot.send_message(chat_id=uid, text=msg)
        current_question = None
        current_asker = None
        answers = {}
        for uid in users:
            users[uid]["role"] = None
        await context.bot.send_message(chat_id=current_asker, text="Раунд завершен. Все могут выбрать роль заново.")
    else:
        await update.message.reply_text("Подожди своей очереди или выбери роль.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname))
    app.run_polling()

if __name__ == "__main__":
    main()
