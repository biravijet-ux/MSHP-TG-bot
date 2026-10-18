# Новые посты канала сами сохраняются в базу. Бот тут ничего не пишет.

from aiogram import F, Router
from aiogram.types import Message, MessageOriginChannel

from config import CHANNEL_ID, CHANNEL_USERNAME
from database import make_link, save_post

router = Router()


def is_our_channel(chat):
    if CHANNEL_ID:
        return str(chat.id) == CHANNEL_ID
    if CHANNEL_USERNAME:
        return (chat.username or "").lower() == CHANNEL_USERNAME.lower()
    return True


# бот - админ канала: новый или изменённый пост
@router.channel_post()
@router.edited_channel_post()
async def new_channel_post(message: Message):
    text = message.text or message.caption
    if not text or not is_our_channel(message.chat):
        return
    link = make_link(message.chat.username, message.chat.id, message.message_id)
    save_post(link, text, message.date.strftime("%d.%m.%Y"))


# канал сам пересылает каждый пост в группу с комментариями
@router.message(F.is_automatic_forward)
@router.edited_message(F.is_automatic_forward)
async def post_in_comments(message: Message):
    origin = message.forward_origin
    text = message.text or message.caption
    if not text or not isinstance(origin, MessageOriginChannel) or not is_our_channel(origin.chat):
        return
    link = make_link(origin.chat.username, origin.chat.id, origin.message_id)
    save_post(link, text, origin.date.strftime("%d.%m.%Y"))
