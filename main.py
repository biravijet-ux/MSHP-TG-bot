import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

import ai
from config import ADMIN_IDS, BOT_TOKEN, DB_PATH, VERSION
from database import get_posts, init_db
from handlers import admin, buttons, channel, commands, inline, messages, updates

# Команды, которые Telegram показывает в меню (кнопка «/» рядом с полем ввода)
COMMANDS_FOR_ALL = [
    BotCommand(command="search", description="Найти пост: /search расписание"),
    BotCommand(command="help", description="Как искать посты"),
    BotCommand(command="ai", description="Умный поиск с ИИ: /ai хочу летом покодить"),
    BotCommand(command="last", description="Последние посты канала"),
    BotCommand(command="random", description="Случайный пост"),
    BotCommand(command="tags", description="Популярные хештеги"),
    BotCommand(command="update", description="Обновить пост: по ссылке или ответом на пост"),
]
COMMANDS_FOR_ADMINS = [
    BotCommand(command="update_all", description="Обновить всю базу: /update_all ссылка на последний пост"),
    BotCommand(command="del", description="Убрать пост из базы: /del ссылка"),
    BotCommand(command="stats", description="Статистика бота"),
]


async def set_commands(bot):
    start = [BotCommand(command="start", description="Что умеет бот")]
    await bot.set_my_commands(start + COMMANDS_FOR_ALL, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(COMMANDS_FOR_ALL, scope=BotCommandScopeAllGroupChats())
    # админам в личке показываем ещё и админские команды
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                start + COMMANDS_FOR_ALL + COMMANDS_FOR_ADMINS,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except TelegramBadRequest:
            print(f"Админ {admin_id} ещё не писал боту - админские команды в меню ему не видны")


async def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        print("Нет BOT_TOKEN. Скопируй .env.example в .env и впиши туда токен")
        return

    init_db(DB_PATH)
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True))
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(updates.router)
    dp.include_router(buttons.router)
    dp.include_router(channel.router)
    dp.include_router(commands.router)
    dp.include_router(inline.router)
    dp.include_router(messages.router)  # обычные сообщения - последними, иначе перехватят команды

    await set_commands(bot)

    print(ai.status())
    count = len(get_posts())
    if count == 0:
        # старые посты бот сам не видит - их надо загрузить командой
        print("База постов пустая. Напиши боту в личку: /update_all ссылка на последний пост канала")
    else:
        print(f"Постов в базе: {count}")
    print(f"Бот запущен, версия {VERSION}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
