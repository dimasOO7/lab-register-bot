from typing import Optional, List
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.database.models import Lesson, QueueEntry
from src.database.repository import Repository
from src.keyboards.inline import (
    get_queue_keyboard,
    get_slots_keyboard,
)
from src.states.forms import ProfileForm, QueueSlotForm
from src.config import settings

router = Router(name="queue")


def format_queue_text(
    lesson: Lesson,
    queue_entries: List[QueueEntry],
    current_user_id: int,
    user_entry: Optional[QueueEntry],
) -> str:
    desc_part = f"\n📍 <b>Инфо:</b> {lesson.description}" if lesson.description else ""
    occupied_count = len(queue_entries)

    header = (
        f"📚 <b>Предмет:</b> {lesson.subject}\n"
        f"📅 <b>Дата и время:</b> {lesson.datetime_str}{desc_part}\n"
        f"👥 <b>Записано в очередь:</b> {occupied_count} чел.\n"
    )

    if user_entry:
        header += f"⭐ <b>Ваше место:</b> #{user_entry.position}\n"

    header += "\n📋 <b>Текущая очередь:</b>\n"

    if not queue_entries:
        body = "<i>Очередь пока пуста. Будьте первыми! Нажмите кнопку «Быстрая запись» или отправьте 1 в чат.</i>"
    else:
        lines = []
        for e in queue_entries:
            uname = f" (@{e.user_username})" if e.user_username else ""
            if e.user_id == current_user_id:
                lines.append(f"👉 <b>{e.position}.</b> <b>{e.user_full_name}</b>{uname} <i>(Вы)</i>")
            else:
                lines.append(f"<b>{e.position}.</b> {e.user_full_name}{uname}")

        body = "\n".join(lines)

    occupied_positions = {e.position for e in queue_entries}
    next_free = 1
    while next_free in occupied_positions:
        next_free += 1

    footer = (
        f"\n\n💬 <i>Чтобы записаться на желаемое место, <b>отправьте его номер в чат</b> "
        f"(например: <code>{next_free}</code>, <code>10</code> или любое другое число) либо выберите кнопками ниже:</i>"
    )
    return header + body + footer


@router.callback_query(F.data.startswith("lesson_view:"))
@router.callback_query(F.data.startswith("queue_view:"))
async def view_queue(callback: CallbackQuery, repo: Repository, state: FSMContext):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена или уже удалена.", show_alert=True)
        return

    user_id = callback.from_user.id
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)

    # Set state so user can simply type desired slot number
    await state.set_state(QueueSlotForm.waiting_for_slot)
    await state.update_data(current_lesson_id=lesson_id)

    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("queue_refresh:"))
async def refresh_queue(callback: CallbackQuery, repo: Repository, state: FSMContext):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена или уже удалена.", show_alert=True)
        return

    user_id = callback.from_user.id
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)

    await state.set_state(QueueSlotForm.waiting_for_slot)
    await state.update_data(current_lesson_id=lesson_id)

    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("🔄 Очередь обновлена")


@router.callback_query(F.data.startswith("queue_quick:"))
async def quick_join_queue(callback: CallbackQuery, repo: Repository, state: FSMContext):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена!", show_alert=True)
        return

    user_id = callback.from_user.id
    user = await repo.get_user(user_id)

    if not user:
        await state.set_state(ProfileForm.waiting_for_name)
        await callback.answer("⚠️ Сначала укажите ваше ФИО!", show_alert=True)
        await callback.message.answer(
            "⚠️ Для записи в очередь необходимо указать свои <b>Имя и Фамилию</b>.\n"
            "Пожалуйста, напишите их в ответном сообщении:",
            parse_mode="HTML",
        )
        return

    success, msg, assigned_pos = await repo.join_queue_at_first_free(lesson_id, user_id)
    await callback.answer(msg, show_alert=True)

    await state.set_state(QueueSlotForm.waiting_for_slot)
    await state.update_data(current_lesson_id=lesson_id)

    # Refresh queue view
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)
    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


@router.callback_query(F.data.startswith("queue_slots:"))
async def show_slots(callback: CallbackQuery, repo: Repository, state: FSMContext):
    parts = callback.data.split(":")
    lesson_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена!", show_alert=True)
        return

    user_id = callback.from_user.id
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)

    await state.set_state(QueueSlotForm.waiting_for_slot)
    await state.update_data(current_lesson_id=lesson_id)

    cur_info = f"\n👉 Вы записаны на <b>место #{user_entry.position}</b>" if user_entry else ""

    text = (
        f"🎯 <b>Выбор места в очереди</b>\n"
        f"📚 <b>{lesson.subject}</b> ({lesson.datetime_str})\n"
        f"{cur_info}\n\n"
        "Нажмите на свободный зеленый слот 🟢 ниже либо <b>просто отправьте желаемый номер сообщением в чат</b>:\n"
        "<i>(Если вы уже в очереди, выбор другого слота переместит вас на него)</i>"
    )
    keyboard = get_slots_keyboard(
        lesson_id=lesson_id,
        queue_entries=queue_entries,
        current_user_id=user_id,
        page=page,
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("slot_take:"))
async def take_slot(callback: CallbackQuery, repo: Repository, state: FSMContext):
    parts = callback.data.split(":")
    lesson_id = int(parts[1])
    position = int(parts[2])

    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена!", show_alert=True)
        return

    user_id = callback.from_user.id
    user = await repo.get_user(user_id)
    if not user:
        await state.set_state(ProfileForm.waiting_for_name)
        await callback.answer("⚠️ Сначала укажите ваше ФИО!", show_alert=True)
        await callback.message.answer(
            "⚠️ Для записи в очередь необходимо указать свои <b>Имя и Фамилию</b>.\n"
            "Пожалуйста, напишите их в ответном сообщении:",
            parse_mode="HTML",
        )
        return

    success, msg = await repo.join_queue_at_position(lesson_id, user_id, position)
    await callback.answer(msg, show_alert=True)

    await state.set_state(QueueSlotForm.waiting_for_slot)
    await state.update_data(current_lesson_id=lesson_id)

    # After slot choice, return to updated queue view
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)
    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


@router.message(QueueSlotForm.waiting_for_slot, F.text.regexp(r"^\s*\d+\s*$"))
async def handle_slot_text_input(message: Message, state: FSMContext, repo: Repository):
    position = int(message.text.strip())
    data = await state.get_data()
    lesson_id = data.get("current_lesson_id")
    if not lesson_id:
        await state.clear()
        return

    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await message.answer("Пара не найдена или уже удалена.")
        await state.clear()
        return

    user_id = message.from_user.id
    user = await repo.get_user(user_id)
    if not user:
        await state.set_state(ProfileForm.waiting_for_name)
        await message.answer(
            "⚠️ Для записи в очередь необходимо указать свои <b>Имя и Фамилию</b>.\n"
            "Пожалуйста, напишите их в ответном сообщении:",
            parse_mode="HTML",
        )
        return

    if position < 1 or position > 200:
        await message.answer(
            "⚠️ Номер места должен быть числом от 1 до 200. Пожалуйста, укажите корректный номер:"
        )
        return

    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    occupied_dict = {e.position: e for e in queue_entries}

    if position in occupied_dict:
        occ = occupied_dict[position]
        if occ.user_id == user_id:
            await message.answer(f"ℹ️ Вы уже записаны на место #{position}.")
            return
        else:
            await message.answer(
                f"❌ <b>Место #{position} уже занято</b> студентом {occ.user_full_name}!\n\n"
                "Пожалуйста, выберите другое свободное место (отправьте другой номер в чат):",
                parse_mode="HTML",
            )
            return

    # Valid free slot chosen by text
    success, msg = await repo.join_queue_at_position(lesson_id, user_id, position)
    if success:
        await message.answer(f"✅ {msg}")
        queue_entries = await repo.get_queue_for_lesson(lesson_id)
        user_entry = await repo.get_user_entry(lesson_id, user_id)
        can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
        text = format_queue_text(lesson, queue_entries, user_id, user_entry)
        keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(f"❌ {msg}\nПопробуйте ещё раз:")


@router.callback_query(F.data.startswith("slot_occupied:"))
async def slot_occupied_clicked(callback: CallbackQuery, repo: Repository):
    parts = callback.data.split(":")
    lesson_id = int(parts[1])
    position = int(parts[2])
    occ_type = parts[3] if len(parts) > 3 else "other"

    if occ_type == "self":
        await callback.answer(f"ℹ️ Вы уже занимаете место #{position}.", show_alert=True)
    else:
        queue_entries = await repo.get_queue_for_lesson(lesson_id)
        entry = next((e for e in queue_entries if e.position == position), None)
        occupant = entry.user_full_name if entry else "другим студентом"
        await callback.answer(f"⚠️ Место #{position} уже занято: {occupant}. Выберите свободный слот!", show_alert=True)


@router.callback_query(F.data.startswith("queue_leave:"))
async def leave_queue_handler(callback: CallbackQuery, repo: Repository, state: FSMContext):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена!", show_alert=True)
        return

    user_id = callback.from_user.id
    left = await repo.leave_queue(lesson_id, user_id)
    if left:
        await callback.answer("✅ Вы вышли из очереди.", show_alert=True)
    else:
        await callback.answer("Вы не были записаны в эту очередь.", show_alert=True)

    await state.set_state(QueueSlotForm.waiting_for_slot)
    await state.update_data(current_lesson_id=lesson_id)

    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)
    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
