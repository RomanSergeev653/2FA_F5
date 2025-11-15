import asyncio
import logging
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
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    print("=" * 50)
    print("🤖 Запуск Telegram бота для 2FA кодов")
    print("=" * 50)

    # Инициализируем базу данных
    print("\n📦 Инициализация базы данных...")
    init_database()

    # Создаём бота и диспетчер
    print("\n🔧 Создание бота...")
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()

    # Подключаем роутеры (обработчики команд)
    print("📝 Подключение обработчиков...")
    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(permissions.router)
    dp.include_router(codes.router)

    print("\n✅ Бот готов к работе!")
    print("Нажми Ctrl+C для остановки\n")

    # Запускаем polling (бот начинает получать сообщения)
    try:
        # Пропускаем все накопившиеся сообщения
        await bot.delete_webhook(drop_pending_updates=True)

        print("⏭️  Все старые сообщения пропущены")

        await dp.start_polling(bot)

    except KeyboardInterrupt:
        print("\n\n👋 Остановка бота...")
    finally:
        await bot.session.close()
        print("✅ Бот остановлен")

if __name__ == '__main__':
    """
    Точка входа в программу.
    Запускаем асинхронную функцию main()
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")