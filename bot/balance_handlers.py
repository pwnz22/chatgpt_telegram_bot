# balance_handlers.py - Обработчики баланса и статистики с локализацией
from datetime import datetime
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from utils import register_user_if_not_exists
from localization import t

# Заменить в balance_handlers.py функцию с исправленными вызовами t()

async def show_balance_handle(update: Update, context: CallbackContext, db):
    """Показать баланс и статистику с учетом подписки"""

    # Определяем откуда пришел запрос - команда или callback
    if update.message:
        # Пришло через команду /balance
        await register_user_if_not_exists(update, context, update.message.from_user, db)
        user_id = update.message.from_user.id
        chat_id = update.message.chat.id
        send_method = update.message.reply_text
    else:
        # Пришло через callback (кнопку "Обновить статистику")
        await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)
        user_id = update.callback_query.from_user.id
        chat_id = update.callback_query.message.chat.id
        send_method = update.callback_query.edit_message_text
        await update.callback_query.answer()

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    is_premium = db.get_user_subscription_status(user_id)

    # Статистика использования за сегодня
    daily_messages = db.get_daily_usage(user_id, "messages")
    daily_images = db.get_daily_usage(user_id, "images")

    # Лимиты
    max_messages = 1000 if is_premium else 5
    max_images = 50 if is_premium else 2

    # Основная статистика
    text = t(user_id, "balance_title", chat_id=chat_id)

    # Статус подписки
    if is_premium:
        subscription = db.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })
        date_str = subscription['expires_at'].strftime('%d.%m.%Y')
        text += t(user_id, "premium_until", chat_id=chat_id, date=date_str)
    else:
        text += t(user_id, "free_plan", chat_id=chat_id)

    # Использование за сегодня
    text += t(user_id, "usage_today", chat_id=chat_id)
    text += t(user_id, "messages_stat", chat_id=chat_id, used=daily_messages, max=max_messages)
    text += t(user_id, "images_stat", chat_id=chat_id, used=daily_images, max=max_images)

    # Кнопки
    keyboard = []
    if not is_premium:
        keyboard.append([InlineKeyboardButton(
            t(user_id, "buy_premium", chat_id=chat_id),
            callback_data="show_premium_plans"
        )])

    keyboard.append([InlineKeyboardButton(
        t(user_id, "refresh_stats", chat_id=chat_id),
        callback_data="refresh_balance"
    )])

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await send_method(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            # Сообщение не изменилось, просто ответим на callback
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer(t(user_id, "stats_up_to_date", chat_id=chat_id))
        else:
            # Другая ошибка - пробрасываем дальше
            raise
