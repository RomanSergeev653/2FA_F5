import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, DEBUG
from database.models import init_database

# Импортируем роутеры из handlers
from handlers import start
from handlers import registration
from handlers import permissions
from handlers import codes

async def main():
    """
    Главная функция запуска бота.
    """

    # Настройка логирования
    if DEBUG:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(levelname)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("🤖 Запуск Telegram бота для 2FA кодов")
    logger.info("=" * 60)

    # Инициализируем базу данных
    logger.info("📦 Инициализация базы данных...")
    init_database()
    logger.info("✅ База данных готова")

    # Создаём бота и диспетчер
    logger.info("🔧 Создание бота...")
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    logger.info("✅ Бот создан")

    dp = Dispatcher()

    # Подключаем роутеры (обработчики команд)
    logger.info("📝 Подключение обработчиков...")
    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(permissions.router)
    dp.include_router(codes.router)
    logger.info("✅ Все обработчики подключены")

    logger.info("✅ Бот готов к работе!")
    logger.info("Нажми Ctrl+C для остановки\n")

    # Запускаем polling (бот начинает получать сообщения)
    try:
        # Пропускаем все накопившиеся сообщения
        logger.info("⏭️  Пропускаю старые сообщения...")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Старые сообщения пропущены")

        logger.info("🚀 Бот запущен и ожидает сообщения...")
        await dp.start_polling(bot)

    except KeyboardInterrupt:
        logger.info("\n👋 Остановка бота...")
    finally:
        await bot.session.close()
        logger.info("✅ Бот остановлен")

def check_existing_instances():
    """
    Проверяет, не запущен ли уже другой экземпляр бота.
    """
    import subprocess
    try:
        # Ищем процессы python с main.py
        result = subprocess.run(
            ['pgrep', '-f', 'python.*main.py'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            # Исключаем текущий процесс
            current_pid = str(os.getpid())
            other_pids = [pid for pid in pids if pid and pid != current_pid]
            if other_pids:
                print(f"⚠️  Обнаружены другие запущенные экземпляры бота (PID: {', '.join(other_pids)})")
                print("Остановите их перед запуском нового экземпляра:")
                print(f"  pkill -f 'python.*main.py'")
                return False
        return True
    except Exception as e:
        # Если команда не найдена (например, на Windows), пропускаем проверку
        return True


if __name__ == '__main__':
    """
    Точка входа в программу.
    Запускаем асинхронную функцию main()
    """
    # Проверяем, не запущен ли уже другой экземпляр
    if not check_existing_instances():
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")