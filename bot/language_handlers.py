# language_handlers.py - Обработчики языков
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from utils import register_user_if_not_exists
from localization import t, localization, TEXTS

async def language_handle(update: Update, context: CallbackContext, db):
    """Показать меню выбора языка"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id

    text = t(user_id, "select_language")

    keyboard = []

    # Получаем доступные языки напрямую из TEXTS
    available_languages = {
        "en": "🇺🇸 English",
        "ru": "🇷🇺 Русский"
    }

    # Получаем текущий язык пользователя
    current_lang = db.get_user_attribute(user_id, "language") or "en"

    for lang_code, lang_name in available_languages.items():
        if lang_code == current_lang:
            lang_name = "✅ " + lang_name

        keyboard.append([
            InlineKeyboardButton(lang_name, callback_data=f"set_language|{lang_code}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def set_language_handle(update: Update, context: CallbackContext, db):
    """Установить язык пользователя"""
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    language = query.data.split("|")[1]

    # Устанавливаем язык
    db.set_user_attribute(user_id, "language", language)

    # Отправляем подтверждение на новом языке
    confirmation_text = t(user_id, "language_changed")

    await query.edit_message_text(confirmation_text, parse_mode=ParseMode.HTML)
