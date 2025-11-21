from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db_manager import db


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

    # Проверяем, зарегистрирован ли запрашивающий
    requester = db.get_user_by_telegram_id(requester_id)
    if not requester:
        await message.answer(
            "❌ Сначала зарегистрируйся!\n"
            "Используй /register"
        )
        return

    # Проверяем, указан ли username в команде
    args = message.text.split()

    if len(args) < 2:
        await message.answer(
            "📝 Укажи username коллеги:\n\n"
            "Формат: <code>/request_access @username</code>\n\n"
            "Пример:\n"
            "<code>/request_access @ivan_petrov</code>"
        )
        return

    target_username = args[1].lstrip('@')

    # Проверяем, не себя ли запрашивает
    if target_username == requester['username']:
        await message.answer("😅 Нельзя запросить доступ к своим кодам!")
        return

    # Ищем пользователя в БД
    owner = db.get_user_by_username(target_username)

    if not owner:
        await message.answer(
            f"❌ Пользователь @{target_username} не найден!\n\n"
            "Возможные причины:\n"
            "• Пользователь ещё не зарегистрирован в боте\n"
            "• Неправильно указан username\n\n"
            "Попроси коллегу использовать /register"
        )
        return

    owner_id = owner['telegram_id']

    # Проверяем, нет ли уже разрешения
    if db.check_permission(owner_id, requester_id):
        await message.answer(
            f"✅ У тебя уже есть доступ к кодам @{target_username}!\n\n"
            f"Получить код: /get_code @{target_username}"
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
    requester_username = requester['username']
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
            f"📧 Email: {requester['email']}\n\n"
            f"Разрешить доступ?"
        )

        await bot_instance.send_message(
            chat_id=owner_id,
            text=notification_text,
            reply_markup=keyboard
        )

        await message.answer(
            f"✅ Запрос отправлен @{target_username}!\n"
            f"Ожидай ответа."
        )

        print(f"📤 Запрос доступа: {requester_username} → @{target_username}")

    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")
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
    requester_id = int(callback.data.split('_')[2])

    # Обновляем статус в БД
    db.update_permission(owner_id, requester_id, 'approved')

    # Получаем данные запрашивающего
    requester = db.get_user_by_telegram_id(requester_id)
    requester_username = requester['username'] if requester else 'unknown'

    # Обновляем сообщение
    await callback.message.edit_text(
        f"✅ <b>Доступ разрешён</b>\n\n"
        f"Пользователь @{requester_username} теперь может получать твои 2FA коды.\n\n"
        f"Отозвать доступ: /revoke @{requester_username}"
    )

    # Уведомляем запрашивающего
    try:
        bot_instance = callback.bot

        owner = db.get_user_by_telegram_id(owner_id)
        owner_username = owner['username'] if owner else 'unknown'

        await bot_instance.send_message(
            chat_id=requester_id,
            text=(
                f"✅ <b>Доступ получен!</b>\n\n"
                f"@{owner_username} разрешил доступ к своим кодам.\n\n"
                f"Получить код: /get_code @{owner_username}"
            )
        )
    except Exception as e:
        print(f"❌ Ошибка уведомления запрашивающего: {e}")

    await callback.answer("✅ Доступ разрешён")

    print(f"✅ Разрешение: {owner_id} → {requester_id}")


@router.callback_query(F.data.startswith('perm_deny_'))
async def process_deny(callback: CallbackQuery):
    """
    Обработчик кнопки "Запретить".

    Args:
        callback: Callback от нажатия кнопки
    """
    owner_id = callback.from_user.id
    requester_id = int(callback.data.split('_')[2])

    # Обновляем статус в БД
    db.update_permission(owner_id, requester_id, 'denied')

    # Получаем данные запрашивающего
    requester = db.get_user_by_telegram_id(requester_id)
    requester_username = requester['username'] if requester else 'unknown'

    # Обновляем сообщение
    await callback.message.edit_text(
        f"❌ <b>Доступ запрещён</b>\n\n"
        f"Ты отклонил запрос от @{requester_username}."
    )

    # Уведомляем запрашивающего
    try:
        bot_instance = callback.bot

        owner = db.get_user_by_telegram_id(owner_id)
        owner_username = owner['username'] if owner else 'unknown'

        await bot_instance.send_message(
            chat_id=requester_id,
            text=(
                f"❌ <b>Доступ отклонён</b>\n\n"
                f"@{owner_username} отклонил твой запрос на доступ к кодам."
            )
        )
    except Exception as e:
        print(f"❌ Ошибка уведомления запрашивающего: {e}")

    await callback.answer("❌ Доступ запрещён")

    print(f"❌ Отказано: {owner_id} → {requester_id}")


@router.message(Command('my_permissions'))
async def cmd_my_permissions(message: Message):
    """
    Показать все разрешения пользователя.
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
        text += "<b>✅ Кому ты дал доступ к своим кодам:</b>\n"
        for perm in given:
            username = perm['requester_username']
            text += f"• @{username}\n"
        text += f"\nОтозвать: /revoke @username\n\n"
    else:
        text += "📭 Ты никому не давал доступ к своим кодам\n\n"

    # От кого получил доступ
    if received:
        text += "<b>✅ От кого ты получил доступ к кодам:</b>\n"
        for perm in received:
            username = perm['owner_username']
            text += f"• @{username}\n"
        text += f"\nПолучить код: /get_code @username\n"
        text += f"\nNew!!! Используй только: @username\n"
    else:
        text += "📭 У тебя нет доступа к кодам коллег\n"
        text += "Запросить: /request_access @username"

    await message.answer(text)


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
            "Формат: <code>/revoke @username</code>\n\n"
            "Пример:\n"
            "<code>/revoke @ivan_petrov</code>"
        )
        return

    target_username = args[1].lstrip('@')

    # Ищем пользователя
    requester = db.get_user_by_username(target_username)

    if not requester:
        await message.answer(f"❌ Пользователь @{target_username} не найден!")
        return

    requester_id = requester['telegram_id']

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

            await bot_instance.send_message(
                chat_id=requester_id,
                text=f"⚠️ @{owner['username']} отозвал доступ к своим кодам."
            )
        except:
            pass

        print(f"🔒 Отозван доступ: {owner_id} ⇢ {requester_id}")
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
        conn = db.get_connection()
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
        print(f"❌ Ошибка получения pending запросов: {e}")
        await message.answer("❌ Ошибка получения данных")