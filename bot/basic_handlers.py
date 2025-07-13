# basic_handlers.py - Базовые обработчики команд
from datetime import datetime
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
import config
from utils import register_user_if_not_exists

# Константы
HELP_MESSAGE = """Commands:
⚪ /retry – Regenerate last bot answer
⚪ /new – Start new dialog
⚪ /mode – Select chat mode
⚪ /settings – Show settings
⚪ /balance – Show balance
⚪ /premium – Premium subscription
⚪ /help – Show help

🎨 Generate images from text prompts in <b>👩‍🎨 Artist</b> /mode
👥 Add bot to <b>group chat</b>: /help_group_chat
🎤 You can send <b>Voice Messages</b> instead of text

💎 <b>Premium features:</b>
- 1000 messages/day (vs 5 free)
- GPT-4 and GPT-4o access
- 50 images/day (vs 2 free)
"""

HELP_GROUP_CHAT_MESSAGE = """You can add bot to any <b>group chat</b> to help and entertain its participants!

Instructions (see <b>video</b> below):
1. Add the bot to the group chat
2. Make it an <b>admin</b>, so that it can see messages (all other rights can be restricted)
3. You're awesome!

To get a reply from the bot in the chat – @ <b>tag</b> it or <b>reply</b> to its message.
For example: "{bot_username} write a poem about Telegram"
"""

async def start_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)

    reply_text = "Hi! I'm <b>ChatGPT</b> bot implemented with OpenAI API 🤖\n\n"
    reply_text += HELP_MESSAGE

    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
    await show_chat_modes_handle(update, context, db)

async def help_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)

async def help_group_chat_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text = HELP_GROUP_CHAT_MESSAGE.format(bot_username="@" + context.bot.username)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    await update.message.reply_video(config.help_group_chat_video_path)

async def new_dialog_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.set_user_attribute(user_id, "current_model", "gpt-3.5-turbo")

    db.start_new_dialog(user_id)
    await update.message.reply_text("Starting new dialog ✅")

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")
    await update.message.reply_text(f"{config.chat_modes[chat_mode]['welcome_message']}", parse_mode=ParseMode.HTML)

# Chat modes handlers
def get_chat_mode_menu(page_index: int):
    n_chat_modes_per_page = config.n_chat_modes_per_page
    text = f"Select <b>chat mode</b> ({len(config.chat_modes)} modes available):"

    # buttons
    chat_mode_keys = list(config.chat_modes.keys())
    page_chat_mode_keys = chat_mode_keys[page_index * n_chat_modes_per_page:(page_index + 1) * n_chat_modes_per_page]

    keyboard = []
    for chat_mode_key in page_chat_mode_keys:
        name = config.chat_modes[chat_mode_key]["name"]
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_chat_mode|{chat_mode_key}")])

    # pagination
    if len(chat_mode_keys) > n_chat_modes_per_page:
        is_first_page = (page_index == 0)
        is_last_page = ((page_index + 1) * n_chat_modes_per_page >= len(chat_mode_keys))

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

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_chat_mode_menu(0)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_chat_modes_callback_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)

    user_id = update.callback_query.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    query = update.callback_query
    await query.answer()

    page_index = int(query.data.split("|")[1])
    if page_index < 0:
        return

    text, reply_markup = get_chat_mode_menu(page_index)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass

async def set_chat_mode_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    chat_mode = query.data.split("|")[1]

    db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    db.start_new_dialog(user_id)

    await context.bot.send_message(
        update.callback_query.message.chat.id,
        f"{config.chat_modes[chat_mode]['welcome_message']}",
        parse_mode=ParseMode.HTML
    )

# Settings handlers
def get_settings_menu(user_id: int, db):
    current_model = db.get_user_attribute(user_id, "current_model")
    text = config.models["info"][current_model]["description"]

    text += "\n\n"
    score_dict = config.models["info"][current_model]["scores"]
    for score_key, score_value in score_dict.items():
        text += "🟢" * score_value + "⚪️" * (5 - score_value) + f" – {score_key}\n\n"

    text += "\nSelect <b>model</b>:"

    # buttons to choose models
    buttons = []
    for model_key in config.models["available_text_models"]:
        title = config.models["info"][model_key]["name"]
        if model_key == current_model:
            title = "✅ " + title

        buttons.append(
            InlineKeyboardButton(title, callback_data=f"set_settings|{model_key}")
        )
    reply_markup = InlineKeyboardMarkup([buttons])

    return text, reply_markup

async def settings_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_settings_menu(user_id, db)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def set_settings_handle(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    _, model_key = query.data.split("|")
    db.set_user_attribute(user_id, "current_model", model_key)
    db.start_new_dialog(user_id)

    text, reply_markup = get_settings_menu(user_id, db)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass
