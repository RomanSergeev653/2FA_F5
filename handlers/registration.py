from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging

from config import MESSAGES, IMAP_SETTINGS
from database.db_manager import db
from utils.encryption import encrypt_password
from utils.email_parser import EmailParser

# Создаём роутер
router = Router()
logger = logging.getLogger(__name__)


# Определяем состояния для регистрации
class RegistrationStates(StatesGroup):
    """
    Состояния процесса регистрации.
    """
    waiting_for_email_data = State()  # Ожидание email и пароля
    choosing_provider = State()  # Выбор провайдера для неизвестного домена


@router.message(Command('register'))
async def cmd_register(message: Message, state: FSMContext):
    """
    Обработчик команды /register
    Начинает процесс регистрации почты.
    """
    user_id = message.from_user.id

    # Проверяем, не зарегистрирован ли уже
    existing_user = db.get_user_by_telegram_id(user_id)

    if existing_user:
        await message.answer(
            "⚠️ Ты уже зарегистрирован!\n\n"
            f"📧 Email: <code>{existing_user['email']}</code>\n"
            f"🏢 Провайдер: {existing_user['email_provider']}\n\n"
            "Если хочешь изменить данные, сначала используй /unregister"
        )
        return

    # Отправляем инструкцию
    await message.answer(MESSAGES['register_start'])

    # Переводим пользователя в состояние ожидания данных
    await state.set_state(RegistrationStates.waiting_for_email_data)

    logger.info(f"📝 Пользователь {user_id} начал регистрацию")


@router.message(RegistrationStates.waiting_for_email_data)
async def process_email_data(message: Message, state: FSMContext):
    """
    Обработчик получения email и пароля.
    Формат: email@example.com пароль_приложения
    """
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"

    # Парсим введённые данные
    text = message.text.strip()
    parts = text.split()

    # Проверяем формат
    if len(parts) < 2:
        await message.answer(
            "❌ Неправильный формат!\n\n"
            "Отправь данные в формате:\n"
            "<code>email@example.com пароль_приложения</code>\n\n"
            "Пример:\n"
            "<code>ivan@gmail.com abcd efgh ijkl mnop</code>"
        )
        return

    email = parts[0]
    password = ' '.join(parts[1:])  # Пароль может содержать пробелы

    # Определяем провайдера по домену
    provider = detect_email_provider(email)

    if not provider:
        # Домен неизвестен - предлагаем выбрать платформу
        await state.update_data(email=email, password=password)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📧 Gmail", callback_data="platform_gmail"),
                InlineKeyboardButton(text="📧 Yandex", callback_data="platform_yandex")
            ],
            [
                InlineKeyboardButton(text="📧 Mail.ru", callback_data="platform_mail.ru"),
                InlineKeyboardButton(text="📧 Outlook", callback_data="platform_outlook")
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="register_cancel")
            ]
        ])

        domain = email.split('@')[1] if '@' in email else email

        await message.answer(
            f"🤔 Домен <code>@{domain}</code> не определён автоматически\n\n"
            f"📧 Email: <code>{email}</code>\n\n"
            f"<b>На базе какой платформы работает твоя почта?</b>\n\n"
            f"💡 Это нужно чтобы понять какой IMAP сервер использовать",
            reply_markup=keyboard
        )

        await state.set_state(RegistrationStates.choosing_provider)
        return

    # Провайдер определён - продолжаем регистрацию
    await complete_registration(message, state, email, password, provider, username, user_id)


@router.callback_query(F.data.startswith('platform_'))
async def process_platform_choice(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора платформы для корпоративной почты.
    """
    provider = callback.data.split('_')[1]

    # Получаем сохранённые данные
    data = await state.get_data()
    email = data['email']
    password = data['password']

    user_id = callback.from_user.id
    username = callback.from_user.username or f"user_{user_id}"

    await callback.message.edit_text(
        f"✅ Выбрана платформа: <b>{provider}</b>\n\n"
        f"🔄 Проверяю подключение к почте..."
    )

    await callback.answer()

    # Завершаем регистрацию
    await complete_registration(
        callback.message,
        state,
        email,
        password,
        provider,
        username,
        user_id,
        is_callback=True
    )


async def complete_registration(message: Message, state: FSMContext,
                                email: str, password: str, provider: str,
                                username: str, user_id: int, is_callback: bool = False):
    """
    Завершение процесса регистрации.

    Args:
        message: Объект сообщения
        state: Состояние FSM
        email: Email адрес
        password: Пароль приложения
        provider: Провайдер (gmail, yandex, mail.ru, outlook)
        username: Username пользователя
        user_id: Telegram ID
        is_callback: True если вызвано из callback (не нужно создавать новое сообщение)
    """
    # Отправляем сообщение о проверке (если это не callback)
    if not is_callback:
        checking_msg = await message.answer("🔄 Проверяю подключение к почте...")
    else:
        checking_msg = message

    # Проверяем подключение к почте
    parser = EmailParser(email, password, provider)

    if not parser.connect():
        await checking_msg.edit_text(
            "❌ Не удалось подключиться к почте!\n\n"
            "Возможные причины:\n"
            "• Неправильный пароль приложения\n"
            "• Не включен доступ по IMAP\n"
            "• Выбрана неправильная платформа\n\n"
            "Проверь данные и попробуй снова:\n"
            "/register"
        )
        await state.clear()
        return

    parser.disconnect()

    # Шифруем пароль
    encrypted_password = encrypt_password(password)

    # Сохраняем в БД
    success = db.add_user(
        telegram_id=user_id,
        username=username,
        email=email,
        encrypted_password=encrypted_password,
        email_provider=provider
    )

    if not success:
        await checking_msg.edit_text(
            "❌ Ошибка сохранения данных!\n"
            "Попробуй позже или обратись к администратору."
        )
        await state.clear()
        return

    # Успешная регистрация!
    await checking_msg.edit_text(
        "✅ <b>Регистрация успешна!</b>\n\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🏢 Провайдер: {provider}\n\n"
        "Теперь коллеги могут запросить доступ к твоим кодам через:\n"
        f"/request_access @{username}\n\n"
        "А ты можешь получать коды коллег (с их разрешения):\n"
        "/get_code @username"
    )

    # Очищаем состояние
    await state.clear()

    logger.info(f"✅ Пользователь {user_id} ({username}) зарегистрирован с {email} ({provider})")


@router.callback_query(F.data == 'register_cancel')
async def process_register_cancel(callback: CallbackQuery, state: FSMContext):
    """
    Отмена регистрации.
    """
    await callback.message.edit_text("❌ Регистрация отменена")
    await state.clear()
    await callback.answer()


def detect_email_provider(email: str) -> str:
    """
    Определить провайдера по email адресу.

    Args:
        email: Email адрес

    Returns:
        str: Название провайдера (gmail, yandex, mail.ru, outlook) или None
    """
    email = email.lower()

    if '@gmail.com' in email:
        return 'gmail'
    elif '@yandex.ru' in email or '@yandex.com' in email or '@yandex.kz' in email:
        return 'yandex'
    elif any(domain in email for domain in ['@mail.ru', '@bk.ru', '@inbox.ru', '@list.ru']):
        return 'mail.ru'
    elif '@outlook.com' in email or '@hotmail.com' in email or '@live.com' in email:
        return 'outlook'
    else:
        return None

# Оставь функции unregister без изменений
# (process_unregister_confirm, cmd_unregister и т.д.)