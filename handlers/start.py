from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from config import MESSAGES
from database.db_manager import db
from utils.keyboards import (
    create_main_menu_keyboard,
    create_help_keyboard
)
from utils.messages import (
    format_user_status,
    format_permissions_count,
    format_help_section,
    format_tips_message,
    format_request_access_hint,
    REQUEST_ACCESS_SOLO_MESSAGE,
)

# Создаём роутер для этого обработчика
router = Router()


@router.message(Command('start'))
async def cmd_start(message: Message):
    """
    Обработчик команды /start
    Показывает приветствие и главное меню с кнопками.

    Args:
        message: Объект сообщения от пользователя
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "друг"
    
    # Проверяем регистрацию
    user = db.get_user_by_telegram_id(user_id)
    is_registered = user is not None
    
    # Формируем приветствие
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        f"{MESSAGES['start']}\n\n"
    )
    
    # Добавляем статус пользователя
    if is_registered:
        welcome_text += f"{format_user_status(user)}\n\n"
        # Добавляем статистику разрешений
        permissions = db.get_my_permissions(user_id)
        welcome_text += f"{format_permissions_count(permissions)}\n\n"
    else:
        welcome_text += "⚠️ Ты ещё не зарегистрирован!\n"
        welcome_text += "Используй кнопку ниже для регистрации.\n\n"
    
    welcome_text += "💡 Используй кнопки ниже для быстрого доступа к функциям"
    
    # Создаём клавиатуру
    keyboard = create_main_menu_keyboard(is_registered=is_registered)
    
    await message.answer(
        text=welcome_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

    # Логируем в консоль для отладки
    print(f"👤 Пользователь {user_id} ({message.from_user.username}) запустил бота")


@router.message(Command('menu'))
async def cmd_menu(message: Message):
    """
    Обработчик команды /menu
    Показывает интерактивное главное меню.
    """
    user_id = message.from_user.id
    user = db.get_user_by_telegram_id(user_id)
    is_registered = user is not None
    
    menu_text = "🏠 <b>Главное меню</b>\n\n"
    
    if is_registered:
        menu_text += f"{format_user_status(user)}\n\n"
        permissions = db.get_my_permissions(user_id)
        menu_text += f"{format_permissions_count(permissions)}\n\n"
    else:
        menu_text += "❌ Ты ещё не зарегистрирован\n\n"
    
    menu_text += "Выбери действие:"
    
    keyboard = create_main_menu_keyboard(is_registered=is_registered)
    
    await message.answer(
        text=menu_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


@router.message(Command('help'))
async def cmd_help(message: Message):
    """
    Обработчик команды /help
    Показывает интерактивную справку с разделами.
    """
    help_text = (
        "❓ <b>Справка по боту</b>\n\n"
        "Выбери раздел справки:"
    )
    
    keyboard = create_help_keyboard()
    
    await message.answer(
        text=help_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


@router.message(Command('tips'))
async def cmd_tips(message: Message):
    """
    Обработчик команды /tips
    Показывает полезные советы.
    """
    tips_text = format_tips_message()
    
    keyboard = create_main_menu_keyboard(
        is_registered=db.get_user_by_telegram_id(message.from_user.id) is not None
    )
    
    await message.answer(
        text=tips_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )


# Обработчики callback для меню
@router.callback_query(F.data == "menu_main")
async def callback_menu_main(callback: CallbackQuery):
    """Обработчик кнопки 'Главное меню'"""
    user_id = callback.from_user.id
    user = db.get_user_by_telegram_id(user_id)
    is_registered = user is not None
    
    menu_text = "🏠 <b>Главное меню</b>\n\n"
    
    if is_registered:
        menu_text += f"{format_user_status(user)}\n\n"
        permissions = db.get_my_permissions(user_id)
        menu_text += f"{format_permissions_count(permissions)}\n\n"
    else:
        menu_text += "❌ Ты ещё не зарегистрирован\n\n"
    
    menu_text += "Выбери действие:"
    
    keyboard = create_main_menu_keyboard(is_registered=is_registered)
    
    await callback.message.edit_text(
        text=menu_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "menu_register")
async def callback_menu_register(callback: CallbackQuery):
    """Обработчик кнопки 'Зарегистрироваться'"""
    await callback.answer("Используй команду /register")
    await callback.message.answer(
        text=MESSAGES['register_start'],
        parse_mode='HTML'
    )


@router.callback_query(F.data == "menu_get_code")
async def callback_menu_get_code(callback: CallbackQuery):
    """Обработчик кнопки 'Получить код'"""
    await callback.answer("Используй команду /get_code")
    await callback.message.answer(
        text=(
            "🔐 <b>Получить код</b>\n\n"
            "Используй команду:\n"
            "<code>/get_code @username</code>\n"
            "или\n"
            "<code>/get_code email@example.com</code>\n\n"
            "Или просто напиши <code>/get_code</code> для интерактивного выбора"
        ),
        parse_mode='HTML'
    )


@router.callback_query(F.data == "menu_permissions")
async def callback_menu_permissions(callback: CallbackQuery):
    """Обработчик кнопки 'Мои разрешения'"""
    await callback.answer("Используй команду /my_permissions")
    await callback.message.answer(
        text="Используй команду /my_permissions для просмотра разрешений",
        parse_mode='HTML'
    )


@router.callback_query(F.data == "menu_request_access")
async def callback_menu_request_access(callback: CallbackQuery):
    """Обработчик кнопки 'Запросить доступ'"""
    await callback.answer("Используй команду /request_access")
    try:
        total = db.count_registered_users()
    except Exception:
        total = 0
    if total <= 1:
        text = REQUEST_ACCESS_SOLO_MESSAGE
    else:
        text = format_request_access_hint(total)
    await callback.message.answer(text=text, parse_mode='HTML')


@router.callback_query(F.data == "menu_stats")
async def callback_menu_stats(callback: CallbackQuery):
    """Обработчик кнопки 'Статистика'"""
    user_id = callback.from_user.id
    user = db.get_user_by_telegram_id(user_id)
    
    if not user:
        await callback.answer("Сначала зарегистрируйся!", show_alert=True)
        return
    
    permissions = db.get_my_permissions(user_id)
    stats_text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"{format_user_status(user)}\n\n"
        f"{format_permissions_count(permissions)}"
    )
    
    keyboard = create_main_menu_keyboard(is_registered=True)
    
    await callback.message.edit_text(
        text=stats_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "menu_refresh")
async def callback_menu_refresh(callback: CallbackQuery):
    """Обработчик кнопки 'Обновить меню'"""
    user_id = callback.from_user.id
    user = db.get_user_by_telegram_id(user_id)
    is_registered = user is not None
    
    menu_text = "🏠 <b>Главное меню</b>\n\n"
    
    if is_registered:
        menu_text += f"{format_user_status(user)}\n\n"
        permissions = db.get_my_permissions(user_id)
        menu_text += f"{format_permissions_count(permissions)}\n\n"
    else:
        menu_text += "❌ Ты ещё не зарегистрирован\n\n"
    
    menu_text += "Выбери действие:"
    
    keyboard = create_main_menu_keyboard(is_registered=is_registered)
    
    await callback.message.edit_text(
        text=menu_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer("✅ Меню обновлено")


# Обработчики callback для help
@router.callback_query(F.data.startswith("help_"))
async def callback_help_section(callback: CallbackQuery):
    """Обработчик разделов справки"""
    section = callback.data.replace("help_", "", 1)
    
    # Валидируем раздел справки
    valid_sections = ['register', 'get_code', 'permissions', 'faq', 'tips']
    if section not in valid_sections:
        await callback.answer("❌ Неверный раздел!", show_alert=True)
        return
    
    help_text = format_help_section(section)
    keyboard = create_help_keyboard()
    
    await callback.message.edit_text(
        text=help_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    await callback.answer()