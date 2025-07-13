# message_handlers.py - Обработчики сообщений
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
from utils import register_user_if_not_exists

user_semaphores = {}
user_tasks = {}

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

    # Инициализация семафора если не существует
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(1)

    if user_semaphores[user_id].locked():
        text = "⏳ Please <b>wait</b> for a reply to the previous message\n"
        text += "Or you can /cancel it"
        await update.message.reply_text(text, reply_to_message_id=update.message.id, parse_mode=ParseMode.HTML)
        return True
    else:
        return False

async def message_handle(update: Update, context: CallbackContext, db, message=None, use_new_dialog_timeout=True):
    """Обработка сообщений с проверкой подписки и лимитов"""

    # Проверка упоминания бота
    if not await is_bot_mentioned(update, context):
        return

    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return

    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id

    # Инициализация семафора
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(1)

    # ПРОВЕРКА ЛИМИТОВ
    is_premium = db.get_user_subscription_status(user_id)
    daily_messages = db.get_daily_usage(user_id, "messages")

    # Лимиты
    max_daily_messages = 1000 if is_premium else 5

    if daily_messages >= max_daily_messages:
        text = f"🚫 <b>Дневной лимит исчерпан!</b>\n\n"
        if is_premium:
            text += f"Premium: {max_daily_messages} сообщений в день\n"
            text += f"Использовано: {daily_messages}\n\n"
            text += "Лимит обновится завтра в 00:00"
        else:
            text += f"Бесплатно: {max_daily_messages} сообщений в день\n"
            text += f"Использовано: {daily_messages}\n\n"
            text += "💎 Оформите Premium для 1000 сообщений в день!"

            keyboard = [[
                InlineKeyboardButton("💎 Купить Premium", callback_data="show_premium_plans")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            return

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    if await is_previous_message_not_answered_yet(update, context, db):
        return

    # Проверка доступа к моделям
    current_model = db.get_user_attribute(user_id, "current_model")
    premium_models = ["gpt-4", "gpt-4o", "gpt-4-vision-preview"]

    if current_model in premium_models and not is_premium:
        await update.message.reply_text(
            "🔒 GPT-4 доступен только в Premium. Переключено на GPT-3.5-turbo.",
            parse_mode=ParseMode.HTML
        )
        db.set_user_attribute(user_id, "current_model", "gpt-3.5-turbo")
        current_model = "gpt-3.5-turbo"

    # Увеличиваем счетчик использования
    db.add_daily_usage(user_id, "messages", 1)

    # Далее оригинальный код
    _message = message or update.message.text

    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    if chat_mode == "artist":
        # Проверка лимита изображений
        daily_images = db.get_daily_usage(user_id, "images")
        max_daily_images = 50 if is_premium else 2

        if daily_images >= max_daily_images:
            text = f"🚫 Лимит изображений исчерпан!\n\n"
            text += f"{'Premium' if is_premium else 'Бесплатно'}: {max_daily_images} изображений в день\n"
            text += f"Использовано: {daily_images}"

            if not is_premium:
                text += "\n\n💎 Premium: 50 изображений в день!"
                keyboard = [[InlineKeyboardButton("💎 Купить Premium", callback_data="show_premium_plans")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                return

            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            return

        await generate_image_handle_with_limits(update, context, db, message=message)
        return

    # Остальная логика как в оригинальном message_handle
    async def message_handle_fn():
        # new dialog timeout
        if use_new_dialog_timeout:
            if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
                db.start_new_dialog(user_id)
                await update.message.reply_text(f"Starting new dialog due to timeout (<b>{config.chat_modes[chat_mode]['name']}</b> mode) ✅", parse_mode=ParseMode.HTML)
        db.set_user_attribute(user_id, "last_interaction", datetime.now())

        # in case of CancelledError
        n_input_tokens, n_output_tokens = 0, 0

        try:
            # send placeholder message to user
            placeholder_message = await update.message.reply_text("...")

            # send typing action
            await update.message.chat.send_action(action="typing")

            if _message is None or len(_message) == 0:
                 await update.message.reply_text("🥲 You sent <b>empty message</b>. Please, try again!", parse_mode=ParseMode.HTML)
                 return

            dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
            parse_mode = {
                "html": ParseMode.HTML,
                "markdown": ParseMode.MARKDOWN
            }[config.chat_modes[chat_mode]["parse_mode"]]

            chatgpt_instance = openai_utils.ChatGPT(model=current_model)
            if config.enable_message_streaming:
                gen = chatgpt_instance.send_message_stream(_message, dialog_messages=dialog_messages, chat_mode=chat_mode)
            else:
                answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = await chatgpt_instance.send_message(
                    _message,
                    dialog_messages=dialog_messages,
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

            # update user data
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
                text = "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context.\n Send /new command to start new dialog"
            else:
                text = f"✍️ <i>Note:</i> Your current dialog is too long, so <b>{n_first_dialog_messages_removed} first messages</b> were removed from the context.\n Send /new command to start new dialog"
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async with user_semaphores[user_id]:
        if current_model == "gpt-4-vision-preview" or current_model == "gpt-4o" or update.message.photo is not None and len(update.message.photo) > 0:

            if current_model != "gpt-4o" and current_model != "gpt-4-vision-preview":
                current_model = "gpt-4o"
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
            await update.message.reply_text("✅ Canceled", parse_mode=ParseMode.HTML)
        else:
            pass
        finally:
            if user_id in user_tasks:
                del user_tasks[user_id]

async def _vision_message_handle_fn(update: Update, context: CallbackContext, db, use_new_dialog_timeout: bool = True):
    user_id = update.message.from_user.id
    current_model = db.get_user_attribute(user_id, "current_model")

    if current_model != "gpt-4-vision-preview" and current_model != "gpt-4o":
        await update.message.reply_text(
            "🥲 Images processing is only available for <b>gpt-4-vision-preview</b> and <b>gpt-4o</b> model. Please change your settings in /settings",
            parse_mode=ParseMode.HTML,
        )
        return

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    # new dialog timeout
    if use_new_dialog_timeout:
        if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
            db.start_new_dialog(user_id)
            await update.message.reply_text(f"Starting new dialog due to timeout (<b>{config.chat_modes[chat_mode]['name']}</b> mode) ✅", parse_mode=ParseMode.HTML)
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

        dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
        parse_mode = {"html": ParseMode.HTML, "markdown": ParseMode.MARKDOWN}[
            config.chat_modes[chat_mode]["parse_mode"]
        ]

        chatgpt_instance = openai_utils.ChatGPT(model=current_model)
        if config.enable_message_streaming:
            gen = chatgpt_instance.send_vision_message_stream(
                message,
                dialog_messages=dialog_messages,
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
                dialog_messages=dialog_messages,
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

        # update user data
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
            text = "🥲 Your request <b>doesn't comply</b> with OpenAI's usage policies.\nWhat did you write there, huh?"
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
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)

    # store file in memory, not on disk
    buf = io.BytesIO()
    await voice_file.download_to_memory(buf)
    buf.name = "voice.oga"  # file extension is required
    buf.seek(0)  # move cursor to the beginning of the buffer

    transcribed_text = await openai_utils.transcribe_audio(buf)
    text = f"🎤: <i>{transcribed_text}</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # update n_transcribed_seconds
    db.set_user_attribute(user_id, "n_transcribed_seconds", voice.duration + db.get_user_attribute(user_id, "n_transcribed_seconds"))

    await message_handle(update, context, db, message=transcribed_text)

async def unsupport_message_handle(update: Update, context: CallbackContext):
    """Обработка неподдерживаемых типов сообщений"""
    error_text = "I don't know how to read files or videos. Send the picture in normal mode (Quick Mode)."
    await update.message.reply_text(error_text)
    return

async def edited_message_handle(update: Update, context: CallbackContext):
    """Обработка отредактированных сообщений"""
    if update.edited_message.chat.type == "private":
        text = "🥲 Unfortunately, message <b>editing</b> is not supported"
        await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)

async def retry_handle(update: Update, context: CallbackContext, db):
    """Повтор последнего сообщения"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)
    if await is_previous_message_not_answered_yet(update, context, db):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
    if len(dialog_messages) == 0:
        await update.message.reply_text("No message to retry 🤷‍♂️")
        return

    last_dialog_message = dialog_messages.pop()
    db.set_dialog_messages(user_id, dialog_messages, dialog_id=None)  # last message was removed from the context

    await message_handle(update, context, db, message=last_dialog_message["user"], use_new_dialog_timeout=False)

async def cancel_handle(update: Update, context: CallbackContext, db):
    """Отмена текущего запроса"""
    await register_user_if_not_exists(update, context, update.message.from_user, db)

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    if user_id in user_tasks:
        task = user_tasks[user_id]
        task.cancel()
    else:
        await update.message.reply_text("<i>Nothing to cancel...</i>", parse_mode=ParseMode.HTML)
