from datetime import date
from typing import Dict
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from src.database.repository import Repository
from src.states.forms import LessonForm
from src.keyboards.reply import get_main_keyboard, get_cancel_keyboard, get_skip_keyboard
from src.keyboards.inline import get_lessons_keyboard, get_delete_confirm_keyboard
from src.utils.date_parser import parse_lesson_datetime
from src.config import settings

router = Router(name="lessons")


async def render_lessons_list(user_id: int, repo: Repository) -> tuple[str, InlineKeyboardMarkup]:
    lessons = await repo.get_active_lessons(auto_cleanup=True)
    if not lessons:
        text = (
            "📅 <b>Список пар пуст</b>\n\n"
            "На данный момент нет активных пар для записи на лабораторные.\n"
            "Вы можете создать новую пару с помощью кнопки ниже."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать пару", callback_data="lesson_create")],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="lessons_refresh")],
            ]
        )
        return text, keyboard

    # Calculate count of registered students for each lesson
    counts: Dict[int, int] = {}
    for lesson in lessons:
        queue = await repo.get_queue_for_lesson(lesson.id)
        counts[lesson.id] = len(queue)

    text = (
        "📅 <b>Доступные пары для сдачи лабораторных:</b>\n\n"
        "Выберите пару из списка ниже, чтобы посмотреть текущую очередь или записаться:"
    )
    keyboard = get_lessons_keyboard(lessons, counts)
    return text, keyboard


@router.message(Command("pairs"))
@router.message(F.text == "📋 Список пар / Очереди")
async def show_lessons_command(message: Message, repo: Repository):
    text, keyboard = await render_lessons_list(message.from_user.id, repo)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.in_(["lessons_list", "lessons_refresh"]))
async def show_lessons_callback(callback: CallbackQuery, repo: Repository):
    text, keyboard = await render_lessons_list(callback.from_user.id, repo)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("🔄 Список пар обновлен")


# ================= LESSON CREATION FSM =================

@router.message(Command("create_pair"))
@router.message(F.text == "➕ Добавить пару")
async def start_create_lesson_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not settings.is_admin(user_id):
        await message.answer(
            "⛔ Создание пар доступно только администраторам.",
            reply_markup=get_main_keyboard(False),
        )
        return

    await state.set_state(LessonForm.subject)
    await message.answer(
        "📚 <b>Шаг 1 из 4: Название предмета</b>\n\n"
        "Введите название дисциплины (например: <i>Операционные системы</i> или <i>Базы данных</i>):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.callback_query(F.data == "lesson_create")
async def start_create_lesson_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not settings.is_admin(user_id):
        await callback.answer("⛔ Создание пар доступно только администраторам.", show_alert=True)
        return

    await state.set_state(LessonForm.subject)
    await callback.message.answer(
        "📚 <b>Шаг 1 из 4: Название предмета</b>\n\n"
        "Введите название дисциплины (например: <i>Операционные системы</i> или <i>Базы данных</i>):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(LessonForm.subject, F.text)
async def process_subject(message: Message, state: FSMContext):
    subject = message.text.strip()
    if len(subject) < 2 or len(subject) > 100:
        await message.answer("⚠️ Название предмета должно быть от 2 до 100 символов. Попробуйте ещё раз:")
        return

    await state.update_data(subject=subject)
    await state.set_state(LessonForm.datetime_str)
    await message.answer(
        "📅 <b>Шаг 2 из 4: Дата и время проведения</b>\n\n"
        "Введите дату и время пары. Поддерживаются форматы:\n"
        "• <code>15.09.2026 14:00</code>\n"
        "• <code>15.09 14:00</code>\n"
        "• <code>сегодня 16:30</code> или <code>завтра 10:00</code>\n"
        "• <code>15.09</code> (без времени)",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(LessonForm.datetime_str, F.text)
async def process_datetime(message: Message, state: FSMContext):
    parsed = parse_lesson_datetime(message.text)
    if not parsed:
        await message.answer(
            "⚠️ Не удалось распознать дату.\n"
            "Пожалуйста, используйте формат <code>ДД.ММ ЧЧ:ММ</code> (например: <code>15.09 14:00</code>) "
            "или <code>сегодня 15:00</code>:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        return

    display_str, date_iso = parsed
    today_iso = date.today().isoformat()
    if date_iso < today_iso:
        await message.answer(
            f"⚠️ Указанная дата ({display_str}) уже прошла! "
            f"Пожалуйста, укажите сегодняшнюю или будущую дату:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(datetime_str=display_str, lesson_date=date_iso)
    await state.set_state(LessonForm.description)
    await message.answer(
        "📍 <b>Шаг 3 из 4: Дополнительная информация</b>\n\n"
        "Укажите аудиторию, преподавателя или ссылку на материалы (например: <i>ауд. 312, преп. Смирнов А.В.</i>).\n"
        "Если дополнительной информации нет, нажмите <b>«⏭️ Пропустить»</b>:",
        parse_mode="HTML",
        reply_markup=get_skip_keyboard(),
    )


@router.message(LessonForm.description, F.text)
async def process_description(message: Message, state: FSMContext):
    desc_text = message.text.strip()
    if desc_text in ["⏭️ Пропустить", "пропустить", "/skip"]:
        description = None
    else:
        description = desc_text

    await state.update_data(description=description)
    await state.set_state(LessonForm.max_slots)
    await message.answer(
        "🔢 <b>Шаг 4 из 4: Количество мест в очереди</b>\n\n"
        "Укажите максимальное количество слотов для сдачи (например: <code>20</code>).\n"
        "Либо нажмите <b>«⏭️ Пропустить»</b>, чтобы установить значение по умолчанию (30 мест):",
        parse_mode="HTML",
        reply_markup=get_skip_keyboard(),
    )


@router.message(LessonForm.max_slots, F.text)
async def process_max_slots(message: Message, state: FSMContext, repo: Repository):
    raw_text = message.text.strip()
    if raw_text in ["⏭️ Пропустить", "пропустить", "/skip"]:
        max_slots = 30
    else:
        if not raw_text.isdigit():
            await message.answer("⚠️ Пожалуйста, введите целое положительное число (например: 25) или нажмите «⏭️ Пропустить»:")
            return
        max_slots = int(raw_text)
        if max_slots < 1 or max_slots > 200:
            await message.answer("⚠️ Количество мест должно быть в диапазоне от 1 до 200. Попробуйте ещё раз:")
            return

    data = await state.get_data()
    subject = data["subject"]
    datetime_str = data["datetime_str"]
    lesson_date = data["lesson_date"]
    description = data.get("description")
    user_id = message.from_user.id

    # Register user in DB if not already registered
    user = await repo.get_user(user_id)
    if not user:
        name = message.from_user.full_name or "Пользователь"
        await repo.upsert_user(user_id, message.from_user.username, name)

    lesson = await repo.create_lesson(
        subject=subject,
        datetime_str=datetime_str,
        lesson_date=lesson_date,
        description=description,
        max_slots=max_slots,
        created_by=user_id,
    )

    await state.clear()
    is_admin = settings.is_admin(user_id)

    desc_info = f"\n📍 <b>Инфо:</b> {description}" if description else ""
    summary_text = (
        "✅ <b>Пара успешно добавлена!</b>\n\n"
        f"📚 <b>Предмет:</b> {subject}\n"
        f"📅 <b>Дата и время:</b> {datetime_str}{desc_info}\n"
        f"👥 <b>Мест в очереди:</b> {max_slots}\n\n"
        "<i>Студенты теперь могут записываться на эту пару. "
        "Пара будет автоматически удалена в конце дня проведения.</i>"
    )

    action_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👀 Открыть очередь пары", callback_data=f"lesson_view:{lesson.id}")],
            [InlineKeyboardButton(text="📋 Ко всем парам", callback_data="lessons_list")],
        ]
    )

    await message.answer(
        summary_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(is_admin),
    )
    await message.answer("Действия с созданной парой:", reply_markup=action_kb)


# ================= LESSON DELETION =================

@router.callback_query(F.data.startswith("lesson_del_ask:"))
async def ask_delete_lesson(callback: CallbackQuery, repo: Repository):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара не найдена!", show_alert=True)
        return

    user_id = callback.from_user.id
    if not (settings.is_admin(user_id) or lesson.created_by == user_id):
        await callback.answer("⛔ У вас нет прав на удаление этой пары.", show_alert=True)
        return

    text = (
        f"⚠️ <b>Вы действительно хотите удалить пару «{lesson.subject}» ({lesson.datetime_str})?</b>\n\n"
        "Вся текущая очередь на эту пару также будет удалена!"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_delete_confirm_keyboard(lesson_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lesson_del_confirm:"))
async def confirm_delete_lesson(callback: CallbackQuery, repo: Repository):
    lesson_id = int(callback.data.split(":")[1])
    lesson = await repo.get_lesson_by_id(lesson_id)
    if not lesson:
        await callback.answer("Пара уже удалена.", show_alert=True)
        await callback.message.edit_text("Пара не найдена.")
        return

    user_id = callback.from_user.id
    if not (settings.is_admin(user_id) or lesson.created_by == user_id):
        await callback.answer("⛔ Нет прав для удаления.", show_alert=True)
        return

    await repo.delete_lesson(lesson_id)
    await callback.answer("✅ Пара удалена", show_alert=True)

    text, keyboard = await render_lessons_list(user_id, repo)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
