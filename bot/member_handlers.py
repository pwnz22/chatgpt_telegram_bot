# member_handlers.py - Обработчики изменения статуса участников группы
from telegram import Update
from telegram.ext import CallbackContext
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def my_chat_member_handler(update: Update, context: CallbackContext, db):
    """Обработчик изменений статуса бота в чате"""
    chat_member_update = update.my_chat_member

    if not chat_member_update:
        return

    chat = chat_member_update.chat
    new_member = chat_member_update.new_chat_member
    old_member = chat_member_update.old_chat_member
    user_who_changed = chat_member_update.from_user

    # Проверяем, что это группа или супергруппа
    if chat.type not in ["group", "supergroup"]:
        return

    # Проверяем, что изменения касаются нашего бота
    if new_member.user.id != context.bot.id:
        return

    # Бот был добавлен в группу
    if (old_member.status in ["left", "kicked"] and
        new_member.status in ["member", "administrator"]):

        # Регистрируем группу с пользователем, который добавил бота, как администратором
        group_id = chat.id
        group_title = chat.title or "Unknown Group"
        admin_id = user_who_changed.id

        logger.info(f"Bot added to group {group_id} by user {admin_id}")

        # Добавляем группу в базу данных
        if not db.check_if_group_exists(group_id):
            db.add_new_group(group_id, group_title, admin_id=admin_id)
        else:
            # Если группа уже существует, обновляем администратора
            db.set_group_admin_id(group_id, admin_id)

        # Отправляем приветственное сообщение
        try:
            welcome_text = f"👋 Привет! Меня добавил в группу пользователь {user_who_changed.first_name}.\n\n"
            welcome_text += f"🔧 Только {user_who_changed.first_name} может изменять мои настройки в этой группе.\n\n"
            welcome_text += "📝 Чтобы получить ответ, упомяните меня (@{}) или ответьте на моё сообщение.".format(context.bot.username)

            await context.bot.send_message(
                chat_id=group_id,
                text=welcome_text
            )
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    # Бот был удален из группы
    elif (old_member.status in ["member", "administrator"] and
          new_member.status in ["left", "kicked"]):

        logger.info(f"Bot removed from group {chat.id}")

        # Можно добавить логику очистки данных группы или пометки как неактивной
        # db.set_group_attribute(chat.id, "active", False)

async def chat_member_handler(update: Update, context: CallbackContext, db):
    """Обработчик изменений статуса других участников группы"""
    chat_member_update = update.chat_member

    if not chat_member_update:
        return

    # Здесь можно добавить логику для отслеживания изменений статуса других участников
    # Например, если администратор группы покинул группу, можно передать права другому

    pass
