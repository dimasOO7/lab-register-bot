from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_keyboard(is_admin: bool = True) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📋 Список пар / Очереди")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="➕ Добавить пару")],
        [KeyboardButton(text="ℹ️ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="⏭️ Пропустить")],
        [KeyboardButton(text="❌ Отмена")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
