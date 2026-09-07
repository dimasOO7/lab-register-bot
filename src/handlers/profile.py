from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.database.repository import Repository
from src.states.forms import ProfileForm
from src.keyboards.reply import get_main_keyboard, get_cancel_keyboard
from src.keyboards.inline import get_profile_keyboard
from src.config import settings

router = Router(name="profile")


@router.message(Command("profile"))
@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message, repo: Repository):
    user_id = message.from_user.id
    user = await repo.get_user(user_id)
    is_admin = settings.is_admin(user_id)

    if not user:
        name = message.from_user.full_name or "Не указано"
    else:
        name = user.full_name

    role_str = "👑 Администратор" if is_admin else "🎓 Студент"
    username_str = f"@{message.from_user.username}" if message.from_user.username else "нет username"

    text = (
        "👤 <b>Ваш профиль:</b>\n\n"
        f"• <b>ФИО:</b> {name}\n"
        f"• <b>Telegram:</b> {username_str}\n"
        f"• <b>ID:</b> <code>{user_id}</code>\n"
        f"• <b>Статус:</b> {role_str}\n\n"
        "<i>Это имя отображается в очереди на сдачу работ.</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_profile_keyboard())


@router.callback_query(F.data == "profile_change_name")
async def ask_new_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileForm.waiting_for_name)
    await callback.message.answer(
        "✏️ Введите ваши <b>Имя и Фамилию</b> (например: <i>Иванов Иван</i>):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(ProfileForm.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext, repo: Repository):
    new_name = message.text.strip()
    if len(new_name) < 2 or len(new_name) > 64:
        await message.answer(
            "⚠️ Имя должно быть длиной от 2 до 64 символов. Пожалуйста, попробуйте ещё раз:"
        )
        return

    user_id = message.from_user.id
    username = message.from_user.username

    await repo.upsert_user(user_id=user_id, username=username, full_name=new_name)
    await state.clear()

    is_admin = settings.is_admin(user_id)
    await message.answer(
        f"✅ Отлично! Ваше имя сохранено как: <b>{new_name}</b>.\n"
        "Теперь вы можете полноценно записываться на лабораторные работы!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(is_admin),
    )
