from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import time

from database.db_manager import db
from utils.encryption import decrypt_password
from utils.email_parser import EmailParser
from utils.keyboards import (
    create_user_list_keyboard,
    create_code_result_keyboard,
    create_error_keyboard
)
from utils.messages import (
    format_code_result,
    format_code_not_found,
    format_error_message,
    format_user_list_message,
    format_progress_message
)

# Создаём роутер
router = Router()


# Состояния для получения кода
class GetCodeStates(StatesGroup):
    waiting_for_user_input = State()  # Ожидание ввода username или email


def is_email(text: str) -> bool:
    """
    Проверяет, является ли текст email адресом.
    
    Args:
        text: Текст для проверки
        
    Returns:
        bool: True если это похоже на email
    """
    if '@' not in text:
        return False
    
    parts = text.split('@')
    if len(parts) != 2:
        return False
    
    # Проверяем, что после @ есть точка и домен
    domain = parts[1]
    return '.' in domain and len(domain.split('.')[-1]) >= 2


async def process_get_code(message: Message, target_input: str, requester: dict):
    """
    Обработка получения кода (общая логика для команды и состояния).
    
    Args:
        message: Сообщение от пользователя
        target_input: Username или email для поиска
        requester: Данные запрашивающего пользователя
    """
    requester_id = requester['telegram_id']
    target_input = target_input.lstrip('@')
    is_email_input = is_email(target_input)

    # Проверяем, не пытается ли получить свой код (бессмысленно)
    if is_email_input:
        # Если это email, проверяем по email
        if target_input.lower() == requester['email'].lower():
            await message.answer(
                "😅 Зачем получать свой код через бота?\n"
                "Он приходит тебе на почту напрямую!\n"
                "Попробуй /my_code"
            )
            return
    else:
        # Если это username, проверяем по username
        if target_input == requester['username']:
            await message.answer(
                "😅 Зачем получать свой код через бота?\n"
                "Он приходит тебе на почту напрямую!\n"
                "Попробуй /my_code"
            )
            return

    # Ищем владельца кодов в БД
    if is_email_input:
        owner = db.get_user_by_email(target_input)
        not_found_message = (
            f"❌ Пользователь с email <code>{target_input}</code> не найден!\n\n"
            "Возможные причины:\n"
            "• Пользователь не зарегистрирован в боте\n"
            "• Неправильно указан email\n\n"
            "Попроси коллегу использовать /register"
        )
    else:
        owner = db.get_user_by_username(target_input)
        not_found_message = (
            f"❌ Пользователь @{target_input} не найден!\n\n"
            "Возможные причины:\n"
            "• Пользователь не зарегистрирован в боте\n"
            "• Неправильно указан username\n\n"
            "Попробуй использовать email:\n"
            f"<code>/get_code email@example.com</code>\n\n"
            "Или попроси коллегу использовать /register"
        )

    if not owner:
        await message.answer(not_found_message)
        return

    owner_id = owner['telegram_id']
    owner_username = owner['username']

    # Проверяем разрешение
    has_permission = db.check_permission(owner_id, requester_id)

    if not has_permission:
        await message.answer(
            f"🔒 <b>Доступ запрещён!</b>\n\n"
            f"У тебя нет разрешения на получение кодов от @{owner_username}\n\n"
            f"Запросить доступ:\n"
            f"<code>/request_access @{owner_username}</code>"
        )
        return

    # Отправляем сообщение о поиске с прогрессом
    start_time = time.time()
    searching_msg = await message.answer(
        format_progress_message('searching', f"Ищу код в почте @{owner_username}...")
    )

    # Расшифровываем пароль владельца
    try:
        email = owner['email']
        encrypted_password = owner['encrypted_password']
        password = decrypt_password(encrypted_password)
        provider = owner['email_provider']

    except Exception as e:
        print(f"❌ Ошибка расшифрования пароля: {e}")
        await searching_msg.edit_text(
            "❌ Ошибка расшифрования данных!\n"
            "Обратись к администратору."
        )
        return

    # Подключаемся к почте и ищем код
    try:
        parser = EmailParser(email, password, provider)
        code = parser.get_latest_code()

        if code:
            # Код найден!
            search_time = time.time() - start_time
            result_text = format_code_result(
                code=code,
                owner_username=owner_username,
                owner_email=email,
                search_time=search_time
            )
            keyboard = create_code_result_keyboard(
                owner_username=owner_username,
                owner_id=owner_id,
                can_retry=True
            )
            
            await searching_msg.edit_text(
                text=result_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )

            # Обновляем время последнего запроса
            db.update_last_code_request(owner_id)

            # Логируем
            db.log_action(
                user_id=requester_id,
                action_type='code_retrieved',
                details=f'Got code from {owner_username}'
            )

            # Уведомляем владельца (опционально)
            try:
                bot_instance = message.bot
                requester_username = requester['username']

                await bot_instance.send_message(
                    chat_id=owner_id,
                    text=(
                        f"ℹ️ @{requester_username} получил твой 2FA код\n"
                        f"🔐 Код: <code>{code}</code>"
                    )
                )
            except Exception as e:
                print(f"⚠️ Не удалось уведомить владельца: {e}")

            print(f"✅ Код передан: {owner['username']} → {requester['username']} | Код: НЕ ЛОГИРУЕТСЯ")

        else:
            # Код не найден
            suggestions = [
                "Подождать несколько секунд",
                "Попросить коллегу запросить новый код",
                f"Повторить команду: /get_code @{owner_username}"
            ]
            not_found_text = format_code_not_found(
                owner_username=owner_username,
                suggestions=suggestions
            )
            keyboard = create_code_result_keyboard(
                owner_username=owner_username,
                owner_id=owner_id,
                can_retry=True
            )
            
            await searching_msg.edit_text(
                text=not_found_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )

            print(f"⚠️ Код не найден для {owner['username']}")

    except Exception as e:
        print(f"❌ Ошибка получения кода: {e}")
        suggestions = [
            "Проверить подключение к интернету",
            f"Связаться с @{owner_username} для проверки настроек",
            "Попробовать позже"
        ]
        error_text = format_error_message(
            error_type='connection',
            details=f"Ошибка при получении кода от @{owner_username}",
            suggestions=suggestions
        )
        keyboard = create_error_keyboard(action="get_code", show_help=True)
        
        await searching_msg.edit_text(
            text=error_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )


@router.message(Command('get_code'))
async def cmd_get_code(message: Message, state: FSMContext):
    """
    Получить последний 2FA код от коллеги.
    Формат: /get_code @username или /get_code email@example.com

    Args:
        message: Сообщение от пользователя
        state: Контекст состояния FSM
    """
    requester_id = message.from_user.id

    # Проверяем регистрацию запрашивающего
    requester = db.get_user_by_telegram_id(requester_id)
    if not requester:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    # Проверяем аргументы команды
    args = message.text.split()

    if len(args) < 2:
        # Нет аргументов - показываем список доступных пользователей
        permissions = db.get_my_permissions(requester_id)
        received = permissions.get('received', [])
        
        if not received:
            await message.answer(
                "📭 <b>Нет доступных пользователей</b>\n\n"
                "У тебя пока нет разрешений на получение кодов.\n\n"
                "Запроси доступ:\n"
                "<code>/request_access @username</code>\n"
                "или\n"
                "<code>/request_access email@example.com</code>"
            )
            return
        
        # Формируем список пользователей с разрешениями
        available_users = []
        for perm in received:
            owner_id = perm['owner_id']
            owner = db.get_user_by_telegram_id(owner_id)
            if owner:
                available_users.append({
                    'telegram_id': owner_id,
                    'username': owner['username'],
                    'email': owner['email']
                })
        
        if not available_users:
            await message.answer(
                "📭 <b>Нет доступных пользователей</b>\n\n"
                "Пользователи, давшие тебе доступ, больше не зарегистрированы."
            )
            return
        
        # Показываем список с кнопками
        list_text = format_user_list_message(available_users, action="get_code")
        keyboard = create_user_list_keyboard(available_users, action="get_code")
        
        await message.answer(
            text=list_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return

    target_input = args[1]
    await process_get_code(message, target_input, requester)


@router.message(GetCodeStates.waiting_for_user_input)
async def process_user_input(message: Message, state: FSMContext):
    """
    Обработчик ввода username или email для получения кода.
    
    Args:
        message: Сообщение с введенным username/email
        state: Контекст состояния FSM
    """
    requester_id = message.from_user.id

    # Проверяем регистрацию запрашивающего
    requester = db.get_user_by_telegram_id(requester_id)
    if not requester:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        await state.clear()
        return

    # Получаем введенный текст
    target_input = message.text.strip()
    
    # Очищаем состояние
    await state.clear()
    
    # Обрабатываем запрос кода
    await process_get_code(message, target_input, requester)


@router.message(Command('check_email'))
async def cmd_check_email(message: Message):
    """
    Проверить своё подключение к почте (для отладки).
    """
    user_id = message.from_user.id

    # Проверяем регистрацию
    user = db.get_user_by_telegram_id(user_id)
    if not user:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    checking_msg = await message.answer("🔄 Проверяю подключение к твоей почте...")

    try:
        # Расшифровываем данные
        email = user['email']
        encrypted_password = user['encrypted_password']
        password = decrypt_password(encrypted_password)
        provider = user['email_provider']

        # Пробуем подключиться
        parser = EmailParser(email, password, provider)

        if parser.connect():
            parser.disconnect()

            await checking_msg.edit_text(
                "✅ <b>Подключение успешно!</b>\n\n"
                f"📧 Email: <code>{email}</code>\n"
                f"🏢 Провайдер: {provider}\n"
                f"🔐 Доступ к почте работает\n\n"
                "Коллеги смогут получать твои коды!"
            )
        else:
            await checking_msg.edit_text(
                "❌ <b>Не удалось подключиться!</b>\n\n"
                f"📧 Email: <code>{email}</code>\n"
                f"🏢 Провайдер: {provider}\n\n"
                "Возможные причины:\n"
                "• Изменился пароль приложения\n"
                "• Отключен IMAP доступ\n"
                "• Проблемы у провайдера\n\n"
                "Попробуй перерегистрироваться: /register"
            )

    except Exception as e:
        print(f"❌ Ошибка проверки почты: {e}")
        await checking_msg.edit_text(
            "❌ Ошибка проверки!\n"
            "Обратись к администратору."
        )


@router.message(Command('my_code'))
async def cmd_test_code(message: Message):
    """
    Получение своего кода (потому что это удобно).
    """
    user_id = message.from_user.id

    # Проверяем регистрацию
    user = db.get_user_by_telegram_id(user_id)
    if not user:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    searching_msg = await message.answer(
        "🔍 Ищу код в твоей почте...\n"
        "⏳ Это тестовый режим"
    )

    try:
        # Расшифровываем данные
        email = user['email']
        encrypted_password = user['encrypted_password']
        password = decrypt_password(encrypted_password)
        provider = user['email_provider']

        # Ищем код
        parser = EmailParser(email, password, provider)
        code = parser.get_latest_code()

        if code:
            await searching_msg.edit_text(
                f"✅ <b>Тест успешен!</b>\n\n"
                f"🔐 Найден код: <code>{code}</code>\n\n"
                f"Это твой собственный код из твоей почты.\n"
                f"Всё работает правильно! ✨"
            )
        else:
            await searching_msg.edit_text(
                f"⚠️ <b>Коды не найдены</b>\n\n"
                f"В последних письмах нет 2FA кодов.\n\n"
                f"Попробуй:\n"
                f"1. Запроси 2FA код на свою почту\n"
                f"2. Подожди несколько секунд\n"
                f"3. Повтори команду /test_code"
            )

    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        await searching_msg.edit_text(
            f"❌ Ошибка при тестировании:\n"
            f"<code>{str(e)}</code>"
        )


@router.message(F.text.regexp(r'^@[\w]+$'))
async def handle_username_mention(message: Message):
    """
    Обработчик упоминания @username.
    Автоматически получает код для указанного пользователя.

    Работает как: /get_code @username
    """
    requester_id = message.from_user.id

    # Проверяем регистрацию запрашивающего
    requester = db.get_user_by_telegram_id(requester_id)
    if not requester:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    username_mention = message.text.strip()
    await process_get_code(message, username_mention, requester)


# Обработчики callback для кнопок
@router.callback_query(F.data.startswith("get_code_"))
async def callback_get_code(callback: CallbackQuery):
    """
    Обработчик кнопки получения кода из списка пользователей.
    """
    requester_id = callback.from_user.id
    
    # Проверяем регистрацию
    requester = db.get_user_by_telegram_id(requester_id)
    if not requester:
        await callback.answer("Сначала зарегистрируйся!", show_alert=True)
        return
    
    # Извлекаем ID владельца из callback_data
    owner_id = int(callback.data.split("_")[-1])
    owner = db.get_user_by_telegram_id(owner_id)
    
    if not owner:
        await callback.answer("Пользователь не найден!", show_alert=True)
        return
    
    await callback.answer("Ищу код...")
    
    # Создаём временное сообщение для обработки
    # Используем edit_text для обновления текущего сообщения
    await callback.message.edit_text(
        format_progress_message('searching', f"Ищу код в почте @{owner['username']}...")
    )
    
    # Обрабатываем получение кода
    await process_get_code(callback.message, owner['username'], requester)


@router.callback_query(F.data.startswith("get_code_page_"))
async def callback_get_code_page(callback: CallbackQuery):
    """
    Обработчик пагинации списка пользователей для получения кода.
    """
    requester_id = callback.from_user.id
    requester = db.get_user_by_telegram_id(requester_id)
    
    if not requester:
        await callback.answer("Сначала зарегистрируйся!", show_alert=True)
        return
    
    # Извлекаем номер страницы
    page = int(callback.data.split("_")[-1])
    
    # Получаем список доступных пользователей
    permissions = db.get_my_permissions(requester_id)
    received = permissions.get('received', [])
    
    available_users = []
    for perm in received:
        owner_id = perm['owner_id']
        owner = db.get_user_by_telegram_id(owner_id)
        if owner:
            available_users.append({
                'telegram_id': owner_id,
                'username': owner['username'],
                'email': owner['email']
            })
    
    if not available_users:
        await callback.answer("Нет доступных пользователей", show_alert=True)
        return
    
    # Вычисляем количество страниц
    per_page = 5
    total_pages = (len(available_users) + per_page - 1) // per_page
    
    # Показываем нужную страницу
    list_text = format_user_list_message(
        available_users[page * per_page:(page + 1) * per_page],
        action="get_code",
        page=page,
        total_pages=total_pages
    )
    keyboard = create_user_list_keyboard(
        available_users,
        action="get_code",
        page=page,
        per_page=per_page
    )
    
    await callback.message.edit_text(
        text=list_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "retry_get_code")
async def callback_retry_get_code(callback: CallbackQuery):
    """
    Обработчик кнопки "Попробовать снова" после ошибки.
    """
    await callback.answer("Используй /get_code для повторной попытки")
    await callback.message.answer(
        "Используй команду /get_code для получения кода"
    )