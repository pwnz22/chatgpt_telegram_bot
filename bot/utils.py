# utils.py - Вспомогательные функции с поддержкой групп
import asyncio
from datetime import datetime
from telegram import Update, User
from telegram.ext import CallbackContext
import config

async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User, db):
    """Регистрация пользователя если не существует"""

    # Получаем chat_id в зависимости от типа update
    if hasattr(update, 'message') and update.message:
        chat_id = update.message.chat_id
    elif hasattr(update, 'callback_query') and update.callback_query:
        chat_id = update.callback_query.message.chat_id
    else:
        chat_id = user.id  # fallback

    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        db.start_new_dialog(user.id, chat_id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id, chat_id)

    if db.get_user_attribute(user.id, "current_model") is None:
        db.set_user_attribute(user.id, "current_model", config.default_model)  # Используем из env

    # back compatibility for n_used_tokens field
    n_used_tokens = db.get_user_attribute(user.id, "n_used_tokens")
    if isinstance(n_used_tokens, int) or isinstance(n_used_tokens, float):  # old format
        new_n_used_tokens = {
            "gpt-3.5-turbo": {
                "n_input_tokens": 0,
                "n_output_tokens": n_used_tokens
            }
        }
        db.set_user_attribute(user.id, "n_used_tokens", new_n_used_tokens)

    # voice message transcription
    if db.get_user_attribute(user.id, "n_transcribed_seconds") is None:
        db.set_user_attribute(user.id, "n_transcribed_seconds", 0.0)

    # image generation
    if db.get_user_attribute(user.id, "n_generated_images") is None:
        db.set_user_attribute(user.id, "n_generated_images", 0)

async def register_group_if_not_exists(update: Update, context: CallbackContext, db):
    """Регистрация группы если не существует (без изменения администратора)"""
    if update.message:
        chat = update.message.chat
        user_id = update.message.from_user.id
    elif update.callback_query:
        chat = update.callback_query.message.chat
        user_id = update.callback_query.from_user.id
    else:
        return

    # Только для групп
    if chat.type not in ["group", "supergroup"]:
        return

    group_id = chat.id
    group_title = chat.title or "Unknown Group"

    if not db.check_if_group_exists(group_id):
        # Если группы нет в базе, создаем без администратора
        # Администратор должен быть установлен через my_chat_member_handler
        db.add_new_group(group_id, group_title, admin_id=None)
    else:
        # Обновляем время последнего взаимодействия
        db.set_group_attribute(group_id, "last_interaction", datetime.now())

async def check_group_admin_rights(update: Update, context: CallbackContext, db) -> bool:
    """Проверить права администратора группы (только тот, кто добавил бота)"""
    if update.message:
        chat_id = update.message.chat.id
        user_id = update.message.from_user.id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat.id
        user_id = update.callback_query.from_user.id
    else:
        return False

    # Для личных чатов всегда разрешаем
    if chat_id > 0:
        return True

    # Проверяем, является ли пользователь тем, кто добавил бота в группу
    group_admin_id = db.get_group_attribute(chat_id, "admin_id")

    # Если администратор не установлен, временно разрешаем первому пользователю
    if group_admin_id is None:
        # Устанавливаем текущего пользователя как администратора
        db.set_group_admin_id(chat_id, user_id)
        return True

    return group_admin_id == user_id


def split_text_into_chunks(text, chunk_size):
    """Разделение текста на части"""
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]

async def send_admin_rights_error(update: Update, context: CallbackContext, db):
    """Отправить сообщение об отсутствии прав администратора с именем того, кто добавил бота"""
    from localization import t

    if update.message:
        user_id = update.message.from_user.id
        chat_id = update.message.chat.id
        reply_method = update.message.reply_text
    else:
        user_id = update.callback_query.from_user.id
        chat_id = update.callback_query.message.chat.id
        reply_method = lambda text, **kwargs: update.callback_query.answer(text, show_alert=True)

    # Получаем информацию о том, кто добавил бота
    admin_id = db.get_group_admin_id(chat_id)

    try:
        admin_info = await context.bot.get_chat_member(chat_id, admin_id)
        admin_name = admin_info.user.first_name
        if admin_info.user.username:
            admin_name += f" (@{admin_info.user.username})"
    except:
        admin_name = f"ID: {admin_id}"

    error_text = t(user_id, "group_admin_only_with_name", chat_id=chat_id, admin_name=admin_name)
    await reply_method(error_text)
