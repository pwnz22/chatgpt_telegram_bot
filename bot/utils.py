# utils.py - Вспомогательные функции
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
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_model") is None:
        db.set_user_attribute(user.id, "current_model", config.models["available_text_models"][0])

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

def split_text_into_chunks(text, chunk_size):
    """Разделение текста на части"""
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]
