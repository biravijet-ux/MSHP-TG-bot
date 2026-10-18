# Разные команды: /last, /random, /tags

import random
import re
from collections import Counter
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from database import get_posts
from search import get_title, post_number

router = Router()


def newest_posts():
    # номер поста растёт со временем, поэтому сортируем по нему
    return sorted(get_posts(), key=lambda p: post_number(p[0]), reverse=True)


@router.message(Command("last"))
async def last_posts(message: Message, command: CommandObject):
    count = 5
    if command.args and command.args.strip().isdigit():
        count = int(command.args.strip())
    count = max(1, min(count, 15))  # больше 15 - уже простыня

    posts = newest_posts()[:count]
    if not posts:
        await message.reply("В базе пока нет постов")
        return
    answer = "Последние посты:\n"
    for i, (link, text, date) in enumerate(posts, start=1):
        answer += f'\n{i}. <a href="{link}">{escape(get_title(text))}</a> ({date})'
    await message.reply(answer)


@router.message(Command("random"))
async def random_post(message: Message):
    posts = get_posts()
    if not posts:
        await message.reply("В базе пока нет постов")
        return
    link, text, date = random.choice(posts)
    await message.reply(f'🎲 Случайный пост:\n<a href="{link}">{escape(get_title(text))}</a> ({date})')


@router.message(Command("tags"))
async def tags(message: Message):
    counter = Counter()
    for link, text, date in get_posts():
        # set - чтобы один тег два раза в одном посте не считался дважды
        for tag in set(re.findall(r"#\w+", text.lower())):
            counter[tag] += 1
    if not counter:
        await message.reply("В постах нет хештегов")
        return
    answer = "Популярные хештеги (можно искать прямо по ним):\n"
    for tag, count in counter.most_common(15):
        answer += f"\n{escape(tag)} - {count}"
    await message.reply(answer)
