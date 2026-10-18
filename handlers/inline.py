# Inline-режим: в любом чате набираешь "@бот запрос" и выбираешь пост из списка

from html import escape

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from database import get_posts
from search import get_snippet, get_title, search

router = Router()


@router.inline_query()
async def inline_search(query: InlineQuery):
    text = query.query.strip()
    if text == "":
        await query.answer([], cache_time=5)
        return

    items = []
    for i, (score, link, post_text, date) in enumerate(search(text, get_posts(), limit=10)):
        title = get_title(post_text)
        # под заголовком - дата и кусочек поста, где нашлось слово
        description = date
        snippet = get_snippet(text, post_text)
        if snippet:
            description += " · " + snippet
        items.append(InlineQueryResultArticle(
            id=str(i),
            title=title,
            description=description,
            url=link,
            # что отправится в чат, когда человек выберет пост
            input_message_content=InputTextMessageContent(message_text=f'<a href="{link}">{escape(title)}</a>'),
        ))
    await query.answer(items, cache_time=10)
