# bot.py - Главный файл бота с системой локализации
import logging
import traceback
import html
import json
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    AIORateLimiter,
    filters,
    ChatMemberHandler
)
from telegram.constants import ParseMode

# Импорты модулей
import config
import database
from utils import split_text_into_chunks

# Инициализация локализации
from localization import init_localization, TEXTS

# Импорты обработчиков
from basic_handlers import (
    start_handle,
    help_handle,
    help_group_chat_handle,
    new_dialog_handle,
    show_chat_modes_handle,
    show_chat_modes_callback_handle,
    set_chat_mode_handle,
    settings_handle,
    set_settings_handle
)

from message_handlers import (
    message_handle,
    voice_message_handle,
    unsupport_message_handle,
    retry_handle,
    cancel_handle
)

from balance_handlers import show_balance_handle

from subscription_handlers import (
    show_premium_plans_handle,
    show_usage_stats_handle,
    buy_premium_handle,
    pre_checkout_callback,
    successful_payment_callback
)

# Импорт обработчиков языков
from language_handlers import (
    language_handle,
    set_language_handle,
    language_info_callback_handle,
    back_to_language_callback_handle
)

from member_handlers import my_chat_member_handler, chat_member_handler

# Setup
db = database.Database()
logger = logging.getLogger(__name__)

# Инициализация локализации
localization = init_localization(db)

async def error_handle(update: Update, context: CallbackContext) -> None:
    """Обработчик ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    try:
        # collect error message
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
            "</pre>\n\n"
            f"<pre>{html.escape(tb_string)}</pre>"
        )

        # split text into multiple messages due to 4096 character limit
        for message_chunk in split_text_into_chunks(message, 4096):
            try:
                await context.bot.send_message(update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML)
            except:
                # answer has invalid characters, so we send it without parse_mode
                await context.bot.send_message(update.effective_chat.id, message_chunk)
    except:
        await context.bot.send_message(update.effective_chat.id, "Some error in error handler")

async def post_init(application: Application):
    """Инициализация команд бота с локализацией"""

    # Получаем команды из системы локализации
    def get_commands_for_language(lang_code):
        texts = TEXTS.get(lang_code, TEXTS["en"])
        return [
            BotCommand("/new", texts["command_new"]),
            BotCommand("/mode", texts["command_mode"]),
            BotCommand("/retry", texts["command_retry"]),
            BotCommand("/balance", texts["command_balance"]),
            BotCommand("/premium", texts["command_premium"]),
            BotCommand("/settings", texts["command_settings"]),
            BotCommand("/lang", texts["command_lang"]),
            BotCommand("/help", texts["command_help"]),
        ]

    # Устанавливаем команды для разных языков
    try:
        en_commands = get_commands_for_language("en")
        ru_commands = get_commands_for_language("ru")

        await application.bot.set_my_commands(en_commands, language_code="en")
        await application.bot.set_my_commands(ru_commands, language_code="ru")

        # Команды по умолчанию (для пользователей без установленного языка)
        await application.bot.set_my_commands(en_commands)

        logger.info("Bot commands set successfully for multiple languages")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")
        # Устанавливаем хотя бы базовые команды
        await application.bot.set_my_commands(get_commands_for_language("en"))

def run_bot() -> None:
    """Запуск бота"""
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .build()
    )

    # Фильтры пользователей
    user_filter = filters.ALL
    if len(config.allowed_telegram_usernames) > 0:
        usernames = [x for x in config.allowed_telegram_usernames if isinstance(x, str)]
        any_ids = [x for x in config.allowed_telegram_usernames if isinstance(x, int)]
        user_ids = [x for x in any_ids if x > 0]
        group_ids = [x for x in any_ids if x < 0]
        user_filter = filters.User(username=usernames) | filters.User(user_id=user_ids) | filters.Chat(chat_id=group_ids)

    application.add_handler(ChatMemberHandler(lambda u, c: my_chat_member_handler(u, c, db), ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(lambda u, c: chat_member_handler(u, c, db), ChatMemberHandler.CHAT_MEMBER))

    # Основные обработчики команд
    application.add_handler(CommandHandler("start", lambda u, c: start_handle(u, c, db), filters=user_filter))
    application.add_handler(CommandHandler("help", lambda u, c: help_handle(u, c, db), filters=user_filter))
    application.add_handler(CommandHandler("help_group_chat", lambda u, c: help_group_chat_handle(u, c, db), filters=user_filter))
    application.add_handler(CommandHandler("new", lambda u, c: new_dialog_handle(u, c, db), filters=user_filter))
    application.add_handler(CommandHandler("retry", lambda u, c: retry_handle(u, c, db), filters=user_filter))
    application.add_handler(CommandHandler("cancel", lambda u, c: cancel_handle(u, c, db), filters=user_filter))

    # Обработчики языков
    application.add_handler(CommandHandler("lang", lambda u, c: language_handle(u, c, db), filters=user_filter))
    application.add_handler(CallbackQueryHandler(lambda u, c: set_language_handle(u, c, db), pattern="^set_language"))
    application.add_handler(CallbackQueryHandler(lambda u, c: language_info_callback_handle(u, c, db), pattern="^language_info"))
    application.add_handler(CallbackQueryHandler(lambda u, c: back_to_language_callback_handle(u, c, db), pattern="^back_to_language_selection"))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, lambda u, c: message_handle(u, c, db)))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND & user_filter, lambda u, c: message_handle(u, c, db)))
    application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND & user_filter, lambda u, c: unsupport_message_handle(u, c, db)))
    application.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND & user_filter, lambda u, c: unsupport_message_handle(u, c, db)))
    application.add_handler(MessageHandler(filters.VOICE & user_filter, lambda u, c: voice_message_handle(u, c, db)))

    # Обработчики режимов чата
    application.add_handler(CommandHandler("mode", lambda u, c: show_chat_modes_handle(u, c, db), filters=user_filter))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_chat_modes_callback_handle(u, c, db), pattern="^show_chat_modes"))
    application.add_handler(CallbackQueryHandler(lambda u, c: set_chat_mode_handle(u, c, db), pattern="^set_chat_mode"))

    # Обработчики настроек
    application.add_handler(CommandHandler("settings", lambda u, c: settings_handle(u, c, db), filters=user_filter))
    application.add_handler(CallbackQueryHandler(lambda u, c: set_settings_handle(u, c, db), pattern="^set_settings"))

    # Обработчики баланса
    application.add_handler(CommandHandler("balance", lambda u, c: show_balance_handle(u, c, db), filters=user_filter))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_balance_handle(u, c, db), pattern="^refresh_balance"))

    # Обработчики Premium подписок
    application.add_handler(CommandHandler("premium", lambda u, c: show_premium_plans_handle(u, c, db), filters=user_filter))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_premium_plans_handle(u, c, db), pattern="^show_premium_plans"))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_usage_stats_handle(u, c, db), pattern="^show_my_usage"))
    application.add_handler(CallbackQueryHandler(lambda u, c: buy_premium_handle(u, c, db), pattern="^buy_premium"))

    # Обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(lambda u, c: pre_checkout_callback(u, c, db)))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, lambda u, c: successful_payment_callback(u, c, db)))

    # Обработчик ошибок
    application.add_error_handler(error_handle)

    # Запуск бота
    application.run_polling()


if __name__ == "__main__":
    run_bot()
