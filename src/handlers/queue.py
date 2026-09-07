from typing import Optional, List
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.database.models import Lesson, QueueEntry
from src.database.repository import Repository
from src.keyboards.inline import (
    get_queue_keyboard,
    get_slots_keyboard,
    get_profile_keyboard,
)
from src.states.forms import ProfileForm
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
        f"👥 <b>Занято мест:</b> {occupied_count} из {lesson.max_slots}\n"
    )

    if user_entry:
        header += f"⭐ <b>Ваше место:</b> #{user_entry.position}\n"

    header += "\n📋 <b>Текущая очередь:</b>\n"

    if not queue_entries:
        body = "<i>Очередь пока пуста. Будьте первыми! Нажмите кнопку «Быстрая запись» ниже.</i>"
    else:
        occupied_dict = {e.position: e for e in queue_entries}
        max_pos = max(occupied_dict.keys())
        lines = []

        # List all positions up to max_pos
        for p in range(1, max_pos + 1):
            if p in occupied_dict:
                e = occupied_dict[p]
                uname = f" (@{e.user_username})" if e.user_username else ""
                if e.user_id == current_user_id:
                    lines.append(f"👉 <b>#{p}</b> <b>{e.user_full_name}</b>{uname} <i>(Вы)</i>")
                else:
                    lines.append(f"▫️ <b>#{p}</b> {e.user_full_name}{uname}")
            else:
                lines.append(f"▫️ <b>#{p}</b> <i>[Свободно]</i>")

        # If max_pos < max_slots, indicate that more slots are available
        if max_pos < lesson.max_slots:
            next_free = max_pos + 1
            lines.append(f"▫️ <b>#{next_free}…#{lesson.max_slots}</b> <i>[Свободно]</i>")

        body = "\n".join(lines)

    return header + body


@router.callback_query(F.data.startswith("lesson_view:"))
@router.callback_query(F.data.startswith("queue_view:"))
async def view_queue(callback: CallbackQuery, repo: Repository):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена или уже удалена.", show_alert=True)
        return

    user_id = callback.from_user.id
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)

    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("queue_refresh:"))
async def refresh_queue(callback: CallbackQuery, repo: Repository):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена или уже удалена.", show_alert=True)
        return

    user_id = callback.from_user.id
    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)

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
        # Prompt user to enter name first
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
async def show_slots(callback: CallbackQuery, repo: Repository):
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

    cur_info = f"\n👉 Вы записаны на <b>место #{user_entry.position}</b>" if user_entry else ""

    text = (
        f"🎯 <b>Выбор места в очереди</b>\n"
        f"📚 <b>{lesson.subject}</b> ({lesson.datetime_str})\n"
        f"{cur_info}\n"
        "Нажмите на свободный зеленый слот 🟢, чтобы занять его:\n"
        "<i>(Если вы уже в очереди, выбор другого слота переместит вас на него)</i>"
    )
    keyboard = get_slots_keyboard(
        lesson_id=lesson_id,
        max_slots=lesson.max_slots,
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


@router.callback_query(F.data.startswith("slot_occupied:"))
async def slot_occupied_clicked(callback: CallbackQuery, repo: Repository):
    parts = callback.data.split(":")
    lesson_id = int(parts[1])
    position = int(parts[2])
    occ_type = parts[3] if len(parts) > 3 else "other"

    if occ_type == "self":
        await callback.answer(f"ℹ️ Вы уже занимаете место #{position}.", show_alert=True)
    else:
        # Find who occupies it
        queue_entries = await repo.get_queue_for_lesson(lesson_id)
        entry = next((e for e in queue_entries if e.position == position), None)
        occupant = entry.user_full_name if entry else "другим студентом"
        await callback.answer(f"⚠️ Место #{position} уже занято: {occupant}", show_alert=True)


@router.callback_query(F.data.startswith("queue_leave:"))
async def leave_queue_handler(callback: CallbackQuery, repo: Repository):
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

    queue_entries = await repo.get_queue_for_lesson(lesson_id)
    user_entry = await repo.get_user_entry(lesson_id, user_id)
    can_delete = settings.is_admin(user_id) or lesson.created_by == user_id
    text = format_queue_text(lesson, queue_entries, user_id, user_entry)
    keyboard = get_queue_keyboard(lesson_id, user_entry, can_delete=can_delete)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
