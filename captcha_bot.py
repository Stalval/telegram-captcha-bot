import logging
import random
import os  # Добавлен импорт для работы с переменными окружения
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- НАСТРОЙКИ ---
# 1. Токен теперь будет загружаться из переменных окружения сервера.
#    Это безопасно и является стандартом для развертывания.
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 2. Укажите прямую ссылку на картинку для проверки.
IMAGE_URL = "https://drive.google.com/uc?export=view&id=1uwlyma2UL6Fmk3b_lUu5iZ8qry6IIyME"

# 3. Напишите тексты для кнопок.
CORRECT_ANSWER_TEXT = "Героям слава!"
WRONG_ANSWER_TEXT = "Не все так однозначно"
# ------------------


# Инициализация логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def welcome_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет капчу новым участникам группы."""
    if not update.message or not update.message.new_chat_members:
        return
        
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
            InlineKeyboardButton(text=CORRECT_ANSWER_TEXT, callback_data=f"verify_correct_{member.id}"),
            InlineKeyboardButton(text=WRONG_ANSWER_TEXT, callback_data=f"verify_wrong_{member.id}")
        ]
        random.shuffle(keyboard_buttons)
        reply_markup = InlineKeyboardMarkup([keyboard_buttons])

        await update.message.reply_photo(
            photo=IMAGE_URL,
            caption=f"Добро пожаловать, {member.mention_html()}! Чтобы писать в чат, подтвердите, что вы не робот. Нажмите на правильный ответ.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки капчи."""
    query = update.callback_query
    await query.answer()

    action, target_user_id_str = query.data.split("_")[1:]
    target_user_id = int(target_user_id_str)

    if query.from_user.id != target_user_id:
        await query.answer("Это проверка для другого пользователя.", show_alert=True)
        return

    chat_id = query.message.chat.id
    user = query.from_user

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
            
            msg = await context.bot.send_message(chat_id, f"✅ Отлично, {user.mention_html()}! Проверка пройдена.", parse_mode='HTML')
            
            if context.job_queue:
                context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(chat_id, msg.message_id), 10) # Примерно 10 секунд
        except Exception as e:
            logger.error(f"Не удалось снять ограничения с {user.id}: {e}")

    elif action == "wrong":
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user.id)
            logger.info(f"Пользователь {user.full_name} ({user.id}) кикнут за неверный ответ.")
            await query.delete_message()
        except Exception as e:
            logger.error(f"Не удалось кикнуть {user.id}: {e}")


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
