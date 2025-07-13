import io
import logging
import asyncio
import traceback
import html
import json
from datetime import datetime, timedelta
import uuid
import openai

import telegram
from telegram import (
    Update,
    User,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    LabeledPrice
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    AIORateLimiter,
    filters
)
from telegram.constants import ParseMode, ChatAction

import config
import database
import openai_utils

import base64

# setup
db = database.Database()
logger = logging.getLogger(__name__)

user_semaphores = {}
user_tasks = {}

HELP_MESSAGE = """Commands:
⚪ /retry – Regenerate last bot answer
⚪ /new – Start new dialog
⚪ /mode – Select chat mode
⚪ /settings – Show settings
⚪ /balance – Show balance
⚪ /premium – Premium subscription
⚪ /help – Show help

🎨 Generate images from text prompts in <b>👩‍🎨 Artist</b> /mode
👥 Add bot to <b>group chat</b>: /help_group_chat
🎤 You can send <b>Voice Messages</b> instead of text

💎 <b>Premium features:</b>
- 1000 messages/day (vs 20 free)
- GPT-4 and GPT-4o access
- 50 images/day (vs 2 free)
"""

HELP_GROUP_CHAT_MESSAGE = """You can add bot to any <b>group chat</b> to help and entertain its participants!

Instructions (see <b>video</b> below):
1. Add the bot to the group chat
2. Make it an <b>admin</b>, so that it can see messages (all other rights can be restricted)
3. You're awesome!

To get a reply from the bot in the chat – @ <b>tag</b> it or <b>reply</b> to its message.
For example: "{bot_username} write a poem about Telegram"
"""


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name= user.last_name
        )
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id)

    if user.id not in user_semaphores:
        user_semaphores[user.id] = asyncio.Semaphore(1)

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


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)

    reply_text = "Hi! I'm <b>ChatGPT</b> bot implemented with OpenAI API 🤖\n\n"
    reply_text += HELP_MESSAGE

    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
    await show_chat_modes_handle(update, context)


async def help_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)


async def help_group_chat_handle(update: Update, context: CallbackContext):
     await register_user_if_not_exists(update, context, update.message.from_user)
     user_id = update.message.from_user.id
     db.set_user_attribute(user_id, "last_interaction", datetime.now())

     text = HELP_GROUP_CHAT_MESSAGE.format(bot_username="@" + context.bot.username)

     await update.message.reply_text(text, parse_mode=ParseMode.HTML)
     await update.message.reply_video(config.help_group_chat_video_path)


async def retry_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
    if len(dialog_messages) == 0:
        await update.message.reply_text("No message to retry 🤷‍♂️")
        return

    last_dialog_message = dialog_messages.pop()
    db.set_dialog_messages(user_id, dialog_messages, dialog_id=None)  # last message was removed from the context

    await message_handle(update, context, message=last_dialog_message["user"], use_new_dialog_timeout=False)

async def _vision_message_handle_fn(
    update: Update, context: CallbackContext, use_new_dialog_timeout: bool = True
):
    logger.info('_vision_message_handle_fn')
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
        logger.error(error_text)
        await update.message.reply_text(error_text)
        return

async def unsupport_message_handle(update: Update, context: CallbackContext, message=None):
    error_text = f"I don't know how to read files or videos. Send the picture in normal mode (Quick Mode)."
    logger.error(error_text)
    await update.message.reply_text(error_text)
    return

async def message_handle(update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True):
    """Обработка сообщений с проверкой подписки и лимитов"""

    # Проверка упоминания бота
    if not await is_bot_mentioned(update, context):
        return

    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return

    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id

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

    if await is_previous_message_not_answered_yet(update, context):
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

        await generate_image_handle_with_limits(update, context, message=message)
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
            logger.error(error_text)
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

            logger.error(current_model)

            if current_model != "gpt-4o" and current_model != "gpt-4-vision-preview":
                current_model = "gpt-4o"
                db.set_user_attribute(user_id, "current_model", "gpt-4o")
            task = asyncio.create_task(
                _vision_message_handle_fn(update, context, use_new_dialog_timeout=use_new_dialog_timeout)
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


async def is_previous_message_not_answered_yet(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    if user_semaphores[user_id].locked():
        text = "⏳ Please <b>wait</b> for a reply to the previous message\n"
        text += "Or you can /cancel it"
        await update.message.reply_text(text, reply_to_message_id=update.message.id, parse_mode=ParseMode.HTML)
        return True
    else:
        return False


async def voice_message_handle(update: Update, context: CallbackContext):
    # check if bot was mentioned (for group chats)
    if not await is_bot_mentioned(update, context):
        return

    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

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

    await message_handle(update, context, message=transcribed_text)


async def generate_image_handle(update: Update, context: CallbackContext, message=None):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    await update.message.chat.send_action(action="upload_photo")

    message = message or update.message.text

    try:
        image_urls = await openai_utils.generate_images(message, n_images=config.return_n_generated_images, size=config.image_size)
    except openai.error.InvalidRequestError as e:
        if str(e).startswith("Your request was rejected as a result of our safety system"):
            text = "🥲 Your request <b>doesn't comply</b> with OpenAI's usage policies.\nWhat did you write there, huh?"
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            return
        else:
            raise

    # token usage
    db.set_user_attribute(user_id, "n_generated_images", config.return_n_generated_images + db.get_user_attribute(user_id, "n_generated_images"))

    for i, image_url in enumerate(image_urls):
        await update.message.chat.send_action(action="upload_photo")
        await update.message.reply_photo(image_url, parse_mode=ParseMode.HTML)

async def generate_image_handle_with_limits(update: Update, context: CallbackContext, message=None):
    """Генерация изображений с проверкой лимитов"""
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
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
    except openai.error.InvalidRequestError as e:
        if str(e).startswith("Your request was rejected as a result of our safety system"):
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

async def new_dialog_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.set_user_attribute(user_id, "current_model", "gpt-3.5-turbo")

    db.start_new_dialog(user_id)
    await update.message.reply_text("Starting new dialog ✅")

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")
    await update.message.reply_text(f"{config.chat_modes[chat_mode]['welcome_message']}", parse_mode=ParseMode.HTML)


async def cancel_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    if user_id in user_tasks:
        task = user_tasks[user_id]
        task.cancel()
    else:
        await update.message.reply_text("<i>Nothing to cancel...</i>", parse_mode=ParseMode.HTML)


def get_chat_mode_menu(page_index: int):
    n_chat_modes_per_page = config.n_chat_modes_per_page
    text = f"Select <b>chat mode</b> ({len(config.chat_modes)} modes available):"

    # buttons
    chat_mode_keys = list(config.chat_modes.keys())
    page_chat_mode_keys = chat_mode_keys[page_index * n_chat_modes_per_page:(page_index + 1) * n_chat_modes_per_page]

    keyboard = []
    for chat_mode_key in page_chat_mode_keys:
        name = config.chat_modes[chat_mode_key]["name"]
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_chat_mode|{chat_mode_key}")])

    # pagination
    if len(chat_mode_keys) > n_chat_modes_per_page:
        is_first_page = (page_index == 0)
        is_last_page = ((page_index + 1) * n_chat_modes_per_page >= len(chat_mode_keys))

        if is_first_page:
            keyboard.append([
                InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
            ])
        elif is_last_page:
            keyboard.append([
                InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
                InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
            ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    return text, reply_markup


async def show_chat_modes_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_chat_mode_menu(0)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def show_chat_modes_callback_handle(update: Update, context: CallbackContext):
     await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
     if await is_previous_message_not_answered_yet(update.callback_query, context): return

     user_id = update.callback_query.from_user.id
     db.set_user_attribute(user_id, "last_interaction", datetime.now())

     query = update.callback_query
     await query.answer()

     page_index = int(query.data.split("|")[1])
     if page_index < 0:
         return

     text, reply_markup = get_chat_mode_menu(page_index)
     try:
         await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
     except telegram.error.BadRequest as e:
         if str(e).startswith("Message is not modified"):
             pass


async def set_chat_mode_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    chat_mode = query.data.split("|")[1]

    db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    db.start_new_dialog(user_id)

    await context.bot.send_message(
        update.callback_query.message.chat.id,
        f"{config.chat_modes[chat_mode]['welcome_message']}",
        parse_mode=ParseMode.HTML
    )


def get_settings_menu(user_id: int):
    current_model = db.get_user_attribute(user_id, "current_model")
    text = config.models["info"][current_model]["description"]

    text += "\n\n"
    score_dict = config.models["info"][current_model]["scores"]
    for score_key, score_value in score_dict.items():
        text += "🟢" * score_value + "⚪️" * (5 - score_value) + f" – {score_key}\n\n"

    text += "\nSelect <b>model</b>:"

    # buttons to choose models
    buttons = []
    for model_key in config.models["available_text_models"]:
        title = config.models["info"][model_key]["name"]
        if model_key == current_model:
            title = "✅ " + title

        buttons.append(
            InlineKeyboardButton(title, callback_data=f"set_settings|{model_key}")
        )
    reply_markup = InlineKeyboardMarkup([buttons])

    return text, reply_markup


async def settings_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_settings_menu(user_id)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def set_settings_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    _, model_key = query.data.split("|")
    db.set_user_attribute(user_id, "current_model", model_key)
    db.start_new_dialog(user_id)

    text, reply_markup = get_settings_menu(user_id)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass


async def show_balance_handle(update: Update, context: CallbackContext):
    """Показать баланс и статистику с учетом подписки"""
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    is_premium = db.get_user_subscription_status(user_id)

    # Статистика использования за сегодня
    daily_messages = db.get_daily_usage(user_id, "messages")
    daily_images = db.get_daily_usage(user_id, "images")

    # Лимиты
    max_messages = 1000 if is_premium else 5
    max_images = 50 if is_premium else 2

    # Основная статистика
    text = f"💳 <b>Ваш баланс и статистика</b>\n\n"

    # Статус подписки
    if is_premium:
        subscription = db.db["subscriptions"].find_one({
            "user_id": user_id,
            "status": "active",
            "expires_at": {"$gt": datetime.now()}
        })
        text += f"💎 <b>Premium до:</b> {subscription['expires_at'].strftime('%d.%m.%Y')}\n\n"
    else:
        text += f"🆓 <b>Бесплатный план</b>\n\n"

    # Использование за сегодня
    text += f"📊 <b>Использование сегодня:</b>\n"
    text += f"💬 Сообщения: {daily_messages}/{max_messages}\n"
    text += f"🎨 Изображения: {daily_images}/{max_images}\n\n"

    # Общая статистика (оригинальный код)
    total_n_spent_dollars = 0
    total_n_used_tokens = 0

    n_used_tokens_dict = db.get_user_attribute(user_id, "n_used_tokens")
    n_generated_images = db.get_user_attribute(user_id, "n_generated_images")
    n_transcribed_seconds = db.get_user_attribute(user_id, "n_transcribed_seconds")

    details_text = "🏷️ <b>Детальная статистика:</b>\n"
    for model_key in sorted(n_used_tokens_dict.keys()):
        n_input_tokens, n_output_tokens = n_used_tokens_dict[model_key]["n_input_tokens"], n_used_tokens_dict[model_key]["n_output_tokens"]
        total_n_used_tokens += n_input_tokens + n_output_tokens

        n_input_spent_dollars = config.models["info"][model_key]["price_per_1000_input_tokens"] * (n_input_tokens / 1000)
        n_output_spent_dollars = config.models["info"][model_key]["price_per_1000_output_tokens"] * (n_output_tokens / 1000)
        total_n_spent_dollars += n_input_spent_dollars + n_output_spent_dollars

        details_text += f"- {model_key}: <b>{n_input_spent_dollars + n_output_spent_dollars:.03f}$</b> / <b>{n_input_tokens + n_output_tokens} токенов</b>\n"

    # Генерация изображений
    image_generation_n_spent_dollars = config.models["info"]["dalle-2"]["price_per_1_image"] * n_generated_images
    if n_generated_images != 0:
        details_text += f"- DALL·E 2: <b>{image_generation_n_spent_dollars:.03f}$</b> / <b>{n_generated_images} изображений</b>\n"

    total_n_spent_dollars += image_generation_n_spent_dollars

    # Распознавание голоса
    voice_recognition_n_spent_dollars = config.models["info"]["whisper"]["price_per_1_min"] * (n_transcribed_seconds / 60)
    if n_transcribed_seconds != 0:
        details_text += f"- Whisper: <b>{voice_recognition_n_spent_dollars:.03f}$</b> / <b>{n_transcribed_seconds:.01f} секунд</b>\n"

    total_n_spent_dollars += voice_recognition_n_spent_dollars

    text += f"💰 <b>Всего потрачено:</b> {total_n_spent_dollars:.03f}$\n"
    text += f"🔤 <b>Всего токенов:</b> {total_n_used_tokens}\n\n"
    text += details_text

    # Кнопка Premium если не активна
    keyboard = []
    if not is_premium:
        keyboard.append([InlineKeyboardButton("💎 Купить Premium", callback_data="show_premium_plans")])

    keyboard.append([InlineKeyboardButton("📊 Обновить статистику", callback_data="refresh_balance")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def edited_message_handle(update: Update, context: CallbackContext):
    if update.edited_message.chat.type == "private":
        text = "🥲 Unfortunately, message <b>editing</b> is not supported"
        await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)


async def error_handle(update: Update, context: CallbackContext) -> None:
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
            except telegram.error.BadRequest:
                # answer has invalid characters, so we send it without parse_mode
                await context.bot.send_message(update.effective_chat.id, message_chunk)
    except:
        await context.bot.send_message(update.effective_chat.id, "Some error in error handler")

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("/new", "Start new dialog"),
        BotCommand("/mode", "Select chat mode"),
        BotCommand("/retry", "Re-generate response for previous query"),
        BotCommand("/balance", "Show balance"),
        BotCommand("/premium", "Premium subscription"),
        BotCommand("/settings", "Show settings"),
        BotCommand("/help", "Show help message"),
    ])

async def show_premium_plans_handle(update: Update, context: CallbackContext):
    """Показать тарифные планы"""
    # Определяем откуда пришел запрос - команда или callback
    if update.message:
        # Пришло через команду /premium
        await register_user_if_not_exists(update, context, update.message.from_user)
        user_id = update.message.from_user.id
        send_method = update.message.reply_text
    else:
        # Пришло через callback (кнопку)
        await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
        user_id = update.callback_query.from_user.id
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
    text += "🗓 Месяц - 299₽\n"
    text += "📅 Год - 2990₽ (скидка 17%)"

    keyboard = []

    # Показываем кнопки покупки только если токен настроен
    if not is_premium and config.PAYMENT_PROVIDER_TOKEN:
        keyboard.extend([
            [InlineKeyboardButton("🗓 Месяц - 299₽", callback_data="buy_premium_monthly")],
            [InlineKeyboardButton("📅 Год - 2990₽", callback_data="buy_premium_yearly")]
        ])
    elif not config.PAYMENT_PROVIDER_TOKEN:
        text += "\n\n❌ <i>Платежи временно недоступны</i>"

    keyboard.append([InlineKeyboardButton("📊 Мое использование", callback_data="show_my_usage")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_method(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_usage_stats_handle(update: Update, context: CallbackContext):
    """Показать статистику использования"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
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

async def buy_premium_handle(update: Update, context: CallbackContext):
    """Покупка Premium подписки"""
    query = update.callback_query
    await query.answer()

    plan_type = query.data.split("_")[-1]  # monthly или yearly

    if plan_type == "monthly":
        title = "Premium на месяц"
        description = "Premium доступ на 30 дней"
        price = 299
        payload = "premium_monthly"
    else:
        title = "Premium на год"
        description = "Premium доступ на 365 дней со скидкой 17%"
        price = 2990
        payload = "premium_yearly"

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=config.PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice("Premium", price * 100)],  # в копейках
        start_parameter="premium_subscription"
    )

async def pre_checkout_callback(update: Update, context: CallbackContext):
    """Проверка перед оплатой"""
    query = update.pre_checkout_query

    if query.invoice_payload in ["premium_monthly", "premium_yearly"]:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка платежа")

async def successful_payment_callback(update: Update, context: CallbackContext):
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

def run_bot() -> None:
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

    # Фильтры пользователей (оригинальный код)
    user_filter = filters.ALL
    if len(config.allowed_telegram_usernames) > 0:
        usernames = [x for x in config.allowed_telegram_usernames if isinstance(x, str)]
        any_ids = [x for x in config.allowed_telegram_usernames if isinstance(x, int)]
        user_ids = [x for x in any_ids if x > 0]
        group_ids = [x for x in any_ids if x < 0]
        user_filter = filters.User(username=usernames) | filters.User(user_id=user_ids) | filters.Chat(chat_id=group_ids)

    # Основные обработчики
    application.add_handler(CommandHandler("start", start_handle, filters=user_filter))
    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))
    application.add_handler(CommandHandler("help_group_chat", help_group_chat_handle, filters=user_filter))

    # Обработчики сообщений (используем новые версии с лимитами)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND & user_filter, message_handle))
    application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND & user_filter, unsupport_message_handle))
    application.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND & user_filter, unsupport_message_handle))

    application.add_handler(CommandHandler("retry", retry_handle, filters=user_filter))
    application.add_handler(CommandHandler("new", new_dialog_handle, filters=user_filter))
    application.add_handler(CommandHandler("cancel", cancel_handle, filters=user_filter))

    application.add_handler(MessageHandler(filters.VOICE & user_filter, voice_message_handle))

    application.add_handler(CommandHandler("mode", show_chat_modes_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(show_chat_modes_callback_handle, pattern="^show_chat_modes"))
    application.add_handler(CallbackQueryHandler(set_chat_mode_handle, pattern="^set_chat_mode"))

    application.add_handler(CommandHandler("settings", settings_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(set_settings_handle, pattern="^set_settings"))

    # Обновленный balance с подписками
    application.add_handler(CommandHandler("balance", show_balance_handle, filters=user_filter))

    # НОВЫЕ обработчики для Premium
    application.add_handler(CommandHandler("premium", show_premium_plans_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(show_premium_plans_handle, pattern="^show_premium_plans"))
    application.add_handler(CallbackQueryHandler(show_usage_stats_handle, pattern="^show_my_usage"))
    application.add_handler(CallbackQueryHandler(buy_premium_handle, pattern="^buy_premium"))

    # Обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Refresh balance callback
    application.add_handler(CallbackQueryHandler(show_balance_handle, pattern="^refresh_balance"))

    application.add_error_handler(error_handle)

    # Запуск бота
    application.run_polling()


if __name__ == "__main__":
    run_bot()
