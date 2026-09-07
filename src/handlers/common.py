from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.database.repository import Repository
from src.keyboards.reply import get_main_keyboard, get_cancel_keyboard
from src.states.forms import ProfileForm
from src.config import settings

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, repo: Repository):
    await state.clear()
    user_id = message.from_user.id
    user = await repo.get_user(user_id)

    if not user:
        # User not registered yet, prompt for Full Name
        suggested_name = ""
        if message.from_user.first_name:
            suggested_name = message.from_user.first_name
            if message.from_user.last_name:
                suggested_name += f" {message.from_user.last_name}"

        await state.set_state(ProfileForm.waiting_for_name)
        text = (
            "👋 <b>Добро пожаловать в бота для записи на сдачу лабораторных работ!</b>\n\n"
            "Чтобы преподаватель и одногруппники видели тебя в очереди, "
            "пожалуйста, укажи свои <b>Имя и Фамилию</b> (например: <i>Иванов Иван</i>):"
        )
        if suggested_name:
            text += f"\n\n<i>Можешь отправить своё имя или нажать кнопку ниже, если подходит.</i>"
        await message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        is_admin = settings.is_admin(user_id)
        text = (
            f"👋 С возвращением, <b>{user.full_name}</b>!\n\n"
            "Используй кнопки меню для просмотра очередей и записи на пары."
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard(is_admin))


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    text = (
        "📖 <b>Справка по использованию бота</b>\n\n"
        "• <b>📋 Список пар / Очереди:</b> просмотр всех доступных пар и текущих списков студентов.\n"
        "• <b>⚡ Быстрая запись:</b> мгновенная запись на <i>первое свободное место</i> в очереди выбранной пары.\n"
        "• <b>🎯 Выбор места:</b> ручной выбор любого свободного номера слота (например, если хотите сдавать 5-м или 10-м).\n"
        "• <b>🔄 Смена места / Выход:</b> в любой момент можно поменять свой номер или покинуть очередь.\n"
        "• <b>👤 Мой профиль:</b> просмотр и редактирование своего ФИО.\n"
        "• <b>➕ Добавить пару:</b> создание новой пары (предмет, дата и время, описание, количество мест).\n"
        "• <b>🗑️ Автоудаление:</b> прошедшие пары автоматически удаляются по окончанию дня проведения."
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "❌ Отмена")
async def btn_cancel(message: Message, state: FSMContext, repo: Repository):
    current_state = await state.get_state()
    await state.clear()
    user_id = message.from_user.id
    user = await repo.get_user(user_id)
    is_admin = settings.is_admin(user_id)

    if current_state:
        text = "❌ Действие отменено."
    else:
        text = "Главное меню."

    await message.answer(text, reply_markup=get_main_keyboard(is_admin))


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()
