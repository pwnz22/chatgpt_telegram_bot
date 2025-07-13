# basic_handlers.py - Базовые обработчики команд с поддержкой групп
from datetime import datetime
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
import config
from utils import register_user_if_not_exists, register_group_if_not_exists
from localization import t

async def start_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    # Регистрируем группу если это групповой чат
    if chat_id < 0:
        await register_group_if_not_exists(update, context, db)

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id, chat_id)

    # Проверяем, установлен ли уже язык у пользователя
    user_language = db.get_user_attribute(user_id, "language")

    if not user_language:
        # Если язык не установлен, показываем выбор языка НА РУССКОМ
        text = "🌐 <b>Выберите язык / Choose language:</b>"

        keyboard = [
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_language|ru")],
            [InlineKeyboardButton("🇺🇸 English", callback_data="set_language|en")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return

    # Если язык уже установлен, показываем обычное приветствие
    reply_text = t(user_id, "start_greeting")
    reply_text += t(user_id, "help_message")

    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

async def help_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    if chat_id < 0:
        await register_group_if_not_exists(update, context, db)

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    help_text = t(user_id, "help_message")
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def help_group_chat_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    if chat_id < 0:
        await register_group_if_not_exists(update, context, db)

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text = t(user_id, "help_group_chat", bot_username="@" + context.bot.username)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    await update.message.reply_video(config.help_group_chat_video_path)

async def new_dialog_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    if chat_id < 0:
        await register_group_if_not_exists(update, context, db)

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.set_user_attribute(user_id, "current_model", "gpt-3.5-turbo")

    db.start_new_dialog(user_id, chat_id)

    success_text = t(user_id, "new_dialog_started")
    await update.message.reply_text(success_text)

    # Получаем режим чата с учетом контекста (группа или приватный чат)
    chat_mode = db.get_chat_mode(user_id, chat_id)
    user_language = db.get_user_attribute(user_id, "language") or "en"

    welcome_message = config.chat_modes[chat_mode]["welcome_message"]

    # Если welcome_message - это словарь с языками
    if isinstance(welcome_message, dict):
        welcome_text = welcome_message.get(user_language, welcome_message.get("en", "Welcome!"))
    else:
        # Если обычная строка (обратная совместимость)
        welcome_text = welcome_message

    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

def get_chat_mode_menu(page_index: int, user_id: int, chat_id: int = None):
    """Получить меню режимов чата с поддержкой групп"""
    # Если это группа, берем настройки группы
    if chat_id and chat_id < 0:  # Отрицательный ID = группа
        from utils import register_group_if_not_exists
        text = t(user_id, "select_chat_mode", count=len(config.chat_modes))
    else:
        text = t(user_id, "select_chat_mode", count=len(config.chat_modes))

    # buttons
    chat_mode_keys = list(config.chat_modes.keys())
    page_chat_mode_keys = chat_mode_keys[page_index * config.n_chat_modes_per_page:(page_index + 1) * config.n_chat_modes_per_page]

    keyboard = []
    for chat_mode_key in page_chat_mode_keys:
        name = config.chat_modes[chat_mode_key]["name"]
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_chat_mode|{chat_mode_key}")])

    # pagination
    if len(chat_mode_keys) > config.n_chat_modes_per_page:
        is_first_page = (page_index == 0)
        is_last_page = ((page_index + 1) * config.n_chat_modes_per_page >= len(chat_mode_keys))

        if is_first_page:
            keyboard.append([
                InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
            ])
        elif is_last_page:
            keyboard.append([
                InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
                InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
            ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup

async def show_chat_modes_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_chat_mode_menu(0, user_id, chat_id)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_chat_modes_callback_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    user_id = update.callback_query.from_user.id
    chat_id = update.callback_query.message.chat.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    query = update.callback_query
    await query.answer()

    page_index = int(query.data.split("|")[1])
    if page_index < 0:
        return

    text, reply_markup = get_chat_mode_menu(page_index, user_id, chat_id)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass

async def set_chat_mode_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    user_id = update.callback_query.from_user.id
    chat_id = update.callback_query.message.chat.id

    query = update.callback_query
    await query.answer()

    chat_mode = query.data.split("|")[1]

    # Для групп сохраняем в настройках группы
    if chat_id < 0:  # Группа
        db.set_group_attribute(chat_id, "current_chat_mode", chat_mode)
        user_language = db.get_group_attribute(chat_id, "language") or "en"
    else:  # Личный чат
        db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
        db.start_new_dialog(user_id)
        user_language = db.get_user_attribute(user_id, "language") or "en"

    # Получаем локализованное welcome сообщение
    welcome_message = config.chat_modes[chat_mode]["welcome_message"]

    if isinstance(welcome_message, dict):
        welcome_text = welcome_message.get(user_language, welcome_message.get("en", "Welcome!"))
    else:
        welcome_text = welcome_message

    await context.bot.send_message(
        update.callback_query.message.chat.id,
        welcome_text,
        parse_mode=ParseMode.HTML
    )

def get_settings_menu(user_id: int, chat_id: int, db):
    """Получить меню настроек с поддержкой групп"""
    # Определяем откуда брать настройки
    if chat_id < 0:  # Группа
        current_model = db.get_group_attribute(chat_id, "current_model")
    else:  # Личный чат
        current_model = db.get_user_attribute(user_id, "current_model")

    text = config.models["info"][current_model]["description"]

    text += "\n\n"
    score_dict = config.models["info"][current_model]["scores"]
    for score_key, score_value in score_dict.items():
        text += "🟢" * score_value + "⚪️" * (5 - score_value) + f" – {score_key}\n\n"

    text += t(user_id, "select_model")

    # buttons to choose models
    keyboard = []
    for model_key in config.models["available_text_models"]:
        title = config.models["info"][model_key]["name"]
        if model_key == current_model:
            title = "✅ " + title

        keyboard.append([
            InlineKeyboardButton(title, callback_data=f"set_settings|{model_key}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    return text, reply_markup

async def settings_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_settings_menu(user_id, chat_id, db)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def set_settings_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    user_id = update.callback_query.from_user.id
    chat_id = update.callback_query.message.chat.id

    query = update.callback_query
    await query.answer()

    _, model_key = query.data.split("|")

    # Для групп сохраняем в настройках группы
    if chat_id < 0:  # Группа
        db.set_group_attribute(chat_id, "current_model", model_key)
    else:  # Личный чат
        db.set_user_attribute(user_id, "current_model", model_key)
        db.start_new_dialog(user_id)

    text, reply_markup = get_settings_menu(user_id, chat_id, db)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass
