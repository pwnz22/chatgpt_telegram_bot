# language_handlers.py - Обработчики языков с локализованными текстами (исправленная версия)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from datetime import datetime
from utils import register_user_if_not_exists, register_group_if_not_exists
from localization import t

async def language_handle(update: Update, context: CallbackContext, db):
    """Показать меню выбора языка с поддержкой групп"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text = t(user_id, "select_language")

    keyboard = []

    # Получаем текущий язык (группы или пользователя)
    if chat_id < 0:  # Группа
        current_lang = db.get_group_attribute(chat_id, "language") or "en"
    else:  # Личный чат
        current_lang = db.get_user_attribute(user_id, "language") or "en"

    # Создаем кнопки для языков
    languages = [
        ("en", "🇺🇸 English"),
        ("ru", "🇷🇺 Русский")
    ]

    for lang_code, lang_display in languages:
        if lang_code == current_lang:
            lang_display = "✅ " + lang_display

        keyboard.append([
            InlineKeyboardButton(lang_display, callback_data=f"set_language|{lang_code}")
        ])

    # Добавляем информационную кнопку
    info_text = t(user_id, "language_info_button")
    keyboard.append([InlineKeyboardButton(info_text, callback_data="language_info")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_language_info(update: Update, context: CallbackContext, db):
    """Показать информацию о языковых настройках"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    info_text = t(user_id, "language_info_text")

    # Добавляем кнопку "Назад"
    back_text = t(user_id, "back_to_language")
    keyboard = [[InlineKeyboardButton(back_text, callback_data="back_to_language_selection")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(info_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def back_to_language_selection(update: Update, context: CallbackContext, db):
    """Вернуться к выбору языка"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat.id

    # Повторно показываем меню выбора языка
    text = t(user_id, "select_language")

    keyboard = []

    # Получаем текущий язык (группы или пользователя)
    if chat_id < 0:  # Группа
        current_lang = db.get_group_attribute(chat_id, "language") or "en"
    else:  # Личный чат
        current_lang = db.get_user_attribute(user_id, "language") or "en"

    # Создаем кнопки для языков
    languages = [
        ("en", "🇺🇸 English"),
        ("ru", "🇷🇺 Русский")
    ]

    for lang_code, lang_display in languages:
        if lang_code == current_lang:
            lang_display = "✅ " + lang_display

        keyboard.append([
            InlineKeyboardButton(lang_display, callback_data=f"set_language|{lang_code}")
        ])

    # Добавляем информационную кнопку
    info_text = t(user_id, "how_language_works")
    keyboard.append([InlineKeyboardButton(info_text, callback_data="language_info")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def set_language_handle(update: Update, context: CallbackContext, db):
    """Установить язык с поддержкой групп"""
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat.id
    language = query.data.split("|")[1]

    # Определяем старый язык и устанавливаем новый
    if chat_id < 0:  # Группа
        old_language = db.get_group_attribute(chat_id, "language")
        db.set_group_attribute(chat_id, "language", language)
    else:  # Личный чат
        old_language = db.get_user_attribute(user_id, "language")
        db.set_user_attribute(user_id, "language", language)
        db.set_user_attribute(user_id, "last_interaction", datetime.now())

    # Если это первый выбор языка для личного чата
    if chat_id > 0 and old_language is None:
        # Начинаем новый диалог для применения языковых изменений
        db.start_new_dialog(user_id)

        # Показываем приветствие на выбранном языке
        reply_text = t(user_id, "start_greeting")
        reply_text += t(user_id, "help_message")

        await query.edit_message_text(reply_text, parse_mode=ParseMode.HTML)

        # Показываем режимы чата
        await show_chat_modes_handle_from_callback(query, context, db)
        return

    # Если язык уже был установлен ранее
    if old_language == language:
        # Язык не изменился, показываем текущий статус
        status_text = t(user_id, "language_already_set")
        await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
        return

    # Язык изменился
    if chat_id > 0:  # Личный чат - начинаем новый диалог
        db.start_new_dialog(user_id)

    # Отправляем уведомление на новом языке
    confirmation_text = t(user_id, "language_change_notification")
    await query.edit_message_text(confirmation_text, parse_mode=ParseMode.HTML)

# Обработчик для callback "language_info"
async def language_info_callback_handle(update: Update, context: CallbackContext, db):
    """Обработчик для кнопки информации о языке"""
    await show_language_info(update, context, db)

# Обработчик для callback "back_to_language_selection"
async def back_to_language_callback_handle(update: Update, context: CallbackContext, db):
    """Обработчик для кнопки возврата к выбору языка"""
    await back_to_language_selection(update, context, db)

# Вспомогательная функция для показа режимов чата из callback
async def show_chat_modes_handle_from_callback(query, context: CallbackContext, db):
    """Показать режимы чата после выбора языка"""
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # Используем обновленную функцию с правильными параметрами
    from basic_handlers import get_chat_mode_menu
    text, reply_markup = get_chat_mode_menu(0, user_id, chat_id, db)

    # Отправляем новое сообщение вместо редактирования
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
