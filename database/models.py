import sqlite3
import os
from datetime import datetime

# Путь к файлу базы данных
DB_PATH = 'database/bot.db'


def init_database():
    """
    Инициализация базы данных.
    Создаёт таблицы, если их ещё нет.
    """
    # Создаём папку database, если её нет
    os.makedirs('database', exist_ok=True)

    # Подключаемся к базе данных (если файла нет - создастся автоматически)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Создаём таблицу пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            email_provider TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            last_code_request TEXT
        )
    ''')

    # Создаём таблицу разрешений доступа
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            requester_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            responded_at TEXT,
            FOREIGN KEY (owner_id) REFERENCES users (telegram_id),
            FOREIGN KEY (requester_id) REFERENCES users (telegram_id),
            UNIQUE(owner_id, requester_id)
        )
    ''')

    # Создаём таблицу логов (для отслеживания действий)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            details TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    ''')

    # Сохраняем изменения и закрываем соединение
    conn.commit()
    conn.close()

    print("✅ База данных инициализирована")


def get_connection():
    """
    Получить подключение к базе данных.

    Returns:
        sqlite3.Connection: Объект подключения к БД
    """
    conn = sqlite3.connect(DB_PATH)
    # Включаем возврат результатов в виде словарей (удобнее работать)
    conn.row_factory = sqlite3.Row
    return conn


# Если запустить этот файл напрямую - инициализируем БД
if __name__ == '__main__':
    init_database()
    print("База данных создана успешно!")