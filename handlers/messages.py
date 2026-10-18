# Обычные сообщения. Бот отвечает только если его позвали, и всегда реплаем.

import asyncio
import re
import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

import ai
from database import get_posts
from handlers.buttons import keyboard, remember, search_page
from handlers.updates import is_update_request, update_post
from search import did_you_mean, get_title

router = Router()

HELP_TEXT = (
    "Я ищу посты канала и даю ссылки на них.\n\n"
    "В беседе или комментариях напиши: @{bot} как записаться на курс\n"
    "Или ответь на моё сообщение - тоже поищу.\n"
    "В личке просто напиши, что ищешь.\n\n"
    "<b>Как ещё можно искать:</b>\n"
    '"точная фраза" - в кавычках, ищу ровно так\n'
    "олимпиада -школьная - минус убирает посты со словом\n"
    "#анонс - только посты с хештегом\n"
    "расписание октябрь / 2025 - посты за месяц или год\n"
    "последние олимпиады - сначала свежие\n"
    "Забыл раскладку (hfcgbcfybt) или пишешь транслитом (raspisanie) - тоже пойму\n"
    "Под ответом есть кнопки: «Показать ещё», «Похожие» и «Помогло»\n\n"
    "<b>Умный поиск с ИИ:</b> @{bot} ии хочу летом покодить\n"
    "ИИ понимает запрос своими словами и подбирает посты. "
    "Ответь на его сообщение, чтобы уточнить: «а для 7 класса?»\n\n"
    "<b>Команды:</b>\n"
    "/search запрос - обычный поиск (то же, что @{bot} запрос)\n"
    "/ai запрос - умный поиск с ИИ\n"
    "/last - последние посты\n"
    "/random - случайный пост\n"
    "/tags - популярные хештеги\n\n"
    "Если пост изменили - ответь на него /update или пришли ссылку: /update https://t.me/канал/123\n"
    "В любом чате можно набрать @{bot} запрос - и выбрать пост из списка"
)

# когда каждый человек последний раз спрашивал бота (защита от спама)
last_request = {}
# кто сейчас ждёт ответа, потому что спросил слишком быстро
waiting = set()

# немного статистики для /stats, хранится только пока бот запущен
stats = {"searches": 0, "found": 0, "ai": 0, "start": time.time()}

AI_WORDS = ("ии", "ai", "спроси")


def who(message: Message):
    # id того, кто спрашивает. Анонимный админ группы или человек, который пишет от имени
    # канала, приходит от служебного бота - для них берём id группы или канала (он отрицательный)
    if message.sender_chat is not None:
        return message.sender_chat.id
    return message.from_user.id


@router.message(CommandStart())
@router.message(Command("help"))
async def help_command(message: Message, bot: Bot):
    me = await bot.me()
    await message.reply(HELP_TEXT.format(bot=me.username))



async def smart_answer(message: Message, queries):
    # queries - запросы разговора, последний - новый
    if queries[-1] == "":
        await message.reply("Напиши запрос после «ии», например: ии хочу летом покодить")
        return
    if not ai.is_enabled():
        # ИИ не настроен - не отказываем, а ищем обычным поиском
        text, markup, links = search_page(queries[-1], 0)
        if links:
            sent = await message.reply("Умный поиск сейчас выключен, вот обычный. " + text, reply_markup=markup)
            remember(sent, who(message), query=queries[-1], links=links)
        else:
            await message.reply("Умный поиск сейчас выключен, а обычный ничего не нашёл 😔 Попробуй написать по-другому")
        return
    if len(queries) > ai.MAX_QUERIES:
        await message.reply("Уточнений уже много, давай начнём заново: напиши новый запрос с «ии»")
        return
    error = ai.check_limits(who(message))
    if error:
        await message.reply(error)
        return

    wait = await message.reply("🤖 Ищу...")
    stats["ai"] += 1
    result = await ai.smart_search(queries, get_posts(), who(message))

    if result is None:
        # ИИ не смог - показываем обычный поиск по последнему запросу
        text, markup, links = search_page(queries[-1], 0)
        if links:
            await wait.edit_text("Умный поиск не сработал. " + text, reply_markup=markup)
            remember(wait, who(message), query=queries[-1], links=links)
        else:
            await wait.edit_text("Умный поиск не сработал, а обычный ничего не нашёл 😔 Попробуй написать по-другому")
        return

    links = []
    if result["posts"]:
        answer = "🤖 Вот что подходит:\n"
        for i, (link, post_text, date, reason) in enumerate(result["posts"], start=1):
            links.append(link)
            answer += f'\n{i}. <a href="{link}">{escape(get_title(post_text))}</a> ({date})'
            if reason:
                answer += f"\n    <i>{escape(reason[:100])}</i>"
    else:
        answer = "🤖 Ничего подходящего не нашёл 😔"
    if result["clarify"]:
        answer += f"\n\n❓ {escape(result['clarify'][:150])}"
    answer += "\n\n↩️ Ответь на это сообщение, чтобы уточнить запрос"

    if links:
        await wait.edit_text(answer, reply_markup=keyboard())
        remember(wait, who(message), links=links, ai_text=answer)
    else:
        await wait.edit_text(answer)
    # запоминаем разговор: если тот же человек ответит на это сообщение - продолжим
    ai.save_dialog(message.chat.id, wait.message_id, who(message), queries)


@router.message(Command("ai"))
async def ai_command(message: Message, command: CommandObject):
    await smart_answer(message, [(command.args or "").strip()])


@router.message(Command("search"))
async def search_command(message: Message, command: CommandObject, bot: Bot):
    # /search запрос - то же, что "@бот запрос". Команды доходят до бота всегда,
    # даже если в группе он не админ и у него включён privacy mode
    query = (command.args or "").strip()
    if query == "" and message.reply_to_message is not None:
        query = message.reply_to_message.text or message.reply_to_message.caption or ""
    me = await bot.me()
    if query == "":
        await message.reply("Напиши, что найти: /search расписание")
        return
    await do_search(message, query, me.username)


# обычный текст - последним: этот обработчик ловит любой текст, поэтому команды должны быть выше
@router.message(F.text)
async def on_text(message: Message, bot: Bot):
    if message.from_user is None:
        return
    # сообщения других ботов не слушаем. Но анонимный админ группы и человек, который пишет
    # от имени канала, для телеграма тоже "бот" (служебный) - у них заполнен sender_chat
    if message.from_user.is_bot and message.sender_chat is None:
        return
    text = message.text
    if text.startswith("/"):
        return

    me = await bot.me()
    reply_to = message.reply_to_message

    if message.chat.type == "private":
        called = True
    else:
        mentioned = "@" + me.username.lower() in text.lower()
        answer_to_bot = reply_to is not None and reply_to.from_user is not None and reply_to.from_user.id == me.id
        called = mentioned or answer_to_bot
    if not called:
        return  # бота не звали - молчим

    query = re.sub("@" + me.username, "", text, flags=re.IGNORECASE).strip()

    # "обнови" / "update" - ответом на пост или со ссылкой на пост
    if is_update_request(query):
        parts = query.split(maxsplit=1)
        rest = parts[1] if len(parts) > 1 else ""  # то, что после слова "обнови" - например ссылка
        await update_post(message, bot, rest)
        return

    # ответ на сообщение умного поиска от того же человека - уточнение запроса
    if reply_to is not None and reply_to.from_user is not None and reply_to.from_user.id == me.id:
        previous = ai.get_dialog(message.chat.id, reply_to.message_id, who(message))
        if previous is not None and query != "":
            words = query.split()
            if words[0].lower().strip(",.:!") in AI_WORDS:
                query = " ".join(words[1:])  # "ии" в уточнении писать не обязательно, но можно
            await smart_answer(message, previous + [query])
            return

    # "@бот" ответом на чужой вопрос - ищем по тексту вопроса (но не по ответу самого бота)
    reply_is_bot = reply_to is not None and reply_to.from_user is not None and reply_to.from_user.id == me.id
    if query == "" and reply_to is not None and not reply_is_bot:
        query = reply_to.text or reply_to.caption or ""
    if query == "":
        await message.reply(f"Напиши, что найти. Например: @{me.username} расписание")
        return

    # "ии запрос" - умный поиск
    words = query.split()
    if words[0].lower().strip(",.:!") in AI_WORDS:
        ai_query = " ".join(words[1:]).strip(" ,.:!")
        # "@бот ии" ответом на чужой вопрос - ищем по тому вопросу
        if ai_query == "" and reply_to is not None and (reply_to.from_user is None or reply_to.from_user.id != me.id):
            ai_query = reply_to.text or reply_to.caption or ""
        await smart_answer(message, [ai_query])
        return

    await do_search(message, query, me.username)


async def do_search(message: Message, query, bot_username):
    # обычный поиск с ответом реплаем
    # один человек получает ответ не чаще раза в 3 секунды. Если спросил быстрее -
    # не молчим, а отвечаем чуть позже. Но ждать может только один запрос, остальные - спам
    user_id = who(message)
    wait = 3 - (time.time() - last_request.get(user_id, 0))
    if wait > 0:
        if user_id in waiting:
            return
        waiting.add(user_id)
        await asyncio.sleep(wait)
        waiting.discard(user_id)
    last_request[user_id] = time.time()

    stats["searches"] += 1
    text, markup, links = search_page(query, 0)
    if not links:
        maybe = did_you_mean(query, get_posts())
        if maybe:
            # похоже на опечатку - сразу ищем исправленный запрос
            text, markup, links = search_page(maybe, 0)
            if links:
                stats["found"] += 1
                text = f"По запросу «{escape(query)}» ничего нет, ищу «{escape(maybe)}».\n" + text
                sent = await message.reply(text, reply_markup=markup)
                remember(sent, user_id, query=maybe, links=links)
                return
        answer = "Ничего не нашёл 😔 Попробуй написать по-другому или короче."
        if ai.is_enabled():
            answer += f"\n\nИли попробуй умный поиск: @{bot_username} ии {escape(query)}"
        await message.reply(answer)
        return

    stats["found"] += 1
    sent = await message.reply(text, reply_markup=markup)
    remember(sent, user_id, query=query, links=links)
