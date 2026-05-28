from typing import Awaitable, Callable

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
from utils.messages import (
    format_registration_success,
    format_error_message
)
from utils.keyboards import (
    create_error_keyboard
)
from utils.security import (
    validate_callback_data,
    validate_email,
    check_rate_limit,
    RATE_LIMITS,
    sanitize_error_message
)

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


async def prompt_registration(
    user_id: int,
    state: FSMContext,
    send_text: Callable[[str], Awaitable],
) -> bool:
    """
    Показать инструкцию и перевести пользователя в режим ожидания данных.
    Returns True если регистрация начата.
    """
    allowed, remaining = check_rate_limit(user_id, 'register', *RATE_LIMITS['register'])
    if not allowed:
        await send_text(
            f"⏳ <b>Слишком много попыток регистрации!</b>\n\n"
            f"Подожди {remaining} секунд перед следующей попыткой."
        )
        return False

    existing_user = db.get_user_by_telegram_id(user_id)
    if existing_user:
        await send_text(
            "⚠️ Ты уже зарегистрирован!\n\n"
            f"📧 Email: <code>{existing_user['email']}</code>\n"
            f"🏢 Провайдер: {existing_user['email_provider']}\n\n"
            "Если хочешь изменить данные, сначала используй /unregister"
        )
        return False

    await send_text(MESSAGES['register_start'])
    await state.set_state(RegistrationStates.waiting_for_email_data)
    logger.info(f"📝 Пользователь {user_id} начал регистрацию")
    return True


@router.message(Command('register'))
async def cmd_register(message: Message, state: FSMContext):
    """
    Обработчик команды /register
    Начинает процесс регистрации почты.
    """
    user_id = message.from_user.id

    async def send_text(text: str) -> None:
        await message.answer(text)

    await prompt_registration(user_id, state, send_text)


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
        suggestions = [
            "Использовать формат: email@example.com пароль_приложения",
            "Убедиться, что пароль приложения скопирован полностью",
            "Проверить, что между email и паролем есть пробел"
        ]
        error_text = format_error_message(
            error_type='validation',
            details="Неправильный формат данных",
            suggestions=suggestions
        )
        error_text += (
            "\n\n<b>Правильный формат:</b>\n"
            "<code>email@example.com пароль_приложения</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>ivan@gmail.com abcd efgh ijkl mnop</code>"
        )
        keyboard = create_error_keyboard(action="register", show_help=False)
        
        await message.answer(
            text=error_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return

    email = parts[0].strip().lower()
    password = ' '.join(parts[1:])  # Пароль может содержать пробелы

    # Валидируем email
    if not validate_email(email):
        suggestions = [
            "Проверить правильность написания email",
            "Убедиться, что email содержит @ и домен",
            "Пример правильного формата: user@example.com"
        ]
        error_text = format_error_message(
            error_type='validation',
            details="Некорректный email адрес",
            suggestions=suggestions
        )
        keyboard = create_error_keyboard(action="register", show_help=False)
        
        await message.answer(
            text=error_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return

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
    # Безопасно извлекаем провайдера
    if not callback.data.startswith('platform_'):
        await callback.answer("❌ Неверный запрос!", show_alert=True)
        return
    
    provider = callback.data.replace('platform_', '', 1)
    
    # Валидируем провайдера
    valid_providers = ['gmail', 'yandex', 'mail.ru', 'outlook']
    if provider not in valid_providers:
        await callback.answer("❌ Неверный провайдер!", show_alert=True)
        return

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

    try:
        if not parser.connect():
            suggestions = [
                "Проверить правильность пароля приложения",
                "Убедиться, что IMAP доступ включен в настройках почты",
                "Проверить правильность выбранной платформы",
                "Попробовать создать новый пароль приложения"
            ]
            error_text = format_error_message(
                error_type='connection',
                details="Не удалось подключиться к почте",
                suggestions=suggestions
            )
            keyboard = create_error_keyboard(action="register", show_help=True)
            
            await checking_msg.edit_text(
                text=error_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            await state.clear()
            return
    except Exception as e:
        # Логируем полную ошибку
        print(f"❌ Ошибка подключения к почте: {e}")
        
        # Пользователю показываем безопасное, но информативное сообщение
        from utils.security import sanitize_error_message
        safe_error = sanitize_error_message(e)
        suggestions = [
            "Проверить подключение к интернету",
            "Попробовать позже",
            "Обратиться к администратору"
        ]
        error_text = format_error_message(
            error_type='connection',
            details=safe_error,
            suggestions=suggestions
        )
        keyboard = create_error_keyboard(action="register", show_help=True)
        
        await checking_msg.edit_text(
            text=error_text,
            parse_mode='HTML',
            reply_markup=keyboard
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
        # Логируем для администратора (без деталей)
        print(f"❌ Ошибка сохранения пользователя {user_id} в БД")
        
        suggestions = [
            "Попробовать позже",
            "Обратиться к администратору"
        ]
        error_text = format_error_message(
            error_type='generic',
            details="Ошибка сохранения данных",
            suggestions=suggestions
        )
        keyboard = create_error_keyboard(action="register", show_help=True)
        
        await checking_msg.edit_text(
            text=error_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        await state.clear()
        return

    # Успешная регистрация!
    success_text = format_registration_success(
        email=email,
        provider=provider,
        username=username
    )
    
    await checking_msg.edit_text(
        text=success_text,
        parse_mode='HTML'
    )

    # Очищаем состояние
    await state.clear()

    logger.info(f"✅ Пользователь {user_id} ({username}) зарегистрирован с {email} ({provider})")


@router.callback_query(F.data == 'retry_register')
async def callback_retry_register(callback: CallbackQuery, state: FSMContext):
    """Повторная попытка регистрации после ошибки."""
    await callback.answer()

    async def send_text(text: str) -> None:
        await callback.message.answer(text)

    await prompt_registration(callback.from_user.id, state, send_text)


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


@router.message(Command('unregister'))
async def cmd_unregister(message: Message, state: FSMContext):
    """
    Удаление своих данных из бота.
    Требует подтверждения через кнопки.
    """
    user_id = message.from_user.id

    # Проверяем, зарегистрирован ли пользователь
    user = db.get_user_by_telegram_id(user_id)

    if not user:
        await message.answer(
            "❌ Ты не зарегистрирован в боте!\n"
            "Нечего удалять 🤷"
        )
        return

    # Получаем информацию о разрешениях
    permissions = db.get_my_permissions(user_id)
    given_count = len(permissions['given'])
    received_count = len(permissions['received'])

    # Формируем предупреждение
    warning_text = (
        "⚠️ <b>Удаление данных</b>\n\n"
        f"📧 Email: <code>{user['email']}</code>\n"
        f"🏢 Провайдер: {user['email_provider']}\n\n"
        f"<b>Будут удалены:</b>\n"
        f"• Твои данные для входа в почту\n"
        f"• Все разрешения ({given_count + received_count} шт.)\n"
        f"• История действий\n\n"
    )

    # Добавляем предупреждения о разрешениях
    if given_count > 0:
        warning_text += (
            f"⚠️ <b>Внимание!</b> {given_count} чел. имеют доступ к твоим кодам:\n"
        )
        for perm in permissions['given'][:5]:  # Показываем первых 5
            warning_text += f"  • @{perm['requester_username']}\n"
        if given_count > 5:
            warning_text += f"  ... и ещё {given_count - 5}\n"
        warning_text += "\n"

    if received_count > 0:
        warning_text += (
            f"⚠️ Ты потеряешь доступ к кодам {received_count} чел.\n\n"
        )

    warning_text += (
        "<b>Это действие нельзя отменить!</b>\n\n"
        "Ты уверен?"
    )

    # Создаём кнопки подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=f"unregister_confirm_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Нет, отменить",
                callback_data="unregister_cancel"
            )
        ]
    ])

    await message.answer(
        text=warning_text,
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith('unregister_confirm_'))
async def process_unregister_confirm(callback: CallbackQuery):
    """
    Обработчик подтверждения удаления.
    """
    user_id = callback.from_user.id
    
    # Безопасно извлекаем ID пользователя
    confirmed_user_id = validate_callback_data(callback.data, "unregister_confirm_")
    if not confirmed_user_id:
        await callback.answer("❌ Неверный запрос!", show_alert=True)
        return

    # Проверка безопасности: удалять может только сам пользователь
    if user_id != confirmed_user_id:
        await callback.answer("❌ Ошибка авторизации!", show_alert=True)
        return

    # Получаем данные перед удалением (для уведомлений)
    user = db.get_user_by_telegram_id(user_id)
    permissions = db.get_my_permissions(user_id)

    if not user:
        await callback.message.edit_text("❌ Данные уже удалены!")
        return

    username = user['username']

    # Уведомляем тех, кто имел доступ к кодам этого пользователя
    for perm in permissions['given']:
        try:
            bot_instance = callback.bot
            requester_id = perm['requester_id']

            await bot_instance.send_message(
                chat_id=requester_id,
                text=(
                    f"⚠️ <b>Доступ потерян</b>\n\n"
                    f"@{username} удалил свои данные из бота.\n"
                    f"Ты больше не можешь получать его коды."
                )
            )
        except Exception as e:
            print(f"⚠️ Не удалось уведомить пользователя {requester_id}: {e}")

    # Уведомляем тех, к чьим кодам имел доступ этот пользователь
    for perm in permissions['received']:
        try:
            bot_instance = callback.bot
            owner_id = perm['owner_id']

            await bot_instance.send_message(
                chat_id=owner_id,
                text=(
                    f"ℹ️ @{username} удалил свои данные из бота.\n"
                    f"Разрешение для него автоматически удалено."
                )
            )
        except Exception as e:
            print(f"⚠️ Не удалось уведомить пользователя {owner_id}: {e}")

    # Удаляем данные из БД
    success = db.delete_user(user_id)

    if success:
        await callback.message.edit_text(
            "✅ <b>Данные удалены</b>\n\n"
            "Твои данные полностью удалены из бота:\n"
            "• Email и пароль\n"
            "• Все разрешения\n"
            "• История действий\n\n"
            "Чтобы снова использовать бота:\n"
            "/register"
        )

        logger.info(f"🗑️ Пользователь {user_id} (@{username}) удалён из системы")
    else:
        await callback.message.edit_text(
            "❌ Ошибка удаления данных!\n"
            "Попробуй позже или обратись к администратору."
        )

    await callback.answer()


@router.callback_query(F.data == 'unregister_cancel')
async def process_unregister_cancel(callback: CallbackQuery):
    """
    Обработчик отмены удаления.
    """
    await callback.message.edit_text(
        "✅ Удаление отменено!\n\n"
        "Твои данные в безопасности 🔒"
    )

    await callback.answer("Отменено")