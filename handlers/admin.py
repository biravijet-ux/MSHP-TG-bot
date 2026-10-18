# Команды для админов: /del, /update_all и /stats

import asyncio
import time

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import ADMIN_IDS, CHANNEL_ID, CHANNEL_USERNAME
import ai
from database import delete_post, get_counter, get_posts, make_link
from handlers.messages import stats
from handlers.updates import channel_ref, fetch_post, parse_link
from search import post_number

router = Router()


@router.message(Command("del"))
async def del_post(message: Message, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not command.args:
        await message.reply("Напиши ссылку на пост: /del https://t.me/канал/123")
        return
    post_id = parse_link(command.args)
    if post_id is None:
        await message.reply("Это ссылка не на пост нашего канала")
        return
    if delete_post(make_link(CHANNEL_USERNAME, CHANNEL_ID, post_id)):
        await message.reply("Удалил пост из базы")
    else:
        await message.reply("Такого поста нет в базе")


@router.message(Command("stats"))
async def stats_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    hours = int((time.time() - stats["start"]) // 3600)
    answer = (
        f"Постов в базе: {len(get_posts())}\n"
        f"Поисков с запуска: {stats['searches']} (нашлось: {stats['found']})\n"
        f"Умных поисков с запуска: {stats['ai']}\n"
        f"Умных поисков сегодня: {ai.used_today()} из {ai.AI_DAILY_LIMIT}\n"
        f"Нажали «Помогло» (за всё время): {get_counter('helped')}\n"
        f"Бот работает: {hours} ч.\n"
        f"{ai.status()}"
    )
    await message.reply(answer)


# идёт ли сейчас /update_all - чтобы не запустить два раза одновременно
updating = {"now": False}


# Бот не умеет читать пост канала по номеру, поэтому пересылаем каждый пост себе в личку,
# берём текст и сразу удаляем пересланное сообщение (см. fetch_post в updates.py)
@router.message(Command("update_all"))
async def update_all(message: Message, command: CommandObject, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.chat.type != "private":
        await message.reply("Эту команду пиши мне в личку")
        return
    if updating["now"]:
        await message.reply("Уже обновляю базу, подожди, пока закончу")
        return
    if channel_ref() is None:
        await message.reply("В .env не указан канал (CHANNEL_USERNAME или CHANNEL_ID)")
        return

    args = (command.args or "").strip()
    if args.isdigit():
        last_id = int(args)
    elif args:
        # прислали ссылку на последний пост канала
        last_id = parse_link(args)
        if last_id is None:
            await message.reply("Это ссылка не на пост нашего канала")
            return
    else:
        # ничего не написали - берём самый новый пост, который бот уже видел в канале
        last_id = 0
        for link, text, date in get_posts():
            last_id = max(last_id, post_number(link))
        if last_id == 0:
            await message.reply(
                "Пришли ссылку на последний пост канала: /update_all https://t.me/канал/850\n"
                "(в Telegram: нажми на пост - «Копировать ссылку»)"
            )
            return

    progress = await message.reply(
        f"Обновляю базу: посты с 1 по {last_id}, это займёт примерно {last_id // 60 + 1} мин."
    )

    updating["now"] = True
    new = changed = deleted = 0
    try:
        for post_id in range(1, last_id + 1):
            # раз в 50 постов показываем, сколько уже сделано (правим то же сообщение, а не пишем новое)
            if post_id % 50 == 0:
                try:
                    await progress.edit_text(f"Обновляю базу: {post_id} из {last_id}...")
                except TelegramBadRequest:
                    pass
            status = await fetch_post(bot, message.chat.id, post_id)
            if status == "new":
                new += 1
            elif status == "changed":
                changed += 1
            elif status == "deleted":
                deleted += 1
            await asyncio.sleep(1)  # чтобы телеграм не ругался, что мы слишком часто пишем
    finally:
        updating["now"] = False

    await message.reply(f"Готово! Новых постов: {new}, изменено: {changed}, удалено: {deleted}")
