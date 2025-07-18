# message_handlers.py - С поддержкой групп и автоматическим определением языка
import io
import asyncio
import base64
from datetime import datetime
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

import config
import openai_utils
from utils import register_user_if_not_exists, register_group_if_not_exists
from localization import t

user_semaphores = {}
user_tasks = {}

def get_language_instruction(user_id: int, chat_id: int, db) -> str:
    """Получить инструкцию о языке для ChatGPT с поддержкой групп"""
    # Определяем источник языка
    if chat_id < 0:  # Группа
        user_language = db.get_group_attribute(chat_id, "language") or "en"
    else:  # Личный чат
        user_language = db.get_user_attribute(user_id, "language") or "en"

    language_instructions = {
        "ru": "Отвечай ТОЛЬКО на русском языке. Будь дружелюбным и полезным помощником. Все твои ответы должны быть на русском языке, независимо от языка вопроса.",
        "en": "Respond ONLY in English. Be a friendly and helpful assistant. All your responses should be in English, regardless of the question's language.",
    }

    return language_instructions.get(user_language, language_instructions["en"])

def enhance_dialog_messages_with_language(dialog_messages: list, user_id: int, chat_id: int, db) -> list:
    """Добавить языковую инструкцию к диалогу с поддержкой групп"""
    if not dialog_messages:
        dialog_messages = []

    language_instruction = get_language_instruction(user_id, chat_id, db)

    # Создаем копию сообщений
    enhanced_messages = []

    # Добавляем языковую инструкцию как первое системное сообщение
    # Определяем язык для ответа бота
    if chat_id < 0:  # Группа
        bot_language = db.get_group_attribute(chat_id, "language") or "en"
    else:  # Личный чат
        bot_language = db.get_user_attribute(user_id, "language") or "en"

    enhanced_messages.append({
        "user": [{"type": "text", "text": f"SYSTEM: {language_instruction}"}],
        "bot": "Понял, буду отвечать на выбранном языке." if bot_language == "ru" else "Understood, I will respond in the selected language.",
        "date": datetime.now()
    })

    # Добавляем остальные сообщения
    enhanced_messages.extend(dialog_messages)

    return enhanced_messages

async def is_bot_mentioned(update: Update, context: CallbackContext):
    try:
        message = update.message

        if message.chat.type == "private":
            return True

        if message.text is not None and ("@" + context.bot.username) in message.text:
            return True

        if message.reply_to_message is not None:
            if message.reply_to_message.from_user.id == context.bot.id:
                return True
    except:
        return True
    else:
        return False

async def is_previous_message_not_answered_yet(update: Update, context: CallbackContext, db):
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    # Инициализация семафора если не существует
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(1)

    if user_semaphores[user_id].locked():
        text = t(user_id, "wait_previous", chat_id=chat_id)
        await update.message.reply_text(text, reply_to_message_id=update.message.id, parse_mode=ParseMode.HTML)
        return True
    else:
        return False

async def check_daily_limits(update: Update, user_id: int, db) -> bool:
    """Проверить дневные лимиты пользователя"""
    is_premium = db.get_user_subscription_status(user_id)
    daily_messages = db.get_daily_usage(user_id, "messages")
    max_daily_messages = 1000 if is_premium else 5
    chat_id = update.message.chat.id

    if daily_messages >= max_daily_messages:
        limit_text = t(user_id, "daily_limit_exceeded", chat_id=chat_id)

        if is_premium:
            limit_text += t(user_id, "premium_limit_text", chat_id=chat_id,
                          max_messages=max_daily_messages,
                          used_messages=daily_messages)
        else:
            limit_text += t(user_id, "free_limit_text", chat_id=chat_id,
                          max_messages=max_daily_messages,
                          used_messages=daily_messages)

            keyboard = [[
                InlineKeyboardButton(t(user_id, "buy_premium", chat_id=chat_id), callback_data="show_premium_plans")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                limit_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            return False

        await update.message.reply_text(limit_text, parse_mode=ParseMode.HTML)
        return False

    return True

async def check_image_limits(update: Update, user_id: int, db) -> bool:
    """Проверить лимиты изображений"""
    is_premium = db.get_user_subscription_status(user_id)
    daily_images = db.get_daily_usage(user_id, "images")
    max_daily_images = 50 if is_premium else 2
    chat_id = update.message.chat.id

    if daily_images >= max_daily_images:
        limit_text = t(user_id, "image_limit_exceeded", chat_id=chat_id)

        if is_premium:
            limit_text += t(user_id, "premium_image_limit", chat_id=chat_id,
                          max_images=max_daily_images,
                          used_images=daily_images)
        else:
            limit_text += t(user_id, "free_image_limit", chat_id=chat_id,
                          max_images=max_daily_images,
                          used_images=daily_images)

            keyboard = [[InlineKeyboardButton(t(user_id, "buy_premium", chat_id=chat_id), callback_data="show_premium_plans")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(limit_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            return False

        await update.message.reply_text(limit_text, parse_mode=ParseMode.HTML)
        return False

    return True

async def check_model_access(update: Update, user_id: int, chat_id: int, db) -> str:
    """Проверить доступ к модели и вернуть допустимую модель с поддержкой групп"""
    # Получаем модель из настроек группы или пользователя
    if chat_id < 0:  # Группа
        current_model = db.get_group_attribute(chat_id, "current_model")
    else:  # Личный чат
        current_model = db.get_user_attribute(user_id, "current_model")

    # Используем premium_models из конфигурации
    is_premium = db.get_user_subscription_status(user_id)

    if current_model in config.premium_models and not is_premium:
        await update.message.reply_text(
            t(user_id, "gpt4_premium_only", chat_id=chat_id),
            parse_mode=ParseMode.HTML
        )

        # Устанавливаем fallback модель
        fallback_model = config.default_model
        if chat_id < 0:  # Группа
            db.set_group_attribute(chat_id, "current_model", fallback_model)
        else:  # Личный чат
            db.set_user_attribute(user_id, "current_model", fallback_model)

        return fallback_model

    return current_model

async def message_handle(update: Update, context: CallbackContext, db, message=None, use_new_dialog_timeout=True):
    """Обработка сообщений с проверкой подписки и лимитов"""

    # Проверка упоминания бота
    if not await is_bot_mentioned(update, context):
        return

    if update.edited_message is not None:
        await edited_message_handle(update, context, db)
        return

    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    # Регистрируем группу если нужно
    from utils import register_group_if_not_exists
    await register_group_if_not_exists(update, context, db)

    # Инициализация семафора
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(1)

    # ПРОВЕРКА ЛИМИТОВ
    if not await check_daily_limits(update, user_id, db):
        return

    if await is_previous_message_not_answered_yet(update, context, db):
        return

    # Проверка доступа к моделям
    current_model = await check_model_access(update, user_id, chat_id, db)

    # Увеличиваем счетчик использования
    db.add_daily_usage(user_id, "messages", 1)

    # Получаем chat_mode из группы или пользователя
    if chat_id < 0:  # Группа
        chat_mode = db.get_group_attribute(chat_id, "current_chat_mode")
    else:  # Личный чат
        chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    _message = message or update.message.text

    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()

    if chat_mode == "artist":
        # Проверка лимита изображений
        if not await check_image_limits(update, user_id, db):
            return

        await generate_image_handle_with_limits(update, context, db, message=message)
        return

    # Остальная логика как в оригинальном message_handle
    async def message_handle_fn():
        # new dialog timeout
        if use_new_dialog_timeout:
            if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
                db.start_new_dialog(user_id)

                # Получаем локализованное welcome сообщение напрямую
                user_language = db.get_user_attribute(user_id, "language") or "en"
                mode_name = config.chat_modes[chat_mode]['name']

                # Отправляем уведомление о таймауте
                timeout_text = t(user_id, "dialog_timeout", chat_id=chat_id, mode_name=mode_name)
                await update.message.reply_text(timeout_text, parse_mode=ParseMode.HTML)

                # Получаем и отправляем локализованное welcome сообщение
                welcome_message = config.chat_modes[chat_mode]["welcome_message"]

                if isinstance(welcome_message, dict):
                    welcome_text = welcome_message.get(user_language, welcome_message.get("en", "Welcome!"))
                else:
                    welcome_text = welcome_message

                await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

        db.set_user_attribute(user_id, "last_interaction", datetime.now())

        # in case of CancelledError
        n_input_tokens, n_output_tokens = 0, 0

        try:
            # send placeholder message to user
            placeholder_message = await update.message.reply_text("...")

            # send typing action
            await update.message.chat.send_action(action="typing")

            if _message is None or len(_message) == 0:
                await update.message.reply_text(t(user_id, "empty_message", chat_id=chat_id), parse_mode=ParseMode.HTML)
                return

            # ВАЖНО: Добавляем языковую инструкцию к диалогу
            dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
            enhanced_dialog_messages = enhance_dialog_messages_with_language(dialog_messages, user_id, chat_id, db)

            parse_mode = {
                "html": ParseMode.HTML,
                "markdown": ParseMode.MARKDOWN
            }[config.chat_modes[chat_mode]["parse_mode"]]

            chatgpt_instance = openai_utils.ChatGPT(model=current_model)
            if config.enable_message_streaming:
                gen = chatgpt_instance.send_message_stream(_message, dialog_messages=enhanced_dialog_messages, chat_mode=chat_mode)
            else:
                answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = await chatgpt_instance.send_message(
                    _message,
                    dialog_messages=enhanced_dialog_messages,
                    chat_mode=chat_mode
                )

                async def fake_gen():
                    yield "finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

                gen = fake_gen()

            prev_answer = ""

            async for gen_item in gen:
                status, answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = gen_item

                answer = answer[:4096]  # telegram message limit

                # update only when 100 new symbols are ready
                if abs(len(answer) - len(prev_answer)) < 100 and status != "finished":
                    continue

                try:
                    await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id, parse_mode=parse_mode)
                except telegram.error.BadRequest as e:
                    if str(e).startswith("Message is not modified"):
                        continue
                    else:
                        await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id)

                await asyncio.sleep(0.01)  # wait a bit to avoid flooding

                prev_answer = answer

            # update user data (сохраняем оригинальные сообщения без языковой инструкции)
            new_dialog_message = {"user": [{"type": "text", "text": _message}], "bot": answer, "date": datetime.now()}

            db.set_dialog_messages(
                user_id,
                db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
                dialog_id=None
            )

            db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)

        except asyncio.CancelledError:
            # note: intermediate token updates only work when enable_message_streaming=True (config.yml)
            db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)
            raise

        except Exception as e:
            error_text = f"Something went wrong during completion. Reason: {e}"
            await update.message.reply_text(error_text)
            return

        # send message if some messages were removed from the context
        if n_first_dialog_messages_removed > 0:
            if n_first_dialog_messages_removed == 1:
                text = t(user_id, "message_removed", chat_id=chat_id)
            else:
                text = t(user_id, "messages_removed", chat_id=chat_id, count=n_first_dialog_messages_removed)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async with user_semaphores[user_id]:
        # Проверяем только наличие фото, а не любых вложений
        if (current_model == "gpt-4-vision-preview" or current_model == "gpt-4o") and update.message.photo is not None and len(update.message.photo) > 0:
            if current_model != "gpt-4o" and current_model != "gpt-4-vision-preview":
                current_model = "gpt-4o"
                if chat_id < 0:  # Группа
                    db.set_group_attribute(chat_id, "current_model", "gpt-4o")
                else:  # Личный чат
                    db.set_user_attribute(user_id, "current_model", "gpt-4o")
            task = asyncio.create_task(
                _vision_message_handle_fn(update, context, db, use_new_dialog_timeout=use_new_dialog_timeout)
            )
        else:
            task = asyncio.create_task(
                message_handle_fn()
            )

        user_tasks[user_id] = task

        try:
            await task
        except asyncio.CancelledError:
            await update.message.reply_text(t(user_id, "canceled", chat_id=chat_id), parse_mode=ParseMode.HTML)
        else:
            pass
        finally:
            if user_id in user_tasks:
                task = user_tasks[user_id]
                task.cancel()
            else:
                await update.message.reply_text(
                    t(user_id, "nothing_to_cancel", chat_id=chat_id),
                    parse_mode=ParseMode.HTML
                )
            del user_tasks[user_id]

async def _vision_message_handle_fn(update: Update, context: CallbackContext, db, use_new_dialog_timeout: bool = True):
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    # Получаем модель из настроек группы или пользователя
    if chat_id < 0:  # Группа
        current_model = db.get_group_attribute(chat_id, "current_model")
    else:  # Личный чат
        current_model = db.get_user_attribute(user_id, "current_model")

    if current_model != "gpt-4-vision-preview" and current_model != "gpt-4o":
        await update.message.reply_text(
            t(user_id, "vision_model_required", chat_id=chat_id),
            parse_mode=ParseMode.HTML,
        )
        return

    # Получаем chat_mode из группы или пользователя
    if chat_id < 0:  # Группа
        chat_mode = db.get_group_attribute(chat_id, "current_chat_mode")
    else:  # Личный чат
        chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    # new dialog timeout
    if use_new_dialog_timeout:
        if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
            db.start_new_dialog(user_id)

            # Получаем локализованное welcome сообщение напрямую
            user_language = db.get_user_attribute(user_id, "language") or "en"
            mode_name = config.chat_modes[chat_mode]['name']

            # Отправляем уведомление о таймауте
            timeout_text = t(user_id, "dialog_timeout", chat_id=chat_id, mode_name=mode_name)
            await update.message.reply_text(timeout_text, parse_mode=ParseMode.HTML)

            # Получаем и отправляем локализованное welcome сообщение
            welcome_message = config.chat_modes[chat_mode]["welcome_message"]

            if isinstance(welcome_message, dict):
                welcome_text = welcome_message.get(user_language, welcome_message.get("en", "Welcome!"))
            else:
                welcome_text = welcome_message

            await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    buf = None
    if update.message.effective_attachment:
        photo = update.message.effective_attachment[-1]
        photo_file = await context.bot.get_file(photo.file_id)

        # store file in memory, not on disk
        buf = io.BytesIO()
        await photo_file.download_to_memory(buf)
        buf.name = "image.jpg"  # file extension is required
        buf.seek(0)  # move cursor to the beginning of the buffer

    # in case of CancelledError
    n_input_tokens, n_output_tokens = 0, 0

    try:
        # send placeholder message to user
        placeholder_message = await update.message.reply_text("...")
        message = update.message.caption or update.message.text or ''

        # send typing action
        await update.message.chat.send_action(action="typing")

        # ВАЖНО: Добавляем языковую инструкцию к диалогу
        dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
        enhanced_dialog_messages = enhance_dialog_messages_with_language(dialog_messages, user_id, chat_id, db)

        parse_mode = {"html": ParseMode.HTML, "markdown": ParseMode.MARKDOWN}[
            config.chat_modes[chat_mode]["parse_mode"]
        ]

        chatgpt_instance = openai_utils.ChatGPT(model=current_model)
        if config.enable_message_streaming:
            gen = chatgpt_instance.send_vision_message_stream(
                message,
                dialog_messages=enhanced_dialog_messages,
                image_buffer=buf,
                chat_mode=chat_mode,
            )
        else:
            (
                answer,
                (n_input_tokens, n_output_tokens),
                n_first_dialog_messages_removed,
            ) = await chatgpt_instance.send_vision_message(
                message,
                dialog_messages=enhanced_dialog_messages,
                image_buffer=buf,
                chat_mode=chat_mode,
            )

            async def fake_gen():
                yield "finished", answer, (
                    n_input_tokens,
                    n_output_tokens,
                ), n_first_dialog_messages_removed

            gen = fake_gen()

        prev_answer = ""
        async for gen_item in gen:
            (
                status,
                answer,
                (n_input_tokens, n_output_tokens),
                n_first_dialog_messages_removed,
            ) = gen_item

            answer = answer[:4096]  # telegram message limit

            # update only when 100 new symbols are ready
            if abs(len(answer) - len(prev_answer)) < 100 and status != "finished":
                continue

            try:
                await context.bot.edit_message_text(
                    answer,
                    chat_id=placeholder_message.chat_id,
                    message_id=placeholder_message.message_id,
                    parse_mode=parse_mode,
                )
            except telegram.error.BadRequest as e:
                if str(e).startswith("Message is not modified"):
                    continue
                else:
                    await context.bot.edit_message_text(
                        answer,
                        chat_id=placeholder_message.chat_id,
                        message_id=placeholder_message.message_id,
                    )

            await asyncio.sleep(0.01)  # wait a bit to avoid flooding

            prev_answer = answer

        # update user data (сохраняем оригинальные сообщения)
        if buf is not None:
            base_image = base64.b64encode(buf.getvalue()).decode("utf-8")
            new_dialog_message = {"user": [
                        {
                            "type": "text",
                            "text": message,
                        },
                        {
                            "type": "image",
                            "image": base_image,
                        }
                    ]
                , "bot": answer, "date": datetime.now()}
        else:
            new_dialog_message = {"user": [{"type": "text", "text": message}], "bot": answer, "date": datetime.now()}

        db.set_dialog_messages(
            user_id,
            db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
            dialog_id=None
        )

        db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)

    except asyncio.CancelledError:
        # note: intermediate token updates only work when enable_message_streaming=True (config.yml)
        db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)
        raise

    except Exception as e:
        error_text = f"Something went wrong during completion. Reason: {e}"
        await update.message.reply_text(error_text)
        return

async def generate_image_handle_with_limits(update: Update, context: CallbackContext, db, message=None):
    """Генерация изображений с проверкой лимитов"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    if await is_previous_message_not_answered_yet(update, context, db):
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    # Увеличиваем счетчик изображений
    db.add_daily_usage(user_id, "images", 1)

    await update.message.chat.send_action(action="upload_photo")
    message = message or update.message.text

    try:
        image_urls = await openai_utils.generate_images(
            message,
            n_images=config.return_n_generated_images,
            size=config.image_size
        )
    except Exception as e:
        if "safety system" in str(e):
            text = t(user_id, "unsupported_content", chat_id=chat_id)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            return
        else:
            raise

    # Обновляем счетчик изображений
    db.set_user_attribute(user_id, "n_generated_images",
                         config.return_n_generated_images + db.get_user_attribute(user_id, "n_generated_images"))

    for i, image_url in enumerate(image_urls):
        await update.message.chat.send_action(action="upload_photo")
        await update.message.reply_photo(image_url, parse_mode=ParseMode.HTML)

async def voice_message_handle(update: Update, context: CallbackContext, db):
    # check if bot was mentioned (for group chats)
    if not await is_bot_mentioned(update, context):
        return

    await register_user_if_not_exists(update, context, update.message.from_user, db)
    if await is_previous_message_not_answered_yet(update, context, db):
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)

    # store file in memory, not on disk
    buf = io.BytesIO()
    await voice_file.download_to_memory(buf)
    buf.name = "voice.oga"  # file extension is required
    buf.seek(0)  # move cursor to the beginning of the buffer

    transcribed_text = await openai_utils.transcribe_audio(buf)
    text = t(user_id, "voice_transcription", chat_id=chat_id, text=transcribed_text)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # update n_transcribed_seconds
    db.set_user_attribute(user_id, "n_transcribed_seconds", voice.duration + db.get_user_attribute(user_id, "n_transcribed_seconds"))

    await message_handle(update, context, db, message=transcribed_text)

async def unsupport_message_handle(update: Update, context: CallbackContext, db):
    """Обработка неподдерживаемых типов сообщений"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    error_text = t(user_id, "unsupported_files", chat_id=chat_id)
    await update.message.reply_text(error_text)
    return

async def edited_message_handle(update: Update, context: CallbackContext, db):
    """Обработка отредактированных сообщений"""
    if update.edited_message.chat.type == "private":
        user_id = update.edited_message.from_user.id
        chat_id = update.edited_message.chat.id
        text = t(user_id, "editing_not_supported", chat_id=chat_id)
        await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)

async def retry_handle(update: Update, context: CallbackContext, db):
    """Повтор последнего сообщения"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    if await is_previous_message_not_answered_yet(update, context, db):
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
    if len(dialog_messages) == 0:
        await update.message.reply_text(t(user_id, "nothing_to_retry", chat_id=chat_id))
        return

    last_dialog_message = dialog_messages.pop()
    db.set_dialog_messages(user_id, dialog_messages, dialog_id=None)  # last message was removed from the context

    await message_handle(update, context, db, message=last_dialog_message["user"], use_new_dialog_timeout=False)

async def cancel_handle(update: Update, context: CallbackContext, db):
    """Отмена текущего запроса"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    if user_id in user_tasks:
        task = user_tasks[user_id]
        task.cancel()
    else:
        await update.message.reply_text(
            t(user_id, "nothing_to_cancel", chat_id=chat_id),
            parse_mode=ParseMode.HTML
        )
