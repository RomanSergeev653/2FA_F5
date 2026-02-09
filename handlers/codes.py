import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import time

from database.db_manager import db

# Создаём логгер для этого модуля
logger = logging.getLogger(__name__)
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
from utils.security import (
    validate_callback_data,
    check_rate_limit,
    RATE_LIMITS,
    sanitize_error_message
)

# Создаём роутер
router = Router()


# Состояния для получения кода
class GetCodeStates(StatesGroup):
    waiting_for_user_input = State()  # Ожидание ввода username или email


def is_email(text: str) -> bool:
    """
    Проверяет, является ли текст email адресом.
    Использует улучшенную валидацию из utils.security.
    
    Args:
        text: Текст для проверки
        
    Returns:
        bool: True если это похоже на email
    """
    from utils.security import validate_email
    return validate_email(text)


async def process_get_code(message: Message, target_input: str, requester: dict):
    """
    Обработка получения кода (общая логика для команды и состояния).
    
    Args:
        message: Сообщение от пользователя
        target_input: Username или email для поиска
        requester: Данные запрашивающего пользователя
    """
    requester_id = requester.get('telegram_id') if requester and isinstance(requester, dict) else None
    if not requester_id:
        logger.error(f"❌ [GET_CODE] Не удалось получить requester_id из requester: {type(requester)}")
        await message.answer("❌ Ошибка: не удалось получить ID пользователя")
        return
    
    requester_username = requester.get('username', 'unknown') if isinstance(requester, dict) else 'unknown'
    target_input = target_input.lstrip('@')
    is_email_input = is_email(target_input)
    
    logger.info(f"🔍 [GET_CODE] Начало обработки. Requester: {requester_id} (@{requester_username}), Target: {target_input} (email: {is_email_input})")

    # Проверяем, не пытается ли получить свой код (бессмысленно)
    if is_email_input:
        # Если это email, проверяем по email
        requester_email = requester.get('email', '') if isinstance(requester, dict) else ''
        if requester_email and target_input.lower() == requester_email.lower():
            await message.answer(
                "😅 Зачем получать свой код через бота?\n"
                "Он приходит тебе на почту напрямую!\n"
                "Попробуй /my_code"
            )
            return
    else:
        # Если это username, проверяем по username
        requester_username = requester.get('username', '') if isinstance(requester, dict) else ''
        if requester_username and target_input == requester_username:
            await message.answer(
                "😅 Зачем получать свой код через бота?\n"
                "Он приходит тебе на почту напрямую!\n"
                "Попробуй /my_code"
            )
            return

    # Ищем владельца кодов в БД
    logger.debug(f"🔍 [GET_CODE] Поиск owner в БД по {'email' if is_email_input else 'username'}: {target_input}")
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

    if not owner or not isinstance(owner, dict):
        logger.warning(f"⚠️  [GET_CODE] Owner не найден. Target: {target_input}, Requester: {requester_id}")
        await message.answer(not_found_message)
        return

    owner_id = owner.get('telegram_id')
    owner_username = owner.get('username', 'unknown')
    
    if not owner_id:
        logger.error(f"❌ [GET_CODE] Не удалось получить owner_id из owner: {type(owner)}")
        await message.answer("❌ Ошибка: не удалось получить ID владельца")
        return

    logger.info(f"👤 [GET_CODE] Owner найден: {owner_id} (@{owner_username})")

    # Проверяем разрешение
    logger.debug(f"🔐 [GET_CODE] Проверка разрешения: Owner {owner_id} → Requester {requester_id}")
    has_permission = db.check_permission(owner_id, requester_id)

    if not has_permission:
        logger.warning(f"🔒 [GET_CODE] Доступ запрещён. Owner: {owner_id} (@{owner_username}) → Requester: {requester_id} (@{requester_username})")
        await message.answer(
            f"🔒 <b>Доступ запрещён!</b>\n\n"
            f"У тебя нет разрешения на получение кодов от @{owner_username}\n\n"
            f"Запросить доступ:\n"
            f"<code>/request_access @{owner_username}</code>"
        )
        return

    logger.info(f"✅ [GET_CODE] Разрешение подтверждено. Начинаю поиск кода...")

    # Отправляем сообщение о поиске с прогрессом
    start_time = time.time()
    searching_msg = await message.answer(
        format_progress_message('searching', f"Ищу код в почте @{owner_username}...")
    )

    # Расшифровываем пароль владельца
    try:
        email = owner.get('email', '')
        encrypted_password = owner.get('encrypted_password', '')
        provider = owner.get('email_provider', '')
        
        if not email or not encrypted_password or not provider:
            logger.error(f"❌ [GET_CODE] Неполные данные owner в БД. Email: {bool(email)}, Password: {bool(encrypted_password)}, Provider: {bool(provider)}")
            await searching_msg.edit_text(
                "❌ Ошибка: неполные данные пользователя в базе данных"
            )
            return
        
        logger.debug(f"🔓 [GET_CODE] Расшифрование пароля для {email} ({provider})...")
        password = decrypt_password(encrypted_password)
        logger.debug(f"✅ [GET_CODE] Пароль расшифрован")

    except Exception as e:
        logger.error(f"❌ [GET_CODE] Ошибка расшифрования пароля: {type(e).__name__}: {e}", exc_info=True)
        from utils.security import sanitize_error_message
        safe_error = sanitize_error_message(e)
        await searching_msg.edit_text(
            "❌ Ошибка расшифрования данных!\n\n"
            f"{safe_error}"
        )
        return

    # Подключаемся к почте и ищем код
    try:
        logger.info(f"📧 [GET_CODE] Подключение к почте {email} ({provider})...")
        parser = EmailParser(email, password, provider)
        code = parser.get_latest_code()

        if code:
            search_time = time.time() - start_time
            logger.info(f"✅ [GET_CODE] Код найден! Время поиска: {search_time:.2f}с. Owner: @{owner_username}, Requester: @{requester_username}")
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
                requester_username = requester.get('username', 'unknown') if isinstance(requester, dict) else 'unknown'

                await bot_instance.send_message(
                    chat_id=owner_id,
                    text=(
                        f"ℹ️ @{requester_username} получил твой 2FA код\n"
                        f"🔐 Код: <code>{code}</code>"
                    )
                )
            except Exception as e:
                logger.warning(f"⚠️  [GET_CODE] Не удалось уведомить владельца: {type(e).__name__}: {e}")

            owner_username_log = owner.get('username', 'unknown') if isinstance(owner, dict) else 'unknown'
            requester_username_log = requester.get('username', 'unknown') if isinstance(requester, dict) else 'unknown'
            logger.info(f"✅ [GET_CODE] Код передан: @{owner_username_log} → @{requester_username_log} (код не логируется)")

        else:
            # Код не найден
            search_time = time.time() - start_time
            logger.warning(f"⚠️  [GET_CODE] Код не найден. Время поиска: {search_time:.2f}с. Owner: @{owner_username}, Requester: @{requester_username}")
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

    except Exception as e:
        # Логируем полную ошибку для администратора
        print(f"❌ Ошибка получения кода: {e}")
        
        # Пользователю показываем безопасное, но информативное сообщение
        safe_error = sanitize_error_message(e)
        suggestions = [
            "Проверить подключение к интернету",
            f"Связаться с @{owner_username} для проверки настроек",
            "Попробовать позже"
        ]
        error_text = format_error_message(
            error_type='connection',
            details=safe_error,
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

    # Проверяем rate limit
    allowed, remaining = check_rate_limit(requester_id, 'get_code', *RATE_LIMITS['get_code'])
    if not allowed:
        await message.answer(
            f"⏳ <b>Слишком много запросов!</b>\n\n"
            f"Подожди {remaining} секунд перед следующим запросом."
        )
        return

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
            owner_id = perm.get('owner_id') if isinstance(perm, dict) else None
            if not owner_id:
                continue
            owner = db.get_user_by_telegram_id(owner_id)
            if owner and isinstance(owner, dict):
                available_users.append({
                    'telegram_id': owner_id,
                    'username': owner.get('username', 'unknown'),
                    'email': owner.get('email', 'N/A')
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

    # Проверяем rate limit
    allowed, remaining = check_rate_limit(user_id, 'check_email', *RATE_LIMITS['check_email'])
    if not allowed:
        await message.answer(
            f"⏳ <b>Слишком много запросов!</b>\n\n"
            f"Подожди {remaining} секунд перед следующей проверкой."
        )
        return

    # Проверяем регистрацию
    user = db.get_user_by_telegram_id(user_id)
    if not user or not isinstance(user, dict):
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    checking_msg = await message.answer("🔄 Проверяю подключение к твоей почте...")

    try:
        # Расшифровываем данные
        email = user.get('email', '')
        encrypted_password = user.get('encrypted_password', '')
        provider = user.get('email_provider', '')
        
        if not email or not encrypted_password or not provider:
            await checking_msg.edit_text("❌ Ошибка: неполные данные в базе данных")
            return
        
        password = decrypt_password(encrypted_password)

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
        # Логируем полную ошибку
        logger.error(f"❌ [CHECK_EMAIL] Ошибка проверки почты: {type(e).__name__}: {e}", exc_info=True)
        
        # Пользователю показываем безопасное, но информативное сообщение
        safe_error = sanitize_error_message(e)
        await checking_msg.edit_text(
            "❌ Ошибка проверки подключения!\n\n"
            f"{safe_error}"
        )


@router.message(Command('my_code'))
async def cmd_test_code(message: Message):
    """
    Получение своего кода (потому что это удобно).
    """
    user_id = message.from_user.id

    # Проверяем rate limit
    allowed, remaining = check_rate_limit(user_id, 'my_code', *RATE_LIMITS['my_code'])
    if not allowed:
        await message.answer(
            f"⏳ <b>Слишком много запросов!</b>\n\n"
            f"Подожди {remaining} секунд перед следующим запросом."
        )
        return

    # Проверяем регистрацию
    user = db.get_user_by_telegram_id(user_id)
    if not user or not isinstance(user, dict):
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
        email = user.get('email', '')
        encrypted_password = user.get('encrypted_password', '')
        provider = user.get('email_provider', '')
        
        if not email or not encrypted_password or not provider:
            await searching_msg.edit_text("❌ Ошибка: неполные данные в базе данных")
            return
        
        password = decrypt_password(encrypted_password)

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
        # Логируем полную ошибку
        logger.error(f"❌ [MY_CODE] Ошибка теста: {type(e).__name__}: {e}", exc_info=True)
        
        # Пользователю показываем безопасное сообщение
        safe_error = sanitize_error_message(e)
        await searching_msg.edit_text(
            f"❌ Ошибка при тестировании\n\n"
            f"{safe_error}"
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
    
    # Безопасно извлекаем ID владельца из callback_data
    owner_id = validate_callback_data(callback.data, "get_code_")
    if not owner_id:
        await callback.answer("❌ Неверный запрос!", show_alert=True)
        return
    
    owner = db.get_user_by_telegram_id(owner_id)
    if not owner or not isinstance(owner, dict):
        await callback.answer("Пользователь не найден!", show_alert=True)
        return
    
    # КРИТИЧНО: Проверяем права доступа перед получением кода
    has_permission = db.check_permission(owner_id, requester_id)
    if not has_permission:
        owner_username = owner.get('username', 'unknown') if isinstance(owner, dict) else 'unknown'
        await callback.answer(
            f"🔒 У тебя нет доступа к кодам @{owner_username}!", 
            show_alert=True
        )
        return
    
    # Проверяем rate limit
    allowed, remaining = check_rate_limit(requester_id, 'get_code', *RATE_LIMITS['get_code'])
    if not allowed:
        await callback.answer(
            f"⏳ Слишком много запросов! Подожди {remaining} сек.", 
            show_alert=True
        )
        return
    
    await callback.answer("Ищу код...")
    
    # Создаём временное сообщение для обработки
    owner_username = owner.get('username', 'unknown') if isinstance(owner, dict) else 'unknown'
    await callback.message.edit_text(
        format_progress_message('searching', f"Ищу код в почте @{owner_username}...")
    )
    
    # Обрабатываем получение кода
    await process_get_code(callback.message, owner_username, requester)


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
    
    # Безопасно извлекаем номер страницы
    try:
        page_str = callback.data.split("_")[-1]
        if not page_str.isdigit():
            await callback.answer("Неверный запрос!", show_alert=True)
            return
        page = int(page_str)
        if page < 0:
            page = 0
    except (ValueError, IndexError):
        await callback.answer("Неверный запрос!", show_alert=True)
        return
    
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