#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import random
import os
import datetime
import asyncio
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
if TOKEN is None:
    raise ValueError("Токен не найден! Убедитесь, что вы установили переменную окружения TELEGRAM_TOKEN.")

IMAGE_URL = "https://drive.google.com/uc?export=view&id=1uwlyma2UL6Fmk3b_lUu5iZ8qry6IIyME"
CORRECT_ANSWER_TEXT = "Героям слава!"
WRONG_ANSWER_TEXT = "Не все так однозначно"
CAPTCHA_TIMEOUT_SECONDS = 60
# ------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def delete_left_member_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет только сообщения о выходе/кике участников."""
    if update.message:
        try:
            await update.message.delete()
            logger.info("Удалено системное сообщение о выходе/кике участника.")
        except BadRequest:
            pass


async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """СНАЧАЛА удаляет сообщение о входе, ПОТОМ отправляет капчу и ставит таймер."""
    if not update.message or not update.message.new_chat_members:
        return

    try:
        await asyncio.sleep(0.5) # Небольшая задержка для надежности
        await update.message.delete()
        logger.info(f"Успешно удалено системное сообщение о входе.")
    except (BadRequest, Forbidden) as e:
        logger.warning(f"Не удалось удалить сообщение о входе: {e}. Проверьте права бота!")

    join_message_id = update.message.message_id
    new_members = update.message.new_chat_members
    chat = update.effective_chat

    for member in new_members:
        if member.is_bot:
            continue

        logger.info(f"Начинаю обработку нового пользователя {member.full_name} ({member.id}).")
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=member.id, permissions=ChatPermissions(can_send_messages=False)
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
        captcha_caption = f"Добро пожаловать, {member.mention_html()}! У вас есть {CAPTCHA_TIMEOUT_SECONDS} секунд, чтобы подтвердить, что вы не робот. Нажмите на правильный ответ."
        
        captcha_message = await context.bot.send_photo(
            chat_id=chat.id, photo=IMAGE_URL, caption=captcha_caption, reply_markup=reply_markup, parse_mode='HTML'
        )

        job_name = f"captcha_timeout_{chat.id}_{member.id}"
        context.job_queue.run_once(
            delete_captcha_timeout, CAPTCHA_TIMEOUT_SECONDS,
            data={'chat_id': chat.id, 'captcha_message_id': captcha_message.message_id, 'user_id': member.id},
            name=job_name,
        )
        logger.info(f"Установлен таймаут '{job_name}' для пользователя {member.id}.")


async def delete_captcha_timeout(context: ContextTypes.DEFAULT_TYPE):
    """Удаляет капчу и пользователя, если он не ответил вовремя."""
    job_data = context.job.data
    chat_id, captcha_message_id, user_id = job_data['chat_id'], job_data['captcha_message_id'], job_data['user_id']
    logger.info(f"Сработал таймаут капчи для {user_id}. Удаление.")
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=captcha_message_id)
    except BadRequest: pass
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=datetime.datetime.now() + datetime.timedelta(seconds=40))
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        logger.info(f"Пользователь {user_id} был удален из-за таймаута капчи.")
    except Exception as e:
        logger.error(f"Не удалось удалить пользователя {user_id} по таймауту: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки капчи."""
    query = update.callback_query
    try:
        _, action, target_user_id_str, join_message_id_str = query.data.split("_")
        target_user_id = int(target_user_id_str)
    except (ValueError, IndexError):
        await query.answer()
        return

    if query.from_user.id != target_user_id:
        await query.answer("Это проверка для другого пользователя.", show_alert=True)
        return

    chat_id = query.message.chat.id
    user = query.from_user
    job_name = f"captcha_timeout_{chat_id}_{user.id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)

    if not current_jobs:
        await query.answer("Срок действия этой проверки истек.", show_alert=True)
        try:
            await query.delete_message()
        except BadRequest: pass
        return

    for job in current_jobs:
        job.schedule_removal()
    await query.answer()

    if action == "correct":
        try:
            full_permissions = ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user.id, permissions=full_permissions)
            await query.delete_message()
            
            # <<< --- ПОЛНЫЙ ТЕКСТ ПРАВИЛ ВОССТАНОВЛЕН --- >>>
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
            msg = await context.bot.send_message(chat_id=chat_id, text=welcome_text, parse_mode='HTML')
            context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(chat_id, msg.message_id), 60)
        except Exception as e:
            logger.error(f"Не удалось снять ограничения с {user.id}: {e}")

    elif action == "wrong":
        try:
            await query.delete_message()
            chat_title = query.message.chat.title
            error_text = (f"❌ Вы не прошли проверку для входа в группу «{chat_title}».\n\n"
                           f"Вы были удалены из группы, но можете сразу же войти снова и попробовать еще раз.")
            try:
                await context.bot.send_message(chat_id=user.id, text=error_text)
            except (Forbidden, BadRequest): pass
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id, until_date=datetime.datetime.now() + datetime.timedelta(seconds=40))
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user.id, only_if_banned=True)
            logger.info(f"Пользователь {user.full_name} ({user.id}) не прошел проверку и был удален.")
        except Exception as e:
            logger.error(f"Не удалось обработать неверный ответ для {user.id}: {e}")

def main():
    """Основная функция для запуска бота."""
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_member))
    application.add_handler(CallbackQueryHandler(button_callback, pattern=r"^verify_"))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_left_member_message))
    
    print("Бот запущен - финальная версия с правилами")
    application.run_polling()
    print("Бот остановлен.")

if __name__ == "__main__":
    main()
