# localization.py - Система локализации с поддержкой групп
from typing import Dict, Any

# Тексты на разных языках
TEXTS = {
    "en": {
        # Команды и помощь
        "help_message": """Commands:
⚪ /retry – Regenerate last bot answer
⚪ /new – Start new dialog
⚪ /mode – Select chat mode
⚪ /settings – Show settings
⚪ /balance – Show balance
⚪ /premium – Premium subscription
⚪ /help – Show help
⚪ /lang – Change language

🎨 Generate images from text prompts in <b>👩‍🎨 Artist</b> /mode
👥 Add bot to <b>group chat</b>: /help_group_chat
🎤 You can send <b>Voice Messages</b> instead of text

💎 <b>Premium features:</b>
• 1000 messages/day (vs 5 free)
• GPT-4 and GPT-4o access
• 50 images/day (vs 2 free)""",

        "help_group_chat": """You can add bot to any <b>group chat</b> to help and entertain its participants!

Instructions (see <b>video</b> below):
1. Add the bot to the group chat
2. Make it an <b>admin</b>, so that it can see messages (all other rights can be restricted)
3. You're awesome!

To get a reply from the bot in the chat – @ <b>tag</b> it or <b>reply</b> to its message.
For example: "{bot_username} write a poem about Telegram" """,

        "start_greeting": "Hi! I'm <b>ChatGPT</b> bot implemented with OpenAI API 🤖\n\n",

        # Лимиты и ошибки
        "daily_limit_exceeded": "🚫 <b>Daily limit exceeded!</b>\n\n",
        "premium_limit_text": "Premium: {max_messages} messages per day\nUsed: {used_messages}\n\nLimit will reset tomorrow at 00:00",
        "free_limit_text": "Free: {max_messages} messages per day\nUsed: {used_messages}\n\n💎 Get Premium for 1000 messages per day!",
        "image_limit_exceeded": "🚫 Image limit exceeded!\n\n",
        "premium_image_limit": "Premium: {max_images} images per day\nUsed: {used_images}",
        "free_image_limit": "Free: {max_images} images per day\nUsed: {used_images}\n\n💎 Premium: 50 images per day!",

        # Модели и доступ
        "gpt4_premium_only": "🔒 GPT-4 is available only in Premium. Switched to GPT-3.5-turbo.",
        "vision_model_required": "🥲 Images processing is only available for <b>gpt-4-vision-preview</b> and <b>gpt-4o</b> model. Please change your settings in /settings",
        "unsupported_content": "🥲 Your request <b>doesn't comply</b> with OpenAI's usage policies.\nWhat did you write there, huh?",

        # Сообщения и диалоги
        "empty_message": "🥲 You sent <b>empty message</b>. Please, try again!",
        "wait_previous": "⏳ Please <b>wait</b> for a reply to the previous message\nOr you can /cancel it",
        "nothing_to_cancel": "<i>Nothing to cancel...</i>",
        "nothing_to_retry": "No message to retry 🤷‍♂️",
        "new_dialog_started": "Starting new dialog ✅",
        "dialog_timeout": "Starting new dialog due to timeout (<b>{mode_name}</b> mode) ✅",
        "message_removed": "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context.\n Send /new command to start new dialog",
        "messages_removed": "✍️ <i>Note:</i> Your current dialog is too long, so <b>{count} first messages</b> were removed from the context.\n Send /new command to start new dialog",
        "editing_not_supported": "🥲 Unfortunately, message <b>editing</b> is not supported",
        "unsupported_files": "I don't know how to read files or videos. Send the picture in normal mode (Quick Mode).",
        "voice_transcription": "🎤: <i>{text}</i>",
        "canceled": "✅ Canceled",

        # Режимы чата
        "select_chat_mode": "Select <b>chat mode</b> ({count} modes available):",
        "select_chat_mode_group": "Select <b>chat mode for this group</b> ({count} modes available):",
        "chat_mode_set_for_group": "✅ Chat mode <b>{mode_name}</b> set for this group",

        # Настройки
        "select_model": "\nSelect <b>model</b>:",

        # Баланс и статистика
        "balance_title": "💳 <b>Your balance and statistics</b>\n\n",
        "premium_until": "💎 <b>Premium until:</b> {date}\n\n",
        "free_plan": "🆓 <b>Free plan</b>\n\n",
        "usage_today": "📊 <b>Usage today:</b>\n",
        "messages_stat": "💬 Messages: {used}/{max}\n",
        "images_stat": "🎨 Images: {used}/{max}\n\n",
        "total_tokens": "🔤 <b>Total tokens:</b> {tokens}\n",
        "total_images": "🎨 <b>Total images:</b> {images}",
        "stats_up_to_date": "✅ Statistics up to date",

        # Premium и подписки
        "premium_subscription": "💎 <b>Premium subscription</b>\n\n",
        "premium_active_until": "✅ You have an active subscription until {date}\n\n",
        "premium_features": """<b>Premium features:</b>
• 1000 messages per day (instead of 5)
• Access to GPT-4 and GPT-4o
• 50 images per day (instead of 2)
• Priority processing\n\n""",
        "premium_pricing": """<b>Pricing:</b>
🗓 Month - 25 TJS
📅 Year - 200 TJS""",
        "payments_unavailable": "\n\n❌ <i>Payments temporarily unavailable</i>",
        "premium_activated": "🎉 <b>Premium activated!</b>\n\n",
        "plan_info": "Plan: {plan}\nValid until: {date}\n\n",
        "test_activation": "✨ <i>Test activation - payments temporarily disabled</i>\n\n",
        "premium_access": "Now you have access to all Premium features!",
        "payment_error": "Payment error",

        # Использование
        "usage_stats_title": "📊 <b>Your usage today:</b>\n\n",
        "premium_until_stat": "💎 Premium until: {date}",
        "free_plan_stat": "🆓 Free plan",

        # Кнопки
        "buy_premium": "💎 Buy Premium",
        "my_usage": "📊 My usage",
        "refresh_stats": "📊 Refresh statistics",
        "month_plan": "🗓 Month - 20 TJS",
        "year_plan": "📅 Year - 200 TJS",

        # Языки
        "language_changed": "✅ Language changed to English",
        "select_language": "🌐 <b>Select language:</b>",
        "english": "🇺🇸 English",
        "russian": "🇷🇺 Русский",
        "language_info_button": "ℹ️ Current language affects ChatGPT responses",
        "language_already_set": "✅ <b>Language already set: English</b>\n\n💬 ChatGPT responds in English\n🔧 Bot interface in English\n\n💡 <i>You can ask any question right away!</i>",
        "language_change_notification": "✅ <b>Language changed to English</b>\n\n💬 <b>Important change:</b> Now ChatGPT will automatically respond in English, even if you write in Russian or any other language!\n\n🔄 <b>What this means:</b>\n• You can write in any language\n• ChatGPT will always respond in English\n• Bot interface is also in English\n\n🆕 Started new dialog with English language settings.\n\n💡 <i>You can ask any question right away to test it!</i>",
        "language_info_text": "ℹ️ <b>Language Settings Information</b>\n\n🌐 <b>What language setting affects:</b>\n• Bot interface (buttons, menus, notifications)\n• ChatGPT responses to your questions\n• System messages and errors\n\n🤖 <b>How ChatGPT works:</b>\n• Automatically responds in selected language\n• Understands questions in any language\n• Translates response to target language\n\n⚙️ <b>Current settings:</b>\n• Current language: English 🇺🇸\n• Change: /lang\n\n🔄 <b>Language switching:</b>\nWhen changing language, a new dialog automatically starts with updated settings.",
        "back_to_language": "🔙 Back to language selection",
        "how_language_works": "ℹ️ How do language settings work?",
    },

    "ru": {
        # Команды и помощь
        "help_message": """Команды:
⚪ /retry – Повторить последний ответ бота
⚪ /new – Начать новый диалог
⚪ /mode – Выбрать режим чата
⚪ /settings – Показать настройки
⚪ /balance – Показать баланс
⚪ /premium – Premium подписка
⚪ /help – Показать помощь
⚪ /lang – Изменить язык

🎨 Генерируйте изображения из текста в режиме <b>👩‍🎨 Художник</b> /mode
👥 Добавьте бота в <b>групповой чат</b>: /help_group_chat
🎤 Вы можете отправлять <b>голосовые сообщения</b> вместо текста

💎 <b>Возможности Premium:</b>
• 1000 сообщений в день (против 5 бесплатных)
• Доступ к GPT-4 и GPT-4o
• 50 изображений в день (против 2 бесплатных)""",

        "help_group_chat": """Вы можете добавить бота в любой <b>групповой чат</b>, чтобы помочь и развлечь его участников!

Инструкции (см. <b>видео</b> ниже):
1. Добавьте бота в групповой чат
2. Сделайте его <b>администратором</b>, чтобы он мог видеть сообщения (все остальные права можно ограничить)
3. Вы великолепны!

Чтобы получить ответ от бота в чате – @ <b>упомяните</b> его или <b>ответьте</b> на его сообщение.
Например: "{bot_username} напиши стихотворение о Telegram" """,

        "start_greeting": "Привет! Я бот <b>ChatGPT</b>, реализованный с помощью OpenAI API 🤖\n\n",

        # Лимиты и ошибки
        "daily_limit_exceeded": "🚫 <b>Дневной лимит исчерпан!</b>\n\n",
        "premium_limit_text": "Premium: {max_messages} сообщений в день\nИспользовано: {used_messages}\n\nЛимит обновится завтра в 00:00",
        "free_limit_text": "Бесплатно: {max_messages} сообщений в день\nИспользовано: {used_messages}\n\n💎 Оформите Premium для 1000 сообщений в день!",
        "image_limit_exceeded": "🚫 Лимит изображений исчерпан!\n\n",
        "premium_image_limit": "Premium: {max_images} изображений в день\nИспользовано: {used_images}",
        "free_image_limit": "Бесплатно: {max_images} изображений в день\nИспользовано: {used_images}\n\n💎 Premium: 50 изображений в день!",

        # Модели и доступ
        "gpt4_premium_only": "🔒 GPT-4 доступен только в Premium. Переключено на GPT-3.5-turbo.",
        "vision_model_required": "🥲 Обработка изображений доступна только для моделей <b>gpt-4-vision-preview</b> и <b>gpt-4o</b>. Пожалуйста, измените настройки в /settings",
        "unsupported_content": "🥲 Ваш запрос <b>не соответствует</b> политикам использования OpenAI.\nЧто вы там написали?",

        # Сообщения и диалоги
        "empty_message": "🥲 Вы отправили <b>пустое сообщение</b>. Пожалуйста, попробуйте еще раз!",
        "wait_previous": "⏳ Пожалуйста, <b>подождите</b> ответа на предыдущее сообщение\nИли вы можете /cancel отменить его",
        "nothing_to_cancel": "<i>Нечего отменять...</i>",
        "nothing_to_retry": "Нет сообщения для повтора 🤷‍♂️",
        "new_dialog_started": "Начинаем новый диалог ✅",
        "dialog_timeout": "Начинаем новый диалог из-за таймаута (режим <b>{mode_name}</b>) ✅",
        "message_removed": "✍️ <i>Примечание:</i> Ваш текущий диалог слишком длинный, поэтому ваше <b>первое сообщение</b> было удалено из контекста.\n Отправьте команду /new, чтобы начать новый диалог",
        "messages_removed": "✍️ <i>Примечание:</i> Ваш текущий диалог слишком длинный, поэтому <b>{count} первых сообщений</b> были удалены из контекста.\n Отправьте команду /new, чтобы начать новый диалог",
        "editing_not_supported": "🥲 К сожалению, <b>редактирование</b> сообщений не поддерживается",
        "unsupported_files": "Я не умею читать файлы или видео. Отправьте картинку в обычном режиме (Быстрый режим).",
        "voice_transcription": "🎤: <i>{text}</i>",
        "canceled": "✅ Отменено",

        # Режимы чата
        "select_chat_mode": "Выберите <b>режим чата</b> (доступно {count} режимов):",
        "select_chat_mode_group": "Выберите <b>режим чата для этой группы</b> (доступно {count} режимов):",
        "chat_mode_set_for_group": "✅ Режим чата <b>{mode_name}</b> установлен для этой группы",

        # Настройки
        "select_model": "\nВыберите <b>модель</b>:",

        # Баланс и статистика
        "balance_title": "💳 <b>Ваш баланс и статистика</b>\n\n",
        "premium_until": "💎 <b>Premium до:</b> {date}\n\n",
        "free_plan": "🆓 <b>Бесплатный план</b>\n\n",
        "usage_today": "📊 <b>Использование сегодня:</b>\n",
        "messages_stat": "💬 Сообщения: {used}/{max}\n",
        "images_stat": "🎨 Изображения: {used}/{max}\n\n",
        "total_tokens": "🔤 <b>Всего токенов:</b> {tokens}\n",
        "total_images": "🎨 <b>Всего изображений:</b> {images}",
        "stats_up_to_date": "✅ Статистика актуальна",

        # Premium и подписки
        "premium_subscription": "💎 <b>Premium подписка</b>\n\n",
        "premium_active_until": "✅ У вас активна подписка до {date}\n\n",
        "premium_features": """<b>Возможности Premium:</b>
• 1000 сообщений в день (вместо 5)
• Доступ к GPT-4 и GPT-4o
• 50 изображений в день (вместо 2)
• Приоритетная обработка\n\n""",
        "premium_pricing": """<b>Тарифы:</b>
🗓 Месяц - 25 сомони
📅 Год - 200 сомони""",
        "payments_unavailable": "\n\n❌ <i>Платежи временно недоступны</i>",
        "premium_activated": "🎉 <b>Premium активирован!</b>\n\n",
        "plan_info": "План: {plan}\nДействует до: {date}\n\n",
        "test_activation": "✨ <i>Тестовая активация - платежи временно отключены</i>\n\n",
        "premium_access": "Теперь вам доступны все Premium функции!",
        "payment_error": "Ошибка платежа",

        # Использование
        "usage_stats_title": "📊 <b>Ваше использование сегодня:</b>\n\n",
        "premium_until_stat": "💎 Premium до: {date}",
        "free_plan_stat": "🆓 Бесплатный план",

        # Кнопки
        "buy_premium": "💎 Купить Premium",
        "my_usage": "📊 Мое использование",
        "refresh_stats": "📊 Обновить статистику",
        "month_plan": "🗓 Месяц - 20 TJS",
        "year_plan": "📅 Год - 200 TJS",

        # Языки
        "language_changed": "✅ Язык изменен на русский",
        "select_language": "🌐 <b>Выберите язык:</b>",
        "english": "🇺🇸 English",
        "russian": "🇷🇺 Русский",
        "language_info_button": "ℹ️ Текущий язык влияет на ответы ChatGPT",
        "language_already_set": "✅ <b>Язык уже установлен: Русский</b>\n\n💬 ChatGPT отвечает на русском языке\n🔧 Интерфейс бота на русском\n\n💡 <i>Можете сразу задать любой вопрос!</i>",
        "language_change_notification": "✅ <b>Язык изменен на Русский</b>\n\n💬 <b>Важное изменение:</b> Теперь ChatGPT будет автоматически отвечать на русском языке, даже если вы напишете на английском или другом языке!\n\n🔄 <b>Что это означает:</b>\n• Вы можете писать на любом языке\n• ChatGPT всегда ответит на русском\n• Интерфейс бота тоже на русском\n\n🆕 Начат новый диалог с русскоязычными настройками.\n\n💡 <i>Можете сразу задать любой вопрос для проверки!</i>",
        "language_info_text": "ℹ️ <b>Информация о языковых настройках</b>\n\n🌐 <b>Что влияет на выбор языка:</b>\n• Интерфейс бота (кнопки, меню, уведомления)\n• Ответы ChatGPT на ваши вопросы\n• Системные сообщения и ошибки\n\n🤖 <b>Как работает ChatGPT:</b>\n• Автоматически отвечает на выбранном языке\n• Понимает вопросы на любом языке\n• Переводит ответ на нужный язык\n\n⚙️ <b>Настройки:</b>\n• Текущий язык: Русский 🇷🇺\n• Изменить: /lang\n\n🔄 <b>Смена языка:</b>\nПри смене языка автоматически начинается новый диалог с обновленными настройками.",
        "back_to_language": "🔙 Назад к выбору языка",
        "how_language_works": "ℹ️ Как работают языковые настройки?",
    }
}

class Localization:
    def __init__(self, db):
        self.db = db
        self.default_language = "en"

    def get_user_language(self, user_id: int) -> str:
        """Получить язык пользователя"""
        try:
            lang = self.db.get_user_attribute(user_id, "language")
            return lang if lang in TEXTS else self.default_language
        except:
            return self.default_language

    def set_user_language(self, user_id: int, language: str):
        """Установить язык пользователя"""
        if language in TEXTS:
            self.db.set_user_attribute(user_id, "language", language)

    def get_text(self, user_id: int, key: str, **kwargs) -> str:
        """Получить локализованный текст"""
        language = self.get_user_language(user_id)

        try:
            text = TEXTS[language][key]
            # Подстановка переменных
            if kwargs:
                text = text.format(**kwargs)
            return text
        except KeyError:
            # Если ключ не найден, пробуем английский
            try:
                text = TEXTS[self.default_language][key]
                if kwargs:
                    text = text.format(**kwargs)
                return text
            except KeyError:
                return f"[Missing text: {key}]"

    def get_available_languages(self) -> Dict[str, str]:
        """Получить список доступных языков"""
        return {
            "en": "🇺🇸 English",
            "ru": "🇷🇺 Русский"
        }

# Глобальный экземпляр (будет инициализирован в bot.py)
localization = None

def init_localization(db):
    """Инициализация системы локализации"""
    global localization
    localization = Localization(db)
    return localization

def t(user_id: int, key: str, **kwargs) -> str:
    """Быстрая функция для получения текста"""
    if localization is None:
        return f"[Localization not initialized: {key}]"
    return localization.get_text(user_id, key, **kwargs)
