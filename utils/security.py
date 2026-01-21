"""
Утилиты для безопасности: валидация, rate limiting, проверка прав доступа.
"""

import re
import time
from typing import Optional, Dict, Tuple
from collections import defaultdict
from datetime import datetime, timedelta


# Rate limiting: храним время последних запросов по пользователям
_rate_limit_storage: Dict[int, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
_rate_limit_cleanup_interval = 3600  # Очистка раз в час
_last_cleanup = time.time()


def validate_callback_data(callback_data: str, expected_prefix: str) -> Optional[int]:
    """
    Безопасно извлечь ID из callback_data.
    
    Args:
        callback_data: Данные callback
        expected_prefix: Ожидаемый префикс (например, "get_code_")
        
    Returns:
        int: Извлечённый ID или None если невалидно
    """
    if not callback_data.startswith(expected_prefix):
        return None
    
    try:
        # Извлекаем ID (последняя часть после последнего _)
        parts = callback_data.split('_')
        if len(parts) < 3:  # Минимум: prefix + число
            return None
        
        # ID должен быть последним элементом
        id_str = parts[-1]
        
        # Проверяем, что это только цифры
        if not id_str.isdigit():
            return None
        
        user_id = int(id_str)
        
        # Проверяем разумные границы (Telegram ID обычно положительные числа)
        if user_id <= 0 or user_id > 2**63:  # Максимальный разумный ID
            return None
        
        return user_id
        
    except (ValueError, IndexError):
        return None


def validate_email(email: str) -> bool:
    """
    Валидация email адреса с использованием регулярного выражения.
    
    Args:
        email: Email адрес для проверки
        
    Returns:
        bool: True если email валиден
    """
    if not email or len(email) > 254:  # RFC 5321 ограничение
        return False
    
    # Более строгая валидация email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email):
        return False
    
    # Дополнительные проверки
    parts = email.split('@')
    if len(parts) != 2:
        return False
    
    local_part, domain = parts
    
    # Локальная часть не должна быть пустой и не должна быть слишком длинной
    if not local_part or len(local_part) > 64:
        return False
    
    # Домен не должен быть пустым
    if not domain or len(domain) > 253:
        return False
    
    # Домен должен содержать хотя бы одну точку
    if '.' not in domain:
        return False
    
    # Проверяем, что домен не начинается/заканчивается точкой или дефисом
    if domain.startswith('.') or domain.endswith('.') or domain.startswith('-') or domain.endswith('-'):
        return False
    
    return True


def validate_username(username: str) -> bool:
    """
    Валидация username.
    
    Args:
        username: Username для проверки
        
    Returns:
        bool: True если username валиден
    """
    if not username:
        return False
    
    # Telegram username ограничения
    if len(username) < 5 or len(username) > 32:
        return False
    
    # Только буквы, цифры и подчёркивания
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False
    
    # Не должен начинаться с цифры
    if username[0].isdigit():
        return False
    
    return True


def check_rate_limit(
    user_id: int,
    action: str,
    max_requests: int = 10,
    time_window: int = 60
) -> Tuple[bool, Optional[int]]:
    """
    Проверить rate limit для действия пользователя.
    
    Args:
        user_id: ID пользователя
        action: Тип действия (например, 'get_code', 'register')
        max_requests: Максимальное количество запросов
        time_window: Временное окно в секундах
        
    Returns:
        Tuple[bool, Optional[int]]: (разрешено, оставшееся время до разблокировки)
    """
    global _last_cleanup
    
    current_time = time.time()
    
    # Периодическая очистка старых записей
    if current_time - _last_cleanup > _rate_limit_cleanup_interval:
        _cleanup_rate_limit_storage()
        _last_cleanup = current_time
    
    # Получаем список запросов для этого пользователя и действия
    requests = _rate_limit_storage[user_id][action]
    
    # Удаляем старые запросы (старше time_window)
    cutoff_time = current_time - time_window
    requests[:] = [req_time for req_time in requests if req_time > cutoff_time]
    
    # Проверяем лимит
    if len(requests) >= max_requests:
        # Вычисляем время до разблокировки
        oldest_request = min(requests)
        unlock_time = oldest_request + time_window
        remaining = int(unlock_time - current_time)
        return False, max(0, remaining)
    
    # Добавляем текущий запрос
    requests.append(current_time)
    
    return True, None


def _cleanup_rate_limit_storage():
    """Очистить старые записи из rate limit storage."""
    global _rate_limit_storage
    
    current_time = time.time()
    cutoff_time = current_time - 3600  # Удаляем записи старше часа
    
    # Удаляем пустые записи и старые данные
    users_to_remove = []
    for user_id, actions in _rate_limit_storage.items():
        actions_to_remove = []
        for action, requests in actions.items():
            requests[:] = [req_time for req_time in requests if req_time > cutoff_time]
            if not requests:
                actions_to_remove.append(action)
        
        for action in actions_to_remove:
            del actions[action]
        
        if not actions:
            users_to_remove.append(user_id)
    
    for user_id in users_to_remove:
        del _rate_limit_storage[user_id]


def sanitize_error_message(error: Exception) -> str:
    """
    Очистить сообщение об ошибке от чувствительной информации.
    
    Args:
        error: Объект исключения
        
    Returns:
        str: Безопасное сообщение об ошибке
    """
    error_type = type(error).__name__
    error_message = str(error)
    
    # Удаляем чувствительную информацию
    sensitive_patterns = [
        r'password[=:]\s*\S+',
        r'token[=:]\s*\S+',
        r'key[=:]\s*\S+',
        r'secret[=:]\s*\S+',
        r'C:\\Users\\[^\\]+',
        r'/home/[^/]+',
        r'\.env',
        r'\.db',
    ]
    
    for pattern in sensitive_patterns:
        error_message = re.sub(pattern, '[REDACTED]', error_message, flags=re.IGNORECASE)
    
    # Возвращаем общее сообщение без деталей
    return f"Произошла ошибка ({error_type}). Обратитесь к администратору."


# Лимиты для разных действий
RATE_LIMITS = {
    'get_code': (5, 60),      # 5 запросов в минуту
    'register': (3, 300),     # 3 регистрации в 5 минут
    'request_access': (10, 60),  # 10 запросов в минуту
    'check_email': (3, 60),   # 3 проверки в минуту
    'my_code': (5, 60),      # 5 запросов в минуту
    'default': (20, 60),      # 20 запросов в минуту по умолчанию
}
