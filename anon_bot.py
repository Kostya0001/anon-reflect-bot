# ⚠️ добавляем в начало
WELCOME_TEXT = """
🎭 Добро пожаловать в Анонимную Игру! 

Здесь ты можешь:
– задавать вопросы незнакомцам,  
– получать неожиданные ответы,  
– почувствовать себя маской с характером.

Но прежде чем начнём – вот **несколько ПРАВИЛ**: 

🚫 Не пытайся вычислить, кто есть кто.  
🚫 Не пиши своё настоящее имя – будь кем угодно, хоть Устрицей Гнева.  
🚫 Не флууди, не молчи, не груби.  

А главное:  
✅ Играй честно, слушай внимательно и выбирай душой.

Когда готов – нажми кнопку ниже 👇
"""

# 📍 функция start теперь выглядит вот так:
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    load_data()

    # Если участник есть, но еще не подтвердил правила
    if user_id not in participants:
        participants[user_id] = {
            "nick": None,
            "role": None,
            "answered": False,
            "wins": 0,
            "accepted_rules": False
        }
        save_data()

    if not participants[user_id].get("accepted_rules", False):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Я понял", callback_data="accept_rules")]
        ])
        await update.message.reply_text(WELCOME_TEXT, reply_markup=keyboard)
    else:
        await update.message.reply_text(f"👋 С возвращением, {participants[user_id]['nick']}!")

# 📍 обработка нажатия кнопки "Я понял"
async def accept_rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    participants[user_id]["accepted_rules"] = True
    save_data()

    await query.message.delete()  # удалим правила
    await context.bot.send_message(
        chat_id=user_id,
        text="👤 Представься, Аноним:"
    )

# 📍 в main() добавь:
app.add_handler(CallbackQueryHandler(accept_rules_callback, pattern="^accept_rules$"))




















