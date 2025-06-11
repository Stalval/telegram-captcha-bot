#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import random
import os
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
IMAGE_URL = "https://drive.google.com/uc?export=view&id=1uwlyma2UL6Fmk3b_lUu5iZ8qry6IIyME"
CORRECT_ANSWER_TEXT = "Героям слава!"
WRONG_ANSWER_TEXT = "Не все так однозначно"
# ------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет капчу и запоминает ID сообщения о входе."""
    if not update.message or not update.message.new_chat_members:
        return
        
    join_message_id = update.message.message_id
    new_members = update.message.new_chat_members
    chat = update.effective_chat
    
    for member in new_members:
        if member.is_bot:
            continue
            
        logger.info(f"Новый пользователь {member.full_name} ({member.id}) в чате {chat.title}.")
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=member.id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception as e:
            logger.error(f"Не удалось ограничить права {member.id}: {e}.")
            return

        keyboard_buttons = [
            InlineKeyboardButton(text=CORRECT_ANSWER_TEXT, callback_data=f"verify_correct_{member.id}_{join_message_id}"),
            InlineKeyboardButton(text=WRONG_ANSWER_TEXT, callback_data=f"verify_wrong_{member.id}_{join_message_id}")
        ]
        random.shuffle(keyboard_buttons)
        reply_markup = InlineKeyboardMarkup([keyboard_buttons])

        captcha_caption = f"Добро пожаловать, {member.mention_html()}! Чтобы писать в чат, подтвердите, что вы не робот. Нажмите на правильный ответ."

        await update.message.reply_photo(
            photo=IMAGE_URL,
            caption=captcha_caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки капчи."""
    query = update.callback_query
    await query.answer()

    try:
        _, action, target_user_id_str, join_message_id_str = query.data.split("_")
        target_user_id = int(target_user_id_str)
        join_message_id = int(join_message_id_str)
    except (ValueError, IndexError):
        logger.warning(f"Некорректный формат callback_data: {query.data}")
        return

    if query.from_user.id != target_user_id:
        await query.answer("Это проверка для другого пользователя.", show_alert=True)
        return

    chat_id = query.message.chat.id
    user = query.from_user
    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    chat = query.message.chat 

    if action == "correct":
        try:
            full_permissions = ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user.id, permissions=full_permissions)
            
            logger.info(f"Пользователь {user.full_name} ({user.id}) прошел проверку.")
            
            await query.delete_message()
            
            welcome_text = f"""✅ Привет, {user.mention_html()}! Проверка пройдена.

<b>Правила чата:</b>
1. Запрещены мат и оскорбления участников.
2. Проявляйте уважение друг к другу (исключение — вата, которая удаляется по умолчанию).
3. Запрещены дискриминация по любому признаку, сексизм, расизм, антисемитизм, ксенофобия.

<b>Большая просьба:</b>
Если есть желание начать спор с конкретным участником, переходите в личные сообщения. Участникам чата не интересно наблюдать за перепалкой двух человек.

<b>Наказания за нарушения:</b>
- 1-е нарушение: предупреждение.
- 2-е нарушение: запрет писать на 24 часа.
- 3-е нарушение: постоянный запрет писать в чате.

<i>Возможность читать чат остаётся.</i>
"""
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_text,
                parse_mode='HTML'
            )
            
            if context.job_queue:
                context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(chat_id, msg.message_id), 60)

        except Exception as e:
            logger.error(f"Не удалось снять ограничения с {user.id}: {e}")

    elif action == "wrong":
        try:
            await query.delete_message()
            await context.bot.delete_message(chat_id=chat_id, message_id=join_message_id)

            try:
                error_text = (f"❌ Вы не прошли проверку для входа в группу «{chat.title}».\n\n"
                              f"Попробуйте выйти и снова войти в группу, чтобы получить новую капчу.")
                await context.bot.send_message(
                    chat_id=user.id,
                    text=error_text
                )
                logger.info(f"Отправлено личное уведомление об ошибке пользователю {user.id}")
            except (Forbidden, BadRequest) as e:
                logger.warning(f"Не удалось отправить личное сообщение пользователю {user.id}: {e}")
            
            until_date = datetime.datetime.now() + datetime.timedelta(seconds=10)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            
            logger.info(f"Пользователь {user.full_name} ({user.id}) не прошел проверку. Сообщения в группе удалены.")
            
        except Exception as e:
            logger.error(f"Не удалось обработать неверный ответ для {user.id}: {e}")


def main():
    """Основная функция для запуска бота."""
    if not TOKEN:
        logger.error("Токен не найден! Убедитесь, что вы установили переменную окружения TELEGRAM_TOKEN.")
        return

    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member))
    application.add_handler(CallbackQueryHandler(button_callback, pattern=r"^verify_"))
    
    print("Бот запущен...")
    application.run_polling()
    print("Бот остановлен.")


if __name__ == "__main__":
    main()
