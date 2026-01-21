"""
Утилиты для создания inline клавиатур Telegram бота.
Содержит функции для генерации различных типов клавиатур.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Optional


def create_main_menu_keyboard(is_registered: bool = False) -> InlineKeyboardMarkup:
    """
    Создать главное меню с основными командами.
    
    Args:
        is_registered: Зарегистрирован ли пользователь
        
    Returns:
        InlineKeyboardMarkup: Клавиатура главного меню
    """
    buttons = []
    
    if not is_registered:
        buttons.append([
            InlineKeyboardButton(text="📧 Зарегистрироваться", callback_data="menu_register")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🔐 Получить код", callback_data="menu_get_code"),
            InlineKeyboardButton(text="👥 Мои разрешения", callback_data="menu_permissions")
        ])
        buttons.append([
            InlineKeyboardButton(text="➕ Запросить доступ", callback_data="menu_request_access"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help"),
        InlineKeyboardButton(text="🔄 Обновить меню", callback_data="menu_refresh")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_user_list_keyboard(
    users: List[Dict],
    action: str = "get_code",
    page: int = 0,
    per_page: int = 5
) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру со списком пользователей.
    
    Args:
        users: Список пользователей (словари с ключами 'username', 'telegram_id', 'email')
        action: Действие при нажатии ('get_code', 'request_access', 'revoke')
        page: Номер страницы (для пагинации)
        per_page: Количество пользователей на странице
        
    Returns:
        InlineKeyboardMarkup: Клавиатура со списком пользователей
    """
    buttons = []
    
    # Вычисляем индексы для текущей страницы
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_users = users[start_idx:end_idx]
    
    # Создаём кнопки для каждого пользователя
    for user in page_users:
        username = user.get('username', 'unknown')
        user_id = user.get('telegram_id', 0)
        
        # Определяем текст кнопки в зависимости от действия
        if action == "get_code":
            button_text = f"🔐 @{username}"
            callback_data = f"get_code_{user_id}"
        elif action == "request_access":
            button_text = f"➕ @{username}"
            callback_data = f"request_access_{user_id}"
        elif action == "revoke":
            button_text = f"❌ @{username}"
            callback_data = f"revoke_{user_id}"
        else:
            button_text = f"👤 @{username}"
            callback_data = f"user_{user_id}"
        
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    # Кнопки навигации (если есть несколько страниц)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"{action}_page_{page-1}")
        )
    
    if end_idx < len(users):
        nav_buttons.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{action}_page_{page+1}")
        )
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Кнопка отмены
    buttons.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_permissions_keyboard(
    permissions: Dict[str, List[Dict]],
    show_get_code_buttons: bool = True
) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру для управления разрешениями.
    
    Args:
        permissions: Словарь с ключами 'given' и 'received' (списки разрешений)
        show_get_code_buttons: Показывать ли кнопки "Получить код"
        
    Returns:
        InlineKeyboardMarkup: Клавиатура разрешений
    """
    buttons = []
    
    # Разрешения, которые дал пользователь
    given = permissions.get('given', [])
    if given:
        buttons.append([InlineKeyboardButton(
            text=f"✅ Кому дал доступ ({len(given)})",
            callback_data="permissions_given_list"
        )])
        
        if show_get_code_buttons:
            # Кнопки для быстрого получения кодов (первые 3)
            for perm in given[:3]:
                username = perm.get('requester_username', 'unknown')
                user_id = perm.get('requester_id', 0)
                buttons.append([InlineKeyboardButton(
                    text=f"🔐 Получить код от @{username}",
                    callback_data=f"get_code_{user_id}"
                )])
    
    # Разрешения, которые получил пользователь
    received = permissions.get('received', [])
    if received:
        buttons.append([InlineKeyboardButton(
            text=f"📥 От кого получил доступ ({len(received)})",
            callback_data="permissions_received_list"
        )])
    
    # Общие действия
    buttons.append([
        InlineKeyboardButton(text="➕ Запросить доступ", callback_data="menu_request_access"),
        InlineKeyboardButton(text="📋 Все разрешения", callback_data="permissions_all")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="permissions_refresh")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_code_result_keyboard(
    owner_username: str,
    owner_id: int,
    can_retry: bool = True
) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру после получения кода.
    
    Args:
        owner_username: Username владельца кода
        owner_id: ID владельца кода
        can_retry: Можно ли повторить запрос
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями
    """
    buttons = []
    
    if can_retry:
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Получить ещё раз",
                callback_data=f"get_code_{owner_id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="📋 Мои разрешения", callback_data="menu_permissions"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_help_keyboard() -> InlineKeyboardMarkup:
    """
    Создать клавиатуру для навигации по справке.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура справки
    """
    buttons = [
        [
            InlineKeyboardButton(text="📧 Регистрация", callback_data="help_register"),
            InlineKeyboardButton(text="🔐 Получение кодов", callback_data="help_get_code")
        ],
        [
            InlineKeyboardButton(text="👥 Разрешения", callback_data="help_permissions"),
            InlineKeyboardButton(text="❓ FAQ", callback_data="help_faq")
        ],
        [
            InlineKeyboardButton(text="💡 Советы", callback_data="help_tips"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_confirm_keyboard(
    action: str,
    item_id: Optional[int] = None,
    confirm_text: str = "✅ Да",
    cancel_text: str = "❌ Нет"
) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру подтверждения действия.
    
    Args:
        action: Название действия (например, 'unregister', 'revoke')
        item_id: ID элемента (опционально)
        confirm_text: Текст кнопки подтверждения
        cancel_text: Текст кнопки отмены
        
    Returns:
        InlineKeyboardMarkup: Клавиатура подтверждения
    """
    callback_data = f"{action}_confirm"
    if item_id is not None:
        callback_data = f"{action}_confirm_{item_id}"
    
    buttons = [
        [
            InlineKeyboardButton(text=confirm_text, callback_data=callback_data),
            InlineKeyboardButton(text=cancel_text, callback_data="cancel")
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_error_keyboard(
    action: str = "retry",
    show_help: bool = True
) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру при ошибке.
    
    Args:
        action: Действие для повтора (например, 'get_code', 'register')
        show_help: Показывать ли кнопку помощи
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями при ошибке
    """
    buttons = []
    
    if action:
        buttons.append([
            InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"retry_{action}")
        ])
    
    if show_help:
        buttons.append([
            InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_main")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
