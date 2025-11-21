from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from database.db_manager import db
from utils.encryption import decrypt_password
from utils.email_parser import EmailParser

# Создаём роутер
router = Router()


@router.message(Command('get_code'))
async def cmd_get_code(message: Message):
    """
    Получить последний 2FA код от коллеги.
    Формат: /get_code @username

    Args:
        message: Сообщение от пользователя
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
        await message.answer(
            "📝 Укажи username коллеги:\n\n"
            "Формат: <code>/get_code @username</code>\n\n"
            "Пример:\n"
            "<code>/get_code @ivan_petrov</code>\n\n"
            "💡 Сначала нужно получить разрешение:\n"
            "/request_access @username"
        )
        return

    target_username = args[1].lstrip('@')

    # Проверяем, не пытается ли получить свой код (бессмысленно)
    if target_username == requester['username']:
        await message.answer(
            "😅 Зачем получать свой код через бота?\n"
            "Он приходит тебе на почту напрямую!\n"
            "Попробуй /test_code"
        )
        return

    # Ищем владельца кодов в БД
    owner = db.get_user_by_username(target_username)

    if not owner:
        await message.answer(
            f"❌ Пользователь @{target_username} не найден!\n\n"
            "Возможные причины:\n"
            "• Пользователь не зарегистрирован в боте\n"
            "• Неправильно указан username\n\n"
            "Попроси коллегу использовать /register"
        )
        return

    owner_id = owner['telegram_id']

    # Проверяем разрешение
    has_permission = db.check_permission(owner_id, requester_id)

    if not has_permission:
        await message.answer(
            f"🔒 <b>Доступ запрещён!</b>\n\n"
            f"У тебя нет разрешения на получение кодов от @{target_username}\n\n"
            f"Запросить доступ:\n"
            f"/request_access @{target_username}"
        )
        return

    # Отправляем сообщение о поиске
    searching_msg = await message.answer(
        f"🔍 Ищу код в почте @{target_username}...\n"
        f"⏳ Это может занять несколько секунд"
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
            await searching_msg.edit_text(
                f"✅ <b>Код найден!</b>\n\n"
                f"🔐 Код: <code>{code}</code>\n\n"
                f"👤 От: @{target_username}\n"
                f"📧 Почта: {email}\n\n"
                f"💡 Нажми на код чтобы скопировать"
            )

            # Обновляем время последнего запроса
            db.update_last_code_request(owner_id)

            # Логируем
            db.log_action(
                user_id=requester_id,
                action_type='code_retrieved',
                details=f'Got code from {target_username}'
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
            await searching_msg.edit_text(
                f"😞 <b>Код не найден</b>\n\n"
                f"Возможные причины:\n"
                f"• В последних письмах нет 2FA кодов\n"
                f"• Коды старше 10 минут (устарели)\n"
                f"• Письма с кодом ещё не пришли\n\n"
                f"💡 Попробуй:\n"
                f"• Подождать несколько секунд\n"
                f"• Попросить коллегу запросить новый код\n"
                f"• Повторить команду: /get_code @{target_username}"
            )

            print(f"⚠️ Код не найден для {owner['username']}")

    except Exception as e:
        print(f"❌ Ошибка получения кода: {e}")
        await searching_msg.edit_text(
            f"❌ <b>Ошибка подключения к почте!</b>\n\n"
            f"Возможные причины:\n"
            f"• Проблемы с подключением к серверу\n"
            f"• Изменился пароль приложения у @{target_username}\n"
            f"• Временные проблемы у почтового провайдера\n\n"
            f"Попробуй позже или свяжись с @{target_username}"
        )


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


@router.message(Command('test_code'))
async def cmd_test_code(message: Message):
    """
    Протестировать получение своего кода (для отладки).
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
    username_mention = message.text.strip()

    # Создаём копию message с изменённым текстом
    modified_message = message.model_copy(update={"text": f"/get_code {username_mention}"})

    await cmd_get_code(modified_message)