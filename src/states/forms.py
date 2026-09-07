from aiogram.fsm.state import State, StatesGroup


class ProfileForm(StatesGroup):
    waiting_for_name = State()


class LessonForm(StatesGroup):
    subject = State()
    datetime_str = State()
    description = State()
    max_slots = State()


class QueueSlotForm(StatesGroup):
    waiting_for_slot = State()
