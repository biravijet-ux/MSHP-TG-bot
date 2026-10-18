# Кнопки под ответом: «Показать ещё», «Похожие», «Назад» и «Помогло».
# Кнопки не присылают новых сообщений, а меняют тот же ответ - чтобы не засорять беседу.
# Листать и смотреть похожие может только тот, кто спрашивал. «Помогло» может нажать любой.

import time
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import add_counter, get_posts
from search import get_snippet, get_title, search, similar_posts

router = Router()

PAGE_SIZE = 5          # сколько постов на одной странице
MAX_RESULTS = 20       # дальше листать нет смысла - лучше уточнить запрос
ANSWER_MINUTES = 60    # через сколько минут кнопки у ответа перестают работать

# Что показано в каждом ответе бота. Ключ - (id чата, id сообщения бота).
# Хранится только в памяти, после перезапуска бота кнопки старых ответов не работают.
answers = {}


def format_results(query, results, start=1):
    # список постов: номер, ссылка, дата, а ниже кусочек поста, где нашлось слово
    text = ""
    for i, result in enumerate(results, start=start):
        link, post_text, date = result[1], result[2], result[3]
        text += f'\n{i}. <a href="{link}">{escape(get_title(post_text))}</a> ({date})'
        if query:
            snippet = get_snippet(query, post_text)
            if snippet:
                text += f"\n    <i>{escape(snippet)}</i>"
    return text


def keyboard(page=0, has_more=False, similar_view=False, can_similar=True):
    nav = []
    if similar_view:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    else:
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
        if has_more:
            nav.append(InlineKeyboardButton(text="Показать ещё ➡️", callback_data="more"))
    row = [InlineKeyboardButton(text="👍 Помогло", callback_data="helped")]
    if can_similar and not similar_view:
        row.append(InlineKeyboardButton(text="🔍 Похожие", callback_data="similar"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_page(query, page):
    # одна страница обычного поиска: (текст, кнопки, ссылки на странице)
    # ищем на один пост больше, чем нужно, чтобы понять, есть ли следующая страница
    results = search(query, get_posts(), limit=(page + 1) * PAGE_SIZE + 1)
    shown = results[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    has_more = len(results) > (page + 1) * PAGE_SIZE and (page + 1) * PAGE_SIZE < MAX_RESULTS
    if page == 0:
        text = "Вот что нашёл:\n"
    else:
        text = f"Ещё результаты (страница {page + 1}):\n"
    text += format_results(query, shown, start=page * PAGE_SIZE + 1)
    links = [r[1] for r in shown]
    return text, keyboard(page, has_more), links


def remember(message, user_id, query=None, links=None, ai_text=None):
    # запоминаем ответ бота, чтобы кнопки знали, что в нём показано.
    # query - для обычного поиска, ai_text - текст ответа умного поиска (для кнопки «Назад»)
    now = time.time()
    for key in list(answers):
        if now - answers[key]["time"] > ANSWER_MINUTES * 60:
            del answers[key]
    answers[(message.chat.id, message.message_id)] = {
        "user": user_id,
        "query": query,
        "page": 0,
        "links": links or [],
        "ai_text": ai_text,
        "helped": set(),
        "time": now,
    }


def main_view(state):
    # ответ без «похожих»: страница обычного поиска или ответ умного поиска
    if state["query"] is None:
        return state["ai_text"], keyboard(can_similar=bool(state["links"])), state["links"]
    return search_page(state["query"], state["page"])


async def edit(callback: CallbackQuery, text, markup):
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # например, текст не поменялся - телеграм ругается, но это не страшно


def get_state(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        return None  # сообщение слишком старое, телеграм его уже не даёт
    return answers.get((callback.message.chat.id, callback.message.message_id))


@router.callback_query(F.data == "helped")
async def helped(callback: CallbackQuery):
    state = get_state(callback)
    if state is not None:
        if callback.from_user.id in state["helped"]:
            await callback.answer("Ты уже отметил, спасибо!")
            return
        state["helped"].add(callback.from_user.id)
    add_counter("helped")
    await callback.answer("Спасибо! Рад, что помог 👍")


@router.callback_query(F.data.in_({"more", "back", "similar"}))
async def navigate(callback: CallbackQuery):
    state = get_state(callback)
    if state is None:
        await callback.answer("Этот ответ устарел, напиши запрос ещё раз", show_alert=True)
        return
    # если спрашивал анонимный админ (id группы - отрицательный), мы не знаем, кто это был,
    # поэтому листать может любой
    if state["user"] > 0 and callback.from_user.id != state["user"]:
        await callback.answer("Это чужой поиск - спроси меня сам 🙂")
        return
    state["time"] = time.time()  # пока человек листает, ответ не устаревает

    if callback.data == "similar":
        if not state["links"]:
            await callback.answer("Тут не на что искать похожие")
            return
        base = state["links"][0]
        posts = get_posts()
        results = similar_posts(base, posts)
        if not results:
            await callback.answer("Похожих постов не нашёл")
            return
        title = ""
        for link, text, date in posts:
            if link == base:
                title = get_title(text)
        state["similar"] = True
        text = f"Похожие на «{escape(title)}»:\n" + format_results(None, results)
        await edit(callback, text, keyboard(similar_view=True))
        await callback.answer()
        return

    if callback.data == "back" and state.get("similar"):
        state["similar"] = False  # из «похожих» возвращаемся на ту же страницу
    elif callback.data == "back":
        state["page"] = max(0, state["page"] - 1)
    elif state["query"] is not None:  # "more"
        state["page"] += 1

    text, markup, links = main_view(state)
    state["links"] = links
    await edit(callback, text, markup)
    await callback.answer()
