from aiogram import Bot, Dispatcher
from src.handlers import common_router, profile_router, lessons_router, queue_router


def test_bot_and_dispatcher_setup():
    bot = Bot(token="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
    dp = Dispatcher()

    dp.include_router(common_router)
    dp.include_router(profile_router)
    dp.include_router(lessons_router)
    dp.include_router(queue_router)

    assert common_router in dp.sub_routers
    assert profile_router in dp.sub_routers
    assert lessons_router in dp.sub_routers
    assert queue_router in dp.sub_routers
