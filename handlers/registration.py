from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import MESSAGES, IMAP_SETTINGS
from database.db_manager import db
from utils.encryption import encrypt_password
from utils.email_parser import EmailParser

# Создаём роутер
router = Router()


# Определяем состояния для регистрации (FSM - Finite State Machine)
class RegistrationStates(StatesGroup):
    """
    Состояния процесса регистрации.
    Бот запоминает на каком этапе находится пользователь.
    """
    waiting_for_email_data = State()  # Ждём email и пароль


@router.message(Command('register'))
async def cmd_register(message: Message, state: FSMContext):
    """
    Обработчик команды /register
    Начинает процесс регистрации почты.

    Args:
        message: Сообщение от пользователя
        state: Контекст состояния FSM
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

    print(f"📝 Пользователь {user_id} начал регистрацию")


@router.message(RegistrationStates.waiting_for_email_data)
async def process_email_data(message: Message, state: FSMContext):
    """
    Обработчик получения email и пароля.
    Формат: email@example.com пароль_приложения

    Args:
        message: Сообщение с данными
        state: Контекст состояния
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
        await message.answer(
            "❌ Неподдерживаемый email провайдер!\n\n"
            "Поддерживаются:\n"
            "• Gmail (@gmail.com)\n"
            "• Yandex (@yandex.ru, @yandex.com)\n"
            "• Mail.ru (@mail.ru, @bk.ru, @inbox.ru, @list.ru)\n"
            "• Outlook (@outlook.com, @hotmail.com)"
        )
        return

    # Отправляем сообщение о проверке
    checking_msg = await message.answer("🔄 Проверяю подключение к почте...")

    # Проверяем подключение к почте
    parser = EmailParser(email, password, provider)

    if not parser.connect():
        await checking_msg.edit_text(
            "❌ Не удалось подключиться к почте!\n\n"
            "Возможные причины:\n"
            "• Неправильный пароль приложения\n"
            "• Не включен доступ по IMAP\n"
            "• Это не пароль приложения, а основной пароль\n\n"
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

    print(f"✅ Пользователь {user_id} ({username}) зарегистрирован с {email}")


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
    confirmed_user_id = int(callback.data.split('_')[2])

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

        print(f"🗑️ Пользователь {user_id} (@{username}) удалён из системы")
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
    elif '@yandex.ru' in email or '@yandex.com' in email:
        return 'yandex'
    elif any(domain in email for domain in ['@mail.ru', '@bk.ru', '@inbox.ru', '@list.ru']):
        return 'mail.ru'
    elif '@outlook.com' in email or '@hotmail.com' in email:
        return 'outlook'
    else:
        return None