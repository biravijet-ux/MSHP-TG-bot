# Обновление одного поста в базе: по ссылке на пост или ответом на пост.
#   /update https://t.me/канал/123        @бот обнови https://t.me/канал/123
#   ответить на пост: /update             ответить на пост: @бот обнови
# Обновлять может любой: текст всё равно берётся из самого канала, а не от человека.

import asyncio
import re

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, MessageOriginChannel

from config import ADMIN_IDS, CHANNEL_ID, CHANNEL_USERNAME
from database import delete_post, make_link, save_post
from handlers.channel import is_our_channel

router = Router()

# слова, которыми можно попросить обновить пост: "@бот обнови", "@бот update ссылка"
UPDATE_WORDS = ("обнови", "обновить", "update")

STATUS_TEXT = {
    "new": "Добавил пост в базу",
    "changed": "Обновил пост в базе",
    "same": "В базе уже последняя версия поста",
    "deleted": "Этого поста больше нет в канале - убрал его из базы",
    "missing": "Такого поста нет в канале",
    "empty": "В этом посте нет текста, мне нечего сохранять",
    "error": "Этот пост я сохранить не могу",
    "no_chat": "Не получилось прочитать пост. Напиши мне это же в личку",
}


def channel_ref():
    # как обращаться к каналу в Telegram API: по id или по @username
    if CHANNEL_ID:
        return int(CHANNEL_ID)
    if CHANNEL_USERNAME:
        return "@" + CHANNEL_USERNAME
    return None


def parse_link(text):
    # номер поста из ссылки на НАШ канал или None.
    # понимает https://t.me/mshp/123, t.me/c/1234567890/123 и ссылки с ?comment=... в конце
    m = re.search(r"t\.me/(c/\d+|[A-Za-z0-9_]+)/(\d+)", text)
    if m is None:
        return None
    where = m.group(1).lower()
    if where.startswith("c/"):
        # приватная ссылка - сверяем id канала
        if not CHANNEL_ID or where[2:] != CHANNEL_ID.replace("-100", "", 1):
            return None
    elif where != CHANNEL_USERNAME.lower():
        return None
    return int(m.group(2))


def is_update_request(text):
    # текст после упоминания бота - это просьба обновить пост?
    # "обнови" или "обнови ссылка" - да. "обновить расписание" - нет, это обычный поиск
    words = text.lower().split()
    if len(words) == 0 or words[0].strip(".,!") not in UPDATE_WORDS:
        return False
    return len(words) == 1 or "t.me/" in text


async def forward(bot, chat_id, channel, post_id):
    # если телеграм просит подождать - ждём и пробуем ещё раз
    while True:
        try:
            return await bot.forward_message(chat_id, channel, post_id, disable_notification=True)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)


async def fetch_post(bot, chat_id, post_id):
    # Бот не умеет читать пост канала по номеру, поэтому пересылает его в чат chat_id,
    # берёт текст и сразу удаляет пересланное. Возвращает ключ из STATUS_TEXT
    link = make_link(CHANNEL_USERNAME, CHANNEL_ID, post_id)
    try:
        copy = await forward(bot, chat_id, channel_ref(), post_id)
    except TelegramForbiddenError:
        return "no_chat"  # человек ещё не писал боту в личку - туда пересылать нельзя
    except TelegramBadRequest as e:
        # "chat not found" проверяем первым - в нём тоже есть слова "not found"
        if "chat not found" in str(e):
            return "no_chat"
        if "not found" in str(e):
            # такого поста нет: удалили из канала или номер неправильный
            if delete_post(link):
                return "deleted"
            return "missing"
        return "error"  # например, служебное сообщение "канал создан" переслать нельзя
    await bot.delete_message(chat_id, copy.message_id)

    text = copy.text or copy.caption
    if not text:
        return "empty"
    return save_post(link, text, copy.forward_origin.date.strftime("%d.%m.%Y"))


def update_from_reply(post: Message):
    # пост, на который ответили (в комментариях или пересланный в личку). Возвращает ключ из STATUS_TEXT
    if post is None or not isinstance(post.forward_origin, MessageOriginChannel):
        return None
    origin = post.forward_origin
    text = post.text or post.caption
    if not is_our_channel(origin.chat):
        return "error"
    if not text:
        return "empty"
    link = make_link(origin.chat.username, origin.chat.id, origin.message_id)
    return save_post(link, text, origin.date.strftime("%d.%m.%Y"))


async def update_post(message: Message, bot: Bot, text):
    # общая часть для /update и "@бот обнови": text - то, что написали после команды
    post_id = parse_link(text)
    if post_id is None and "t.me/" in text:
        await message.reply("Это ссылка не на пост нашего канала")
        return

    if post_id is not None:
        if channel_ref() is None:
            await message.reply("В .env не указан канал (CHANNEL_USERNAME или CHANNEL_ID)")
            return
        # в личке пересылаем пост туда же, а из группы - в личку первому админу,
        # чтобы не мелькать пересланными сообщениями в беседе
        if message.chat.type == "private":
            chat_id = message.chat.id
        elif ADMIN_IDS:
            chat_id = ADMIN_IDS[0]
        else:
            await message.reply("По ссылке могу обновить пост только в личке - напиши мне туда")
            return
        status = await fetch_post(bot, chat_id, post_id)
        await message.reply(STATUS_TEXT[status])
        return

    status = update_from_reply(message.reply_to_message)
    if status is None:
        await message.reply(
            "Пришли ссылку на пост: /update https://t.me/канал/123\n"
            "или ответь на сам пост словом /update"
        )
        return
    await message.reply(STATUS_TEXT[status])


@router.message(Command("update"))
async def update_command(message: Message, command: CommandObject, bot: Bot):
    await update_post(message, bot, (command.args or "").strip())
