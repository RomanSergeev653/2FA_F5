import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from database.models import get_connection


class DatabaseManager:
    """
    Класс для работы с базой данных.
    Все операции с БД идут через этот класс.
    """

    @staticmethod
    def add_user(telegram_id: int, username: str, email: str,
                 encrypted_password: str, email_provider: str) -> bool:
        """
        Добавить нового пользователя в базу.

        Args:
            telegram_id: ID пользователя в Telegram
            username: @username без @
            email: Email адрес
            encrypted_password: Зашифрованный пароль
            email_provider: gmail, yandex, mail.ru и т.д.

        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            registered_at = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO users (telegram_id, username, email, encrypted_password, 
                                 email_provider, registered_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (telegram_id, username, email, encrypted_password,
                  email_provider, registered_at))

            conn.commit()
            conn.close()

            # Логируем действие
            DatabaseManager.log_action(telegram_id, 'registration',
                                       f'Registered with email: {email}')

            return True

        except sqlite3.IntegrityError:
            # Пользователь уже существует
            return False
        except Exception as e:
            print(f"❌ Ошибка добавления пользователя: {e}")
            return False

    @staticmethod
    def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict]:
        """
        Получить пользователя по Telegram ID.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            Dict с данными пользователя или None если не найден
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM users WHERE telegram_id = ?
            ''', (telegram_id,))

            user = cursor.fetchone()
            conn.close()

            if user:
                # Преобразуем sqlite3.Row в словарь
                return dict(user)
            return None

        except Exception as e:
            print(f"❌ Ошибка получения пользователя: {e}")
            return None

    @staticmethod
    def get_user_by_username(username: str) -> Optional[Dict]:
        """
        Получить пользователя по username.

        Args:
            username: @username (с @ или без)

        Returns:
            Dict с данными пользователя или None
        """
        # Убираем @ если есть
        username = username.lstrip('@')

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM users WHERE username = ?
            ''', (username,))

            user = cursor.fetchone()
            conn.close()

            if user:
                return dict(user)
            return None

        except Exception as e:
            print(f"❌ Ошибка получения пользователя по username: {e}")
            return None

    @staticmethod
    def update_last_code_request(telegram_id: int):
        """
        Обновить время последнего запроса кода.

        Args:
            telegram_id: ID пользователя
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            cursor.execute('''
                UPDATE users 
                SET last_code_request = ?
                WHERE telegram_id = ?
            ''', (now, telegram_id))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"❌ Ошибка обновления last_code_request: {e}")

    @staticmethod
    def create_permission_request(owner_id: int, requester_id: int) -> bool:
        """
        Создать запрос на доступ к кодам.

        Args:
            owner_id: ID владельца почты
            requester_id: ID того, кто запрашивает доступ

        Returns:
            bool: True если успешно создан
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            requested_at = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO permissions (owner_id, requester_id, status, requested_at)
                VALUES (?, ?, 'pending', ?)
            ''', (owner_id, requester_id, requested_at))

            conn.commit()
            conn.close()

            # Логируем
            DatabaseManager.log_action(
                requester_id,
                'permission_request',
                f'Requested access to user {owner_id}'
            )

            return True

        except sqlite3.IntegrityError:
            # Запрос уже существует
            return False
        except Exception as e:
            print(f"❌ Ошибка создания запроса: {e}")
            return False

    @staticmethod
    def update_permission(owner_id: int, requester_id: int,
                          new_status: str) -> bool:
        """
        Обновить статус разрешения (одобрить/отклонить).

        Args:
            owner_id: ID владельца
            requester_id: ID запрашивающего
            new_status: 'approved' или 'denied'

        Returns:
            bool: True если успешно
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            responded_at = datetime.now().isoformat()

            cursor.execute('''
                UPDATE permissions
                SET status = ?, responded_at = ?
                WHERE owner_id = ? AND requester_id = ?
            ''', (new_status, responded_at, owner_id, requester_id))

            conn.commit()
            conn.close()

            # Логируем
            DatabaseManager.log_action(
                owner_id,
                'permission_response',
                f'{new_status} access to user {requester_id}'
            )

            return True

        except Exception as e:
            print(f"❌ Ошибка обновления разрешения: {e}")
            return False

    @staticmethod
    def check_permission(owner_id: int, requester_id: int) -> bool:
        """
        Проверить, есть ли у requester разрешение на доступ к кодам owner.

        Args:
            owner_id: ID владельца почты
            requester_id: ID запрашивающего

        Returns:
            bool: True если разрешение есть и статус 'approved'
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT status FROM permissions
                WHERE owner_id = ? AND requester_id = ? AND status = 'approved'
            ''', (owner_id, requester_id))

            result = cursor.fetchone()
            conn.close()

            return result is not None

        except Exception as e:
            print(f"❌ Ошибка проверки разрешения: {e}")
            return False

    @staticmethod
    def get_my_permissions(telegram_id: int) -> Dict[str, List[Dict]]:
        """
        Получить все разрешения пользователя (кому дал, от кого получил).

        Args:
            telegram_id: ID пользователя

        Returns:
            Dict с ключами 'given' (кому дал) и 'received' (от кого получил)
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Разрешения, которые дал этот пользователь
            cursor.execute('''
                SELECT p.*, u.username as requester_username
                FROM permissions p
                JOIN users u ON p.requester_id = u.telegram_id
                WHERE p.owner_id = ? AND p.status = 'approved'
            ''', (telegram_id,))

            given = [dict(row) for row in cursor.fetchall()]

            # Разрешения, которые получил этот пользователь
            cursor.execute('''
                SELECT p.*, u.username as owner_username
                FROM permissions p
                JOIN users u ON p.owner_id = u.telegram_id
                WHERE p.requester_id = ? AND p.status = 'approved'
            ''', (telegram_id,))

            received = [dict(row) for row in cursor.fetchall()]

            conn.close()

            return {
                'given': given,
                'received': received
            }

        except Exception as e:
            print(f"❌ Ошибка получения разрешений: {e}")
            return {'given': [], 'received': []}

    @staticmethod
    def revoke_permission(owner_id: int, requester_id: int) -> bool:
        """
        Отозвать разрешение (удалить из БД).

        Args:
            owner_id: ID владельца
            requester_id: ID того, у кого отзываем доступ

        Returns:
            bool: True если успешно
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM permissions
                WHERE owner_id = ? AND requester_id = ?
            ''', (owner_id, requester_id))

            conn.commit()
            conn.close()

            # Логируем
            DatabaseManager.log_action(
                owner_id,
                'permission_revoked',
                f'Revoked access from user {requester_id}'
            )

            return True

        except Exception as e:
            print(f"❌ Ошибка отзыва разрешения: {e}")
            return False

    @staticmethod
    def log_action(user_id: int, action_type: str, details: str = ''):
        """
        Записать действие в лог.

        Args:
            user_id: ID пользователя
            action_type: Тип действия (registration, permission_request и т.д.)
            details: Подробности
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            timestamp = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO action_logs (user_id, action_type, details, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, action_type, details, timestamp))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"❌ Ошибка записи лога: {e}")


# Создаём глобальный экземпляр для удобного импорта
db = DatabaseManager()