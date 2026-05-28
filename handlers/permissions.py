import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db_manager import db
from database.models import get_connection

# Создаём логгер для этого модуля
logger = logging.getLogger(__name__)
from utils.keyboards import (
    create_permissions_keyboard,
    create_confirm_keyboard
)
from utils.messages import (
    format_permission_request,
    format_permission_granted,
    format_request_access_hint,
    REQUEST_ACCESS_SOLO_MESSAGE,
)
from utils.security import (
    validate_callback_data,
    validate_email,
    check_rate_limit,
    RATE_LIMITS,
    sanitize_error_message
)


def is_email(text: str) -> bool:
    """
    Проверяет, является ли текст email адресом.
    Использует улучшенную валидацию из utils.security.
    
    Args:
        text: Текст для проверки
        
    Returns:
        bool: True если это похоже на email
    """
    return validate_email(text)


# Создаём роутер
router = Router()


# Состояния для запроса доступа
class PermissionStates(StatesGroup):
    waiting_for_username = State()


@router.message(Command('request_access'))
async def cmd_request_access(message: Message, state: FSMContext):
    """
    Команда для запроса доступа к кодам коллеги.
    Формат: /request_access @username

    Args:
        message: Сообщение от пользователя
        state: Контекст состояния
    """
    requester_id = message.from_user.id
    logger.info(f"📝 [REQUEST_ACCESS] Команда от пользователя {requester_id}")

    # Проверяем rate limit
    allowed, remaining = check_rate_limit(
        requester_id, 
        'request_access', 
        *RATE_LIMITS['request_access']
    )
    if not allowed:
        await message.answer(
            f"⏳ <b>Слишком много запросов!</b>\n\n"
            f"Подожди {remaining} секунд перед следующим запросом."
        )
        return

    # Проверяем, зарегистрирован ли запрашивающий
    requester = db.get_user_by_telegram_id(requester_id)
    if not requester:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    # Проверяем, указан ли username или email в команде
    args = message.text.split()

    if len(args) < 2:
        try:
            total = db.count_registered_users()
        except Exception as e:
            logger.error(
                f"❌ [REQUEST_ACCESS] Ошибка подсчёта пользователей: {type(e).__name__}: {e}",
                exc_info=True,
            )
            safe_error = sanitize_error_message(e)
            await message.answer(
                "❌ Не удалось получить статистику бота.\n\n"
                f"{safe_error}\n\n"
                "Укажи username или email напрямую:\n"
                "<code>/request_access @username</code>"
            )
            return

        if total <= 1:
            await message.answer(REQUEST_ACCESS_SOLO_MESSAGE, parse_mode='HTML')
            return

        await message.answer(
            format_request_access_hint(total),
            parse_mode='HTML',
        )
        return

    target_input = args[1].lstrip('@')
    is_email_input = is_email(target_input)

    # Проверяем, не себя ли запрашивает
    if is_email_input:
        # Если это email, проверяем по email
        requester_email = requester.get('email', '') if requester and isinstance(requester, dict) else ''
        if requester_email and target_input.lower() == requester_email.lower():
            await message.answer("😅 Нельзя запросить доступ к своим кодам!")
            return
    else:
        # Если это username, проверяем по username
        requester_username = requester.get('username', '') if requester and isinstance(requester, dict) else ''
        if requester_username and target_input == requester_username:
            await message.answer("😅 Нельзя запросить доступ к своим кодам!")
            return

    # Ищем пользователя в БД
    if is_email_input:
        owner = db.get_user_by_email(target_input)
        not_found_message = (
            f"❌ Пользователь с email <code>{target_input}</code> не найден!\n\n"
            "Возможные причины:\n"
            "• Пользователь ещё не зарегистрирован в боте\n"
            "• Неправильно указан email\n\n"
            "Попробуй использовать username:\n"
            "<code>/request_access @username</code>\n\n"
            "Или попроси коллегу использовать /register"
        )
    else:
        owner = db.get_user_by_username(target_input)
        not_found_message = (
            f"❌ Пользователь @{target_input} не найден!\n\n"
            "Возможные причины:\n"
            "• Пользователь ещё не зарегистрирован в боте\n"
            "• Неправильно указан username\n\n"
            "Попробуй использовать email:\n"
            "<code>/request_access email@example.com</code>\n\n"
            "Или попроси коллегу использовать /register"
        )

    if not owner or not isinstance(owner, dict):
        await message.answer(not_found_message)
        return

    owner_username = owner.get('username', 'unknown')
    owner_id = owner.get('telegram_id')
    
    if not owner_id:
        await message.answer("❌ Ошибка: не удалось получить ID пользователя")
        return

    # Проверяем, нет ли уже разрешения
    if db.check_permission(owner_id, requester_id):
        owner_email = owner.get('email', 'N/A') if isinstance(owner, dict) else 'N/A'
        await message.answer(
            f"✅ У тебя уже есть доступ к кодам @{owner_username}!\n\n"
            f"Получить код:\n"
            f"<code>/get_code @{owner_username}</code>\n"
            f"<code>/get_code {owner_email}</code>"
        )
        return

    # Создаём запрос в БД
    success = db.create_permission_request(owner_id, requester_id)

    if not success:
        await message.answer(
            "⚠️ Запрос уже отправлен ранее!\n"
            "Ожидай ответа от коллеги."
        )
        return

    # Отправляем уведомление владельцу
    requester_username = requester.get('username', 'unknown') if requester and isinstance(requester, dict) else 'unknown'
    requester_email = requester.get('email', 'N/A') if requester and isinstance(requester, dict) else 'N/A'
    requester_name = message.from_user.first_name or requester_username

    # Создаём кнопки для ответа
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Разрешить",
                callback_data=f"perm_approve_{requester_id}"
            ),
            InlineKeyboardButton(
                text="❌ Запретить",
                callback_data=f"perm_deny_{requester_id}"
            )
        ]
    ])

    # Отправляем уведомление владельцу через бота
    try:
        bot_instance = message.bot

        notification_text = (
            f"🔔 <b>Запрос доступа к твоим 2FA кодам</b>\n\n"
            f"👤 От: @{requester_username} ({requester_name})\n"
            f"📧 Email: {requester_email}\n\n"
            f"Разрешить доступ?"
        )

        await bot_instance.send_message(
            chat_id=owner_id,
            text=notification_text,
            reply_markup=keyboard
        )

        await message.answer(
            f"✅ Запрос отправлен @{owner_username}!\n"
            f"Ожидай ответа."
        )

        logger.info(f"📤 [REQUEST_ACCESS] Запрос доступа отправлен: @{requester_username} → @{owner_username}")

    except Exception as e:
        logger.error(f"❌ [REQUEST_ACCESS] Ошибка отправки уведомления: {type(e).__name__}: {e}", exc_info=True)
        await message.answer(
            "⚠️ Запрос создан, но не удалось уведомить коллегу.\n"
            "Свяжись с ним напрямую."
        )


@router.callback_query(F.data.startswith('perm_approve_'))
async def process_approve(callback: CallbackQuery):
    """
    Обработчик кнопки "Разрешить".

    Args:
        callback: Callback от нажатия кнопки
    """
    owner_id = callback.from_user.id
    logger.info(f"🔔 [PERM_APPROVE] Начало обработки. Owner ID: {owner_id}, Callback data: {callback.data}")
    
    # Безопасно извлекаем ID запрашивающего
    requester_id = validate_callback_data(callback.data, "perm_approve_")
    if not requester_id:
        logger.warning(f"⚠️  [PERM_APPROVE] Неверный callback data от owner {owner_id}")
        await callback.answer("❌ Неверный запрос!", show_alert=True)
        return
    
    logger.info(f"📋 [PERM_APPROVE] Requester ID: {requester_id}, Owner ID: {owner_id}")
    
    # КРИТИЧНО: Проверяем, что это действительно запрос к кодам этого владельца
    # Проверяем, существует ли pending запрос от этого requester_id к owner_id
    try:
        logger.debug(f"🔍 [PERM_APPROVE] Проверка pending запроса в БД...")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT status FROM permissions
            WHERE owner_id = ? AND requester_id = ? AND status = 'pending'
        ''', (owner_id, requester_id))
        pending_request = cursor.fetchone()
        conn.close()
        
        if not pending_request:
            logger.warning(f"⚠️  [PERM_APPROVE] Запрос не найден или уже обработан. Owner: {owner_id}, Requester: {requester_id}")
            await callback.answer("❌ Запрос не найден или уже обработан!", show_alert=True)
            return
        
        logger.info(f"✅ [PERM_APPROVE] Pending запрос найден в БД")
    except Exception as e:
        logger.error(f"❌ [PERM_APPROVE] Ошибка проверки запроса в БД: {type(e).__name__}: {e}", exc_info=True)
        # Показываем безопасное, но информативное сообщение пользователю
        safe_error = sanitize_error_message(e)
        await callback.answer(
            f"❌ Ошибка обработки запроса.\n{safe_error}",
            show_alert=True
        )
        return

    # Обновляем статус в БД
    logger.info(f"💾 [PERM_APPROVE] Обновление статуса в БД на 'approved'...")
    db.update_permission(owner_id, requester_id, 'approved')
    logger.info(f"✅ [PERM_APPROVE] Статус обновлён в БД")

    # Получаем данные запрашивающего
    logger.debug(f"👤 [PERM_APPROVE] Получение данных requester (ID: {requester_id})...")
    requester = db.get_user_by_telegram_id(requester_id)
    requester_username = requester.get('username', 'unknown') if requester and isinstance(requester, dict) else 'unknown'
    logger.info(f"👤 [PERM_APPROVE] Requester username: @{requester_username}")

    # Обновляем сообщение
    logger.debug(f"✏️  [PERM_APPROVE] Обновление сообщения для owner...")
    await callback.message.edit_text(
        f"✅ <b>Доступ разрешён</b>\n\n"
        f"Пользователь @{requester_username} теперь может получать твои 2FA коды.\n\n"
        f"Отозвать доступ:\n"
        f"<code>/revoke @{requester_username}</code>"
    )

    # Уведомляем запрашивающего
    try:
        logger.debug(f"📤 [PERM_APPROVE] Отправка уведомления requester (ID: {requester_id})...")
        bot_instance = callback.bot

        owner = db.get_user_by_telegram_id(owner_id)
        if owner and isinstance(owner, dict):
            owner_username = owner.get('username', 'unknown')
            owner_email = owner.get('email', 'N/A')
            
            await bot_instance.send_message(
                chat_id=requester_id,
                text=(
                    f"✅ <b>Доступ получен!</b>\n\n"
                    f"@{owner_username} разрешил доступ к своим кодам.\n\n"
                    f"Получить код:\n"
                    f"<code>/get_code @{owner_username}</code>\n"
                    f"<code>/get_code {owner_email}</code>"
                )
            )
            logger.info(f"✅ [PERM_APPROVE] Уведомление отправлено requester @{requester_username}")
        else:
            logger.warning(f"⚠️  [PERM_APPROVE] Не удалось получить данные owner (ID: {owner_id})")
    except Exception as e:
        logger.error(f"❌ [PERM_APPROVE] Ошибка уведомления requester: {type(e).__name__}: {e}", exc_info=True)

    await callback.answer("✅ Доступ разрешён")
    logger.info(f"✅ [PERM_APPROVE] Успешно завершено. Owner: {owner_id} → Requester: {requester_id} (@{requester_username})")


@router.callback_query(F.data.startswith('perm_deny_'))
async def process_deny(callback: CallbackQuery):
    """
    Обработчик кнопки "Запретить".

    Args:
        callback: Callback от нажатия кнопки
    """
    owner_id = callback.from_user.id
    logger.info(f"🔔 [PERM_DENY] Начало обработки. Owner ID: {owner_id}, Callback data: {callback.data}")
    
    # Безопасно извлекаем ID запрашивающего
    requester_id = validate_callback_data(callback.data, "perm_deny_")
    if not requester_id:
        logger.warning(f"⚠️  [PERM_DENY] Неверный callback data от owner {owner_id}")
        await callback.answer("❌ Неверный запрос!", show_alert=True)
        return
    
    logger.info(f"📋 [PERM_DENY] Requester ID: {requester_id}, Owner ID: {owner_id}")
    
    # КРИТИЧНО: Проверяем, что это действительно запрос к кодам этого владельца
    try:
        logger.debug(f"🔍 [PERM_DENY] Проверка pending запроса в БД...")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT status FROM permissions
            WHERE owner_id = ? AND requester_id = ? AND status = 'pending'
        ''', (owner_id, requester_id))
        pending_request = cursor.fetchone()
        conn.close()
        
        if not pending_request:
            logger.warning(f"⚠️  [PERM_DENY] Запрос не найден или уже обработан. Owner: {owner_id}, Requester: {requester_id}")
            await callback.answer("❌ Запрос не найден или уже обработан!", show_alert=True)
            return
        
        logger.info(f"✅ [PERM_DENY] Pending запрос найден в БД")
    except Exception as e:
        logger.error(f"❌ [PERM_DENY] Ошибка проверки запроса в БД: {type(e).__name__}: {e}", exc_info=True)
        # Показываем безопасное, но информативное сообщение пользователю
        safe_error = sanitize_error_message(e)
        await callback.answer(
            f"❌ Ошибка обработки запроса.\n{safe_error}",
            show_alert=True
        )
        return

    # Обновляем статус в БД
    logger.info(f"💾 [PERM_DENY] Обновление статуса в БД на 'denied'...")
    db.update_permission(owner_id, requester_id, 'denied')
    logger.info(f"✅ [PERM_DENY] Статус обновлён в БД")

    # Получаем данные запрашивающего
    logger.debug(f"👤 [PERM_DENY] Получение данных requester (ID: {requester_id})...")
    requester = db.get_user_by_telegram_id(requester_id)
    requester_username = requester.get('username', 'unknown') if requester and isinstance(requester, dict) else 'unknown'
    logger.info(f"👤 [PERM_DENY] Requester username: @{requester_username}")

    # Обновляем сообщение
    logger.debug(f"✏️  [PERM_DENY] Обновление сообщения для owner...")
    await callback.message.edit_text(
        f"❌ <b>Доступ запрещён</b>\n\n"
        f"Ты отклонил запрос от @{requester_username}."
    )

    # Уведомляем запрашивающего
    try:
        logger.debug(f"📤 [PERM_DENY] Отправка уведомления requester (ID: {requester_id})...")
        bot_instance = callback.bot

        owner = db.get_user_by_telegram_id(owner_id)
        owner_username = owner.get('username', 'unknown') if owner and isinstance(owner, dict) else 'unknown'

        await bot_instance.send_message(
            chat_id=requester_id,
            text=(
                f"❌ <b>Доступ отклонён</b>\n\n"
                f"@{owner_username} отклонил твой запрос на доступ к кодам."
            )
        )
        logger.info(f"✅ [PERM_DENY] Уведомление отправлено requester @{requester_username}")
    except Exception as e:
        logger.error(f"❌ [PERM_DENY] Ошибка уведомления requester: {type(e).__name__}: {e}", exc_info=True)

    await callback.answer("❌ Доступ запрещён")
    logger.info(f"✅ [PERM_DENY] Успешно завершено. Owner: {owner_id} → Requester: {requester_id} (@{requester_username})")


@router.message(Command('my_permissions'))
async def cmd_my_permissions(message: Message):
    """
    Показать все разрешения пользователя с интерактивными кнопками.
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

    # Получаем разрешения
    permissions = db.get_my_permissions(user_id)

    given = permissions['given']
    received = permissions['received']

    # Формируем ответ
    text = "<b>🔐 Твои разрешения</b>\n\n"

    # Кому дал доступ
    if given:
        text += f"<b>✅ Кому ты дал доступ ({len(given)}):</b>\n"
        for perm in given[:5]:  # Показываем первых 5
            username = perm['requester_username']
            text += f"• @{username}\n"
        if len(given) > 5:
            text += f"... и ещё {len(given) - 5}\n"
        text += "\n"
    else:
        text += "📭 Ты никому не давал доступ к своим кодам\n\n"

    # От кого получил доступ
    if received:
        text += f"<b>📥 От кого получил доступ ({len(received)}):</b>\n"
        for perm in received[:5]:  # Показываем первых 5
            username = perm['owner_username']
            text += f"• @{username}\n"
        if len(received) > 5:
            text += f"... и ещё {len(received) - 5}\n"
        text += "\n"
    else:
        text += "📭 У тебя нет доступа к кодам коллег\n\n"

    text += "💡 Используй кнопки ниже для быстрых действий"

    # Создаём клавиатуру с кнопками
    keyboard = create_permissions_keyboard(
        permissions=permissions,
        show_get_code_buttons=True
    )

    await message.answer(
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


@router.message(Command('revoke'))
async def cmd_revoke(message: Message):
    """
    Отозвать доступ к своим кодам.
    Формат: /revoke @username
    """
    owner_id = message.from_user.id

    # Проверяем регистрацию
    owner = db.get_user_by_telegram_id(owner_id)
    if not owner:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    # Проверяем аргументы
    args = message.text.split()

    if len(args) < 2:
        await message.answer(
            "📝 Укажи username:\n\n"
            "Формат:\n"
            "<code>/revoke @username</code>\n\n"
            "Пример:\n"
            "<code>/revoke @ivan_petrov</code>"
        )
        return

    target_username = args[1].lstrip('@')

    # Ищем пользователя
    requester = db.get_user_by_username(target_username)

    if not requester or not isinstance(requester, dict):
        await message.answer(f"❌ Пользователь @{target_username} не найден!")
        return

    requester_id = requester.get('telegram_id')
    if not requester_id:
        await message.answer("❌ Ошибка: не удалось получить ID пользователя")
        return

    # Отзываем разрешение
    success = db.revoke_permission(owner_id, requester_id)

    if success:
        await message.answer(
            f"✅ Доступ отозван!\n\n"
            f"@{target_username} больше не может получать твои коды."
        )

        # Уведомляем пользователя
        try:
            bot_instance = message.bot
            owner_username = owner.get('username', 'unknown') if owner and isinstance(owner, dict) else 'unknown'

            await bot_instance.send_message(
                chat_id=requester_id,
                text=f"⚠️ @{owner_username} отозвал доступ к своим кодам."
            )
        except:
            pass

        logger.info(f"🔒 [REVOKE] Отозван доступ: Owner {owner_id} → Requester {requester_id}")
    else:
        await message.answer(f"⚠️ У @{target_username} не было доступа к твоим кодам.")


@router.message(Command('pending_requests'))
async def cmd_pending_requests(message: Message):
    """
    Показать ожидающие запросы на доступ к твоим кодам.
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

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Получаем pending запросы
        cursor.execute('''
            SELECT p.*, u.username as requester_username
            FROM permissions p
            JOIN users u ON p.requester_id = u.telegram_id
            WHERE p.owner_id = ? AND p.status = 'pending'
            ORDER BY p.requested_at DESC
        ''', (user_id,))

        pending = cursor.fetchall()
        conn.close()

        if not pending:
            await message.answer(
                "📭 Нет ожидающих запросов\n\n"
                "Когда кто-то запросит доступ к твоим кодам,\n"
                "ты получишь уведомление с кнопками."
            )
            return

        text = "<b>⏳ Ожидающие запросы:</b>\n\n"

        for req in pending:
            username = req['requester_username']
            req_time = req['requested_at'][:16]  # Обрезаем до минут

            text += f"• @{username}\n"
            text += f"  Запрошено: {req_time}\n\n"

        text += "Ответить можно в уведомлении с кнопками."

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ [PENDING_REQUESTS] Ошибка получения pending запросов: {type(e).__name__}: {e}", exc_info=True)
        safe_error = sanitize_error_message(e)
        await message.answer(
            "❌ Ошибка получения данных.\n\n"
            f"{safe_error}"
        )


@router.callback_query(F.data == "permissions_given_list")
async def callback_permissions_given_list(callback: CallbackQuery):
    """
    Показать список пользователей, которым дал доступ.
    """
    user_id = callback.from_user.id
    permissions = db.get_my_permissions(user_id)
    given = permissions.get('given', [])
    
    if not given:
        await callback.answer("Ты никому не давал доступ", show_alert=True)
        return
    
    text = "<b>✅ Кому ты дал доступ:</b>\n\n"
    for perm in given:
        username = perm['requester_username']
        text += f"• @{username}\n"
    
    text += "\n💡 Используй /revoke @username для отзыва доступа"
    
    keyboard = create_permissions_keyboard(permissions, show_get_code_buttons=False)
    
    await callback.message.edit_text(
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "permissions_received_list")
async def callback_permissions_received_list(callback: CallbackQuery):
    """
    Показать список пользователей, от которых получил доступ.
    """
    user_id = callback.from_user.id
    permissions = db.get_my_permissions(user_id)
    received = permissions.get('received', [])
    
    if not received:
        await callback.answer("У тебя нет доступа к кодам коллег", show_alert=True)
        return
    
    text = "<b>📥 От кого получил доступ:</b>\n\n"
    for perm in received:
        username = perm['owner_username']
        text += f"• @{username}\n"
    
    text += "\n💡 Используй /get_code @username для получения кода"
    
    keyboard = create_permissions_keyboard(permissions, show_get_code_buttons=True)
    
    await callback.message.edit_text(
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "permissions_all")
async def callback_permissions_all(callback: CallbackQuery):
    """
    Показать все разрешения.
    """
    user_id = callback.from_user.id
    user = db.get_user_by_telegram_id(user_id)
    
    if not user:
        await callback.answer("Сначала зарегистрируйся!", show_alert=True)
        return
    
    permissions = db.get_my_permissions(user_id)
    given = permissions['given']
    received = permissions['received']
    
    text = "<b>🔐 Твои разрешения</b>\n\n"
    
    if given:
        text += f"<b>✅ Кому дал доступ ({len(given)}):</b>\n"
        for perm in given[:5]:
            text += f"• @{perm['requester_username']}\n"
        if len(given) > 5:
            text += f"... и ещё {len(given) - 5}\n"
        text += "\n"
    else:
        text += "📭 Ты никому не давал доступ\n\n"
    
    if received:
        text += f"<b>📥 От кого получил доступ ({len(received)}):</b>\n"
        for perm in received[:5]:
            text += f"• @{perm['owner_username']}\n"
        if len(received) > 5:
            text += f"... и ещё {len(received) - 5}\n"
        text += "\n"
    else:
        text += "📭 У тебя нет доступа к кодам коллег\n\n"
    
    text += "💡 Используй кнопки ниже для быстрых действий"
    
    keyboard = create_permissions_keyboard(permissions, show_get_code_buttons=True)
    
    await callback.message.edit_text(
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "permissions_refresh")
async def callback_permissions_refresh(callback: CallbackQuery):
    """
    Обновить список разрешений.
    """
    user_id = callback.from_user.id
    permissions = db.get_my_permissions(user_id)
    
    given = permissions['given']
    received = permissions['received']
    
    text = "<b>🔐 Твои разрешения</b>\n\n"
    
    if given:
        text += f"<b>✅ Кому дал доступ ({len(given)}):</b>\n"
        for perm in given[:5]:
            text += f"• @{perm['requester_username']}\n"
        if len(given) > 5:
            text += f"... и ещё {len(given) - 5}\n"
        text += "\n"
    else:
        text += "📭 Ты никому не давал доступ\n\n"
    
    if received:
        text += f"<b>📥 От кого получил доступ ({len(received)}):</b>\n"
        for perm in received[:5]:
            text += f"• @{perm['owner_username']}\n"
        if len(received) > 5:
            text += f"... и ещё {len(received) - 5}\n"
        text += "\n"
    else:
        text += "📭 У тебя нет доступа к кодам коллег\n\n"
    
    text += "✅ Обновлено!"
    
    keyboard = create_permissions_keyboard(permissions, show_get_code_buttons=True)
    
    await callback.message.edit_text(
        text=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer("✅ Обновлено")