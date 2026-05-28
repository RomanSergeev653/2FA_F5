"""
Утилиты для создания улучшенных сообщений бота.
Содержит шаблоны и функции для форматирования сообщений.
"""

from typing import Optional, Dict, List
from datetime import datetime


def format_user_status(user: Optional[Dict]) -> str:
    """
    Форматировать статус пользователя.
    
    Args:
        user: Данные пользователя или None
        
    Returns:
        str: Отформатированный статус
    """
    if not user:
        return "❌ Не зарегистрирован"
    
    return (
        f"✅ Зарегистрирован\n"
        f"📧 Email: <code>{user.get('email', 'N/A')}</code>\n"
        f"🏢 Провайдер: {user.get('email_provider', 'N/A')}"
    )


def format_permissions_count(permissions: Dict[str, List[Dict]]) -> str:
    """
    Форматировать количество разрешений.
    
    Args:
        permissions: Словарь с ключами 'given' и 'received'
        
    Returns:
        str: Отформатированная информация о разрешениях
    """
    given_count = len(permissions.get('given', []))
    received_count = len(permissions.get('received', []))
    
    return (
        f"📊 <b>Статистика разрешений:</b>\n"
        f"✅ Дал доступ: {given_count} чел.\n"
        f"📥 Получил доступ: {received_count} чел."
    )


def format_code_result(
    code: str,
    owner_username: str,
    owner_email: str,
    search_time: Optional[float] = None
) -> str:
    """
    Форматировать результат получения кода.
    
    Args:
        code: Найденный код
        owner_username: Username владельца
        owner_email: Email владельца
        search_time: Время поиска в секундах (опционально)
        
    Returns:
        str: Отформатированное сообщение
    """
    message = (
        f"✅ <b>Код найден!</b>\n\n"
        f"🔐 Код: <code>{code}</code>\n\n"
        f"👤 От: @{owner_username}\n"
        f"📧 Почта: {owner_email}\n\n"
        f"💡 Нажми на код чтобы скопировать"
    )
    
    if search_time:
        message += f"\n\n⏱ Время поиска: {search_time:.1f} сек."
    
    return message


def format_code_not_found(
    owner_username: str,
    suggestions: Optional[List[str]] = None
) -> str:
    """
    Форматировать сообщение о том, что код не найден.
    
    Args:
        owner_username: Username владельца
        suggestions: Список предложений (опционально)
        
    Returns:
        str: Отформатированное сообщение
    """
    message = (
        f"😞 <b>Код не найден</b>\n\n"
        f"Возможные причины:\n"
        f"• В последних письмах нет 2FA кодов\n"
        f"• Коды старше 10 минут (устарели)\n"
        f"• Письма с кодом ещё не пришли\n\n"
        f"💡 Попробуй:\n"
        f"• Подождать несколько секунд\n"
        f"• Попросить коллегу запросить новый код\n"
        f"• Повторить команду: <code>/get_code @{owner_username}</code>"
    )
    
    if suggestions:
        message += "\n\n💡 Дополнительные советы:\n"
        for suggestion in suggestions:
            message += f"• {suggestion}\n"
    
    return message


def format_error_message(
    error_type: str,
    details: Optional[str] = None,
    suggestions: Optional[List[str]] = None
) -> str:
    """
    Форматировать сообщение об ошибке с подсказками.
    
    Args:
        error_type: Тип ошибки ('connection', 'permission', 'not_found', 'validation')
        details: Дополнительные детали
        suggestions: Список предложений по исправлению
        
    Returns:
        str: Отформатированное сообщение об ошибке
    """
    error_messages = {
        'connection': (
            "❌ <b>Ошибка подключения к почте!</b>\n\n"
            "Возможные причины:\n"
            "• Проблемы с подключением к серверу\n"
            "• Изменился пароль приложения\n"
            "• Временные проблемы у почтового провайдера\n"
        ),
        'permission': (
            "🔒 <b>Доступ запрещён!</b>\n\n"
            "У тебя нет разрешения на это действие.\n"
        ),
        'not_found': (
            "❌ <b>Не найдено!</b>\n\n"
            "Запрашиваемый элемент не найден.\n"
        ),
        'validation': (
            "❌ <b>Ошибка валидации!</b>\n\n"
            "Проверь правильность введённых данных.\n"
        ),
        'generic': (
            "❌ <b>Произошла ошибка</b>\n\n"
            "Попробуй позже или обратись к администратору.\n"
        )
    }
    
    message = error_messages.get(error_type, error_messages['generic'])
    
    if details:
        message += f"\n📝 Детали: {details}\n"
    
    if suggestions:
        message += "\n💡 Что можно сделать:\n"
        for suggestion in suggestions:
            message += f"• {suggestion}\n"
    
    return message


def format_registration_success(
    email: str,
    provider: str,
    username: str
) -> str:
    """
    Форматировать сообщение об успешной регистрации.
    
    Args:
        email: Email адрес
        provider: Провайдер почты
        username: Username пользователя
        
    Returns:
        str: Отформатированное сообщение
    """
    return (
        f"✅ <b>Регистрация успешна!</b>\n\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🏢 Провайдер: {provider}\n\n"
        f"Теперь коллеги могут запросить доступ к твоим кодам через:\n"
        f"<code>/request_access @{username}</code>\n\n"
        f"А ты можешь получать коды коллег (с их разрешения):\n"
        f"<code>/get_code @username</code>"
    )


def format_permission_request(
    requester_username: str,
    requester_name: str,
    requester_email: str
) -> str:
    """
    Форматировать запрос на доступ.
    
    Args:
        requester_username: Username запрашивающего
        requester_name: Имя запрашивающего
        requester_email: Email запрашивающего
        
    Returns:
        str: Отформатированное сообщение
    """
    return (
        f"🔔 <b>Запрос доступа к твоим 2FA кодам</b>\n\n"
        f"👤 От: @{requester_username} ({requester_name})\n"
        f"📧 Email: {requester_email}\n\n"
        f"Разрешить доступ?"
    )


def format_permission_granted(
    requester_username: str,
    owner_username: str,
    owner_email: str
) -> str:
    """
    Форматировать сообщение о предоставленном доступе.
    
    Args:
        requester_username: Username запрашивающего
        owner_username: Username владельца
        owner_email: Email владельца
        
    Returns:
        str: Отформатированное сообщение
    """
    return (
        f"✅ <b>Доступ получен!</b>\n\n"
        f"@{owner_username} разрешил доступ к своим кодам.\n\n"
        f"Получить код:\n"
        f"<code>/get_code @{owner_username}</code>\n"
        f"<code>/get_code {owner_email}</code>"
    )


def format_progress_message(stage: str, details: Optional[str] = None) -> str:
    """
    Форматировать сообщение о прогрессе выполнения.
    
    Args:
        stage: Этап выполнения ('searching', 'connecting', 'fetching', 'parsing')
        details: Дополнительные детали
        
    Returns:
        str: Отформатированное сообщение
    """
    stage_messages = {
        'searching': "🔍 Ищу код в почте...",
        'connecting': "🔌 Подключаюсь к почте...",
        'fetching': "📥 Получаю письма...",
        'parsing': "🔎 Анализирую письма...",
        'found': "✅ Код найден!"
    }
    
    message = stage_messages.get(stage, "⏳ Обработка...")
    
    if details:
        message += f"\n{details}"
    
    return message


def format_tips_message() -> str:
    """
    Форматировать сообщение с полезными советами.
    
    Returns:
        str: Отформатированное сообщение с советами
    """
    return (
        "💡 <b>Полезные советы</b>\n\n"
        "🔐 <b>Безопасность:</b>\n"
        "• Используй пароль приложения, а не основной пароль\n"
        "• Регулярно проверяй, кому ты дал доступ\n"
        "• Отзывай доступ у бывших коллег\n\n"
        "⚡ <b>Скорость:</b>\n"
        "• Используй inline кнопки для быстрого доступа\n"
        "• Сохраняй часто используемых коллег в избранное\n"
        "• Используй /menu для быстрой навигации\n\n"
        "❓ <b>Проблемы:</b>\n"
        "• Если код не находится, попроси коллегу запросить новый\n"
        "• Проверь подключение к почте командой /check_email\n"
        "• Используй /help для подробной справки"
    )


def format_help_section(section: str) -> str:
    """
    Форматировать раздел справки.
    
    Args:
        section: Название раздела ('register', 'get_code', 'permissions', 'faq', 'tips')
        
    Returns:
        str: Отформатированный текст раздела
    """
    sections = {
        'register': (
            "📧 <b>Регистрация</b>\n\n"
            "Используй /register чтобы добавить свою почту.\n\n"
            "<b>Что нужно:</b>\n"
            "• Email адрес\n"
            "• Пароль приложения (НЕ основной пароль!)\n\n"
            "<b>Как получить пароль приложения:</b>\n"
            "📧 Gmail: https://myaccount.google.com/apppasswords\n"
            "📧 Yandex: https://id.yandex.ru/security/app-passwords\n"
            "📧 Mail.ru: Настройки → Пароль и безопасность\n\n"
            "<b>Формат:</b>\n"
            "<code>email@example.com пароль_приложения</code>"
        ),
        'get_code': (
            "🔐 <b>Получение кодов</b>\n\n"
            "Есть несколько способов получить 2FA код:\n\n"
            "<b>1. Через команду:</b>\n"
            "<code>/get_code @username</code>\n"
            "<code>/get_code email@example.com</code>\n\n"
            "<b>2. Интерактивный режим:</b>\n"
            "<code>/get_code</code> - затем выбери из списка\n\n"
            "<b>3. Быстрый способ:</b>\n"
            "Просто напиши: <code>@username</code>\n\n"
            "<b>Важно:</b>\n"
            "• Сначала нужно получить разрешение через /request_access\n"
            "• Коды действительны только 10 минут"
        ),
        'permissions': (
            "👥 <b>Разрешения</b>\n\n"
            "<b>Запросить доступ:</b>\n"
            "<code>/request_access @username</code>\n"
            "<code>/request_access email@example.com</code>\n\n"
            "<b>Посмотреть свои разрешения:</b>\n"
            "<code>/my_permissions</code>\n\n"
            "<b>Отозвать доступ:</b>\n"
            "<code>/revoke @username</code>\n\n"
            "<b>Ожидающие запросы:</b>\n"
            "<code>/pending_requests</code>"
        ),
        'faq': (
            "❓ <b>Часто задаваемые вопросы</b>\n\n"
            "<b>Q: Безопасно ли это?</b>\n"
            "A: Да, пароли хранятся в зашифрованном виде. Только ты контролируешь доступ.\n\n"
            "<b>Q: Что если я забыл пароль приложения?</b>\n"
            "A: Создай новый пароль приложения и перерегистрируйся через /register\n\n"
            "<b>Q: Можно ли использовать основной пароль?</b>\n"
            "A: Нет! Используй только пароль приложения для безопасности.\n\n"
            "<b>Q: Код не находится, что делать?</b>\n"
            "A: Попроси коллегу запросить новый код, подожди несколько секунд и попробуй снова."
        ),
        'tips': format_tips_message()
    }
    
    return sections.get(section, "Раздел не найден")


def _plural_people(n: int) -> str:
    """Склонение «человек» для русского языка."""
    if n % 10 == 1 and n % 100 != 11:
        return "человек"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "человека"
    return "человек"


def format_request_access_hint(registered_count: int) -> str:
    """
    Подсказка для /request_access без аргументов (без раскрытия списка пользователей).
    """
    word = _plural_people(registered_count)
    return (
        f"➕ <b>Запросить доступ</b>\n\n"
        f"Нас уже {registered_count} {word}!\n\n"
        f"Запроси доступ у своего коллеги командой:\n"
        f"<code>/request_access @username</code>\n"
        f"или\n"
        f"<code>/request_access email@example.com</code>"
    )


REQUEST_ACCESS_SOLO_MESSAGE = (
    "📭 <b>Пока только ты</b>\n\n"
    "В боте зарегистрирован только ты.\n"
    "Попроси коллег зарегистрироваться через /register"
)


def format_user_list_message(
    users: List[Dict],
    action: str = "get_code",
    page: int = 0,
    total_pages: int = 1
) -> str:
    """
    Форматировать сообщение со списком пользователей.
    
    Args:
        users: Список пользователей
        action: Действие ('get_code', 'request_access')
        page: Номер страницы
        total_pages: Всего страниц
        
    Returns:
        str: Отформатированное сообщение
    """
    if action == "get_code":
        title = "🔐 <b>Выбери пользователя для получения кода:</b>"
    elif action == "request_access":
        title = "➕ <b>Выбери пользователя для запроса доступа:</b>"
    else:
        title = "👥 <b>Список пользователей:</b>"
    
    message = f"{title}\n\n"
    
    if not users:
        message += "📭 Пользователи не найдены"
        return message
    
    for i, user in enumerate(users, start=1):
        username = user.get('username', 'unknown')
        email = user.get('email', 'N/A')
        message += f"{i}. @{username} ({email})\n"
    
    if total_pages > 1:
        message += f"\n📄 Страница {page + 1} из {total_pages}"
    
    return message
