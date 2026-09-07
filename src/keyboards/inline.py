import math
from typing import List, Dict, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.database.models import Lesson, QueueEntry


def get_lessons_keyboard(lessons: List[Lesson], counts: Dict[int, int]) -> InlineKeyboardMarkup:
    buttons = []
    for lesson in lessons:
        occupied = counts.get(lesson.id, 0)
        btn_text = f"📚 {lesson.subject} | {lesson.datetime_str} ({occupied}/{lesson.max_slots})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"lesson_view:{lesson.id}")])

    bottom_row = [
        InlineKeyboardButton(text="➕ Добавить пару", callback_data="lesson_create"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="lessons_refresh"),
    ]
    buttons.append(bottom_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_queue_keyboard(
    lesson_id: int,
    user_entry: Optional[QueueEntry],
    can_delete: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []

    if user_entry is None:
        buttons.append([
            InlineKeyboardButton(
                text="⚡ Быстрая запись (1-е своб.)",
                callback_data=f"queue_quick:{lesson_id}",
            ),
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🎯 Выбрать место",
                callback_data=f"queue_slots:{lesson_id}:1",
            ),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text=f"🔄 Сменить место (сейчас #{user_entry.position})",
                callback_data=f"queue_slots:{lesson_id}:1",
            ),
        ])
        buttons.append([
            InlineKeyboardButton(
                text="❌ Покинуть очередь",
                callback_data=f"queue_leave:{lesson_id}",
            ),
        ])

    nav_row = [
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"queue_refresh:{lesson_id}"),
        InlineKeyboardButton(text="⬅️ К списку пар", callback_data="lessons_list"),
    ]
    buttons.append(nav_row)

    if can_delete:
        buttons.append([
            InlineKeyboardButton(
                text="🗑️ Удалить эту пару",
                callback_data=f"lesson_del_ask:{lesson_id}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_slots_keyboard(
    lesson_id: int,
    max_slots: int,
    queue_entries: List[QueueEntry],
    current_user_id: int,
    page: int = 1,
    per_page: int = 10,
) -> InlineKeyboardMarkup:
    occupied_map: Dict[int, QueueEntry] = {e.position: e for e in queue_entries}
    total_pages = max(1, math.ceil(max_slots / per_page))
    page = max(1, min(page, total_pages))

    start_slot = (page - 1) * per_page + 1
    end_slot = min(page * per_page, max_slots)

    buttons = []
    # 2 buttons per row for slots
    current_row = []
    for slot_num in range(start_slot, end_slot + 1):
        if slot_num in occupied_map:
            entry = occupied_map[slot_num]
            if entry.user_id == current_user_id:
                label = f"✅ #{slot_num} (Вы)"
                cb = f"slot_occupied:{lesson_id}:{slot_num}:self"
            else:
                short_name = entry.user_full_name.split()[0] if entry.user_full_name else "Занято"
                if len(short_name) > 10:
                    short_name = short_name[:9] + "…"
                label = f"🔴 #{slot_num} {short_name}"
                cb = f"slot_occupied:{lesson_id}:{slot_num}:other"
        else:
            label = f"🟢 #{slot_num} Свободно"
            cb = f"slot_take:{lesson_id}:{slot_num}"

        current_row.append(InlineKeyboardButton(text=label, callback_data=cb))
        if len(current_row) == 2:
            buttons.append(current_row)
            current_row = []

    if current_row:
        buttons.append(current_row)

    # Pagination controls
    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"queue_slots:{lesson_id}:{page - 1}")
        )
    nav_row.append(
        InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="noop")
    )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"queue_slots:{lesson_id}:{page + 1}")
        )
    buttons.append(nav_row)

    # Bottom action buttons
    buttons.append([
        InlineKeyboardButton(text="⚡ В первое свободное", callback_data=f"queue_quick:{lesson_id}"),
        InlineKeyboardButton(text="⬅️ К очереди", callback_data=f"queue_view:{lesson_id}"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_confirm_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="⚠️ Да, удалить пару",
                callback_data=f"lesson_del_confirm:{lesson_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"queue_view:{lesson_id}",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить ФИО", callback_data="profile_change_name")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
