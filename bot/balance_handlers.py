# balance_handlers.py - Обработчики баланса и статистики с локализацией
from datetime import datetime
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from utils import register_user_if_not_exists
from localization import t

async def show_balance_handle(update: Update, context: CallbackContext, db):
    """Показать баланс и статистику с учетом подписки"""

    # Определяем откуда пришел запрос - команда или callback
    if update.message:
        # Пришло через команду /balance
        await register_user_if_not_exists(update, context, update.message.from_user, db)
        user_id = update.message.from_user.id
        send_method = update.message.reply_text
    else:
        # Пришло через callback (кнопку "Обновить статистику")
        await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)
        user_id = update.callback_query.from_user.id
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
    text = t(user_id, "balance_title")

    # Статус подписки
    if is_premium:
        subscription = db.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })
        date_str = subscription['expires_at'].strftime('%d.%m.%Y')
        text += t(user_id, "premium_until", date=date_str)
    else:
        text += t(user_id, "free_plan")

    # Использование за сегодня
    text += t(user_id, "usage_today")
    text += t(user_id, "messages_stat", used=daily_messages, max=max_messages)
    text += t(user_id, "images_stat", used=daily_images, max=max_images)

    # Общая статистика (упрощенная версия)
    # n_used_tokens_dict = db.get_user_attribute(user_id, "n_used_tokens")
    # n_generated_images = db.get_user_attribute(user_id, "n_generated_images")

    # total_tokens = 0
    # for model_data in n_used_tokens_dict.values():
    #     if isinstance(model_data, dict):
    #         total_tokens += model_data.get("n_input_tokens", 0) + model_data.get("n_output_tokens", 0)

    # text += t(user_id, "total_tokens", tokens=total_tokens)
    # text += t(user_id, "total_images", images=n_generated_images)

    # Кнопки
    keyboard = []
    if not is_premium:
        keyboard.append([InlineKeyboardButton(
            t(user_id, "buy_premium"),
            callback_data="show_premium_plans"
        )])

    keyboard.append([InlineKeyboardButton(
        t(user_id, "refresh_stats"),
        callback_data="refresh_balance"
    )])

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await send_method(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            # Сообщение не изменилось, просто ответим на callback
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer(t(user_id, "stats_up_to_date"))
        else:
            # Другая ошибка - пробрасываем дальше
            raise
