# subscription_handlers.py - Обработчики подписок и платежей
import uuid
from datetime import datetime, timedelta
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

import config
from utils import register_user_if_not_exists

async def show_premium_plans_handle(update: Update, context: CallbackContext, db):
    """Показать тарифные планы"""
    # Определяем откуда пришел запрос - команда или callback
    if update.message:
        # Пришло через команду /premium
        await register_user_if_not_exists(update, context, update.message.from_user, db)
        user_id = update.message.from_user.id
        chat_id = update.message.chat.id
        send_method = update.message.reply_text
    else:
        # Пришло через callback (кнопку)
        await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user, db)
        user_id = update.callback_query.from_user.id
        chat_id = update.callback_query.message.chat.id
        send_method = update.callback_query.edit_message_text
        await update.callback_query.answer()

    is_premium = db.get_user_subscription_status(user_id)

    text = "💎 <b>Premium подписка</b>\n\n"

    if is_premium:
        subscription = db.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })
        text += f"✅ У вас активна подписка до {subscription['expires_at'].strftime('%d.%m.%Y')}\n\n"

    text += "<b>Возможности Premium:</b>\n"
    text += "• 1000 сообщений в день (вместо 5)\n"
    text += "• Доступ к GPT-4 и GPT-4o\n"
    text += "• 50 изображений в день (вместо 2)\n"
    text += "• Приоритетная обработка\n\n"

    text += "<b>Тарифы:</b>\n"
    text += "🗓 Месяц - 25 сомчиков\n"
    text += "📅 Год - 200 сомчиков"

    keyboard = []

    # Показываем кнопки покупки только если токен настроен
    if not is_premium and config.PAYMENT_PROVIDER_TOKEN:
        keyboard.extend([
            [InlineKeyboardButton("🗓 Месяц - 20 TJS", callback_data="buy_premium_monthly")],
            [InlineKeyboardButton("📅 Год - 200 TJS", callback_data="buy_premium_yearly")]
        ])
    elif not config.PAYMENT_PROVIDER_TOKEN:
        text += "\n\n❌ <i>Платежи временно недоступны</i>"

    keyboard.append([InlineKeyboardButton("📊 Мое использование", callback_data="show_my_usage")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_method(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_usage_stats_handle(update: Update, context: CallbackContext, db):
    """Показать статистику использования"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat.id
    is_premium = db.get_user_subscription_status(user_id)

    daily_messages = db.get_daily_usage(user_id, "messages")
    daily_images = db.get_daily_usage(user_id, "images")

    text = "📊 <b>Ваше использование сегодня:</b>\n\n"

    # Сообщения
    max_messages = 1000 if is_premium else 5
    text += f"💬 Сообщения: {daily_messages}/{max_messages}\n"

    # Изображения
    max_images = 50 if is_premium else 2
    text += f"🎨 Изображения: {daily_images}/{max_images}\n\n"

    if is_premium:
        subscription = db.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })
        text += f"💎 Premium до: {subscription['expires_at'].strftime('%d.%m.%Y')}"
    else:
        text += "🆓 Бесплатный план"

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)

async def buy_premium_handle(update: Update, context: CallbackContext, db):
    """Покупка Premium подписки"""
    query = update.callback_query
    await query.answer()

    plan_type = query.data.split("_")[-1]  # monthly или yearly
    user_id = query.from_user.id

    # ВРЕМЕННАЯ ВЕРСИЯ: автоматически активируем Premium без оплаты
    if plan_type == "monthly":
        duration_days = 30
        plan_name = "Premium Monthly"
    else:
        duration_days = 365
        plan_name = "Premium Yearly"

    # Создаем подписку без реального платежа
    subscription_id = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=duration_days)

    subscription = {
        "_id": subscription_id,
        "user_id": user_id,
        "plan": f"premium_{plan_type}",
        "status": "active",
        "created_at": datetime.now(),
        "expires_at": expires_at,
        "payment_id": "test_payment"  # Тестовый платеж
    }

    db.db["subscriptions"].insert_one(subscription)

    # Записываем тестовый платеж
    payment_record = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "amount": 25 if plan_type == "monthly" else 200,
        "currency": "TJS",
        "subscription_id": subscription_id,
        "telegram_payment_id": "test_charge_id",
        "created_at": datetime.now()
    }

    db.db["payments"].insert_one(payment_record)

    # Уведомляем пользователя
    text = f"🎉 <b>Premium активирован!</b>\n\n"
    text += f"План: {plan_name}\n"
    text += f"Действует до: {expires_at.strftime('%d.%m.%Y')}\n\n"
    text += "✨ <i>Тестовая активация - платежи временно отключены</i>\n\n"
    text += "Теперь вам доступны все Premium функции!"

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)

async def pre_checkout_callback(update: Update, context: CallbackContext, db):
    """Проверка перед оплатой"""
    query = update.pre_checkout_query

    if query.invoice_payload in ["premium_monthly", "premium_yearly"]:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка платежа")

async def successful_payment_callback(update: Update, context: CallbackContext, db):
    """Обработка успешного платежа"""
    payment = update.message.successful_payment
    user_id = update.effective_user.id

    # Определяем тип подписки
    duration_days = 30 if payment.invoice_payload == "premium_monthly" else 365

    # Создаем подписку
    subscription_id = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=duration_days)

    subscription = {
        "_id": subscription_id,
        "user_id": user_id,
        "plan": payment.invoice_payload,
        "status": "active",
        "created_at": datetime.now(),
        "expires_at": expires_at,
        "payment_id": payment.telegram_payment_charge_id
    }

    db.db["subscriptions"].insert_one(subscription)

    # Записываем платеж
    payment_record = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "amount": payment.total_amount / 100,
        "currency": payment.currency,
        "subscription_id": subscription_id,
        "telegram_payment_id": payment.telegram_payment_charge_id,
        "created_at": datetime.now()
    }

    db.db["payments"].insert_one(payment_record)

    # Уведомляем пользователя
    text = f"🎉 <b>Premium активирован!</b>\n\n"
    text += f"План: {payment.invoice_payload.replace('_', ' ').title()}\n"
    text += f"Действует до: {expires_at.strftime('%d.%m.%Y')}\n\n"
    text += "Теперь вам доступны все Premium функции!"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
