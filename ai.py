# Умный поиск через ИИ.
# ИИ не отвечает на вопрос сам - по правилам бот должен вести к оригинальному посту.
# Мы отдаём ИИ каталог постов канала (номер, дата, начало текста), а он выбирает подходящие
# и к каждому пишет одну строчку, чем пост поможет. Ссылки бот собирает сам из номеров,
# поэтому ИИ не может придумать ссылку, которой нет.
#
# Сервис выбирается в .env (AI_PROVIDER):
#   anthropic - Claude через библиотеку anthropic
#   openai    - любой сервис, который работает с библиотекой openai (OpenAI, OpenRouter, Ollama...)
# Если ключа нет - ИИ просто выключен, остальной бот работает.

import json
import logging
import time

import anthropic
import openai

from config import AI_API_KEY, AI_BASE_URL, AI_DAILY_LIMIT, AI_MODEL, AI_PROVIDER
from database import add_ai_count, get_ai_count
from search import post_number

provider = AI_PROVIDER
client = None
if AI_API_KEY and provider == "anthropic":
    client = anthropic.AsyncAnthropic(api_key=AI_API_KEY)
elif AI_API_KEY and provider == "openai" and AI_MODEL:
    # base_url=None - значит сам OpenAI
    client = openai.AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)


def status():
    # строчка для запуска бота и /stats: включен ли ИИ, а если нет - почему
    if client is not None:
        where = AI_BASE_URL if provider == "openai" and AI_BASE_URL else provider
        return f"ИИ включен: {AI_MODEL} ({where})"
    if not AI_API_KEY:
        return "ИИ выключен: нет AI_API_KEY в .env"
    if provider not in ("anthropic", "openai"):
        return f"ИИ выключен: неизвестный AI_PROVIDER={provider}, нужно anthropic или openai"
    return "ИИ выключен: для AI_PROVIDER=openai нужно указать AI_MODEL"

# сколько символов от начала каждого поста видит ИИ. Обычно там заголовок и главное
CATALOG_CHARS = 300

SYSTEM = (
    "Ты - поиск по архиву постов Telegram-канала школы программирования МШП. "
    "Тебе дают список постов (номер в квадратных скобках, дата, начало текста) и запрос человека.\n"
    "Выбери посты, которые подходят под запрос, самые подходящие первыми, не больше 5. "
    "Понимай разговорные формулировки, сокращения и опечатки: например, "
    "\"хочу летом покодить\" подходит к посту про летний лагерь по программированию.\n"
    "Для каждого поста напиши reason - одну короткую фразу до 80 символов, чем этот пост поможет. "
    "Не пересказывай пост и не отвечай на вопрос сам: человек должен перейти по ссылке и прочитать оригинал.\n"
    "Если подходящих постов нет - верни пустой список posts.\n"
    "Если запрос слишком общий и подходит к очень разным постам - заполни clarify: "
    "короткий уточняющий вопрос до 100 символов. Иначе clarify - пустая строка.\n"
    "Если даны предыдущие запросы - это один разговор, новый запрос уточняет предыдущие.\n"
    "Ответь только JSON без пояснений, в таком виде: "
    '{"posts": [{"number": 12, "reason": "..."}], "clarify": ""}'
)

# какой ответ мы ждём от ИИ: номера постов с пояснениями и уточняющий вопрос
SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["number", "reason"],
                "additionalProperties": False,
            },
        },
        "clarify": {"type": "string"},
    },
    "required": ["posts", "clarify"],
    "additionalProperties": False,
}

# модели, у которых есть fallbacks: если модель откажется отвечать,
# Anthropic сам передаст запрос другой модели
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}

# когда каждый человек последний раз спрашивал ИИ
last_ai_request = {}

# Разговоры для уточнения запроса. Человек отвечает на сообщение бота - и бот ищет
# с учётом прошлых запросов. Ключ - (id чата, id сообщения бота).
# Хранится только в памяти, после перезапуска бота забывается.
dialogs = {}
MAX_QUERIES = 5        # сколько запросов может быть в одном разговоре
DIALOG_MINUTES = 30    # через сколько минут разговор забывается


def is_enabled():
    return client is not None


def today():
    return time.strftime("%d.%m.%Y")


def used_today():
    return get_ai_count(today())


def check_limits(user_id):
    # возвращает текст ошибки или None, если можно спрашивать.
    # дневной лимит - чтобы случайно не потратить все деньги на ключе
    if used_today() >= AI_DAILY_LIMIT:
        return "Умный поиск на сегодня устал 😴 Попробуй обычный поиск или приходи завтра"
    wait = 20 - (time.time() - last_ai_request.get(user_id, 0))
    if wait > 0:
        return f"Умный поиск можно использовать раз в 20 секунд, подожди ещё {int(wait) + 1} сек."
    return None


def save_dialog(chat_id, message_id, user_id, queries):
    # заодно удаляем старые разговоры, чтобы словарь не рос бесконечно
    now = time.time()
    for key in list(dialogs):
        if now - dialogs[key]["time"] > DIALOG_MINUTES * 60:
            del dialogs[key]
    dialogs[(chat_id, message_id)] = {"user": user_id, "queries": queries, "time": now}


def get_dialog(chat_id, message_id, user_id):
    # прошлые запросы разговора или None, если разговора нет, он старый или он чужой
    dialog = dialogs.get((chat_id, message_id))
    if dialog is None or dialog["user"] != user_id:
        return None
    if time.time() - dialog["time"] > DIALOG_MINUTES * 60:
        return None
    return dialog["queries"]


def make_catalog(posts):
    # посты по порядку номеров, чтобы каталог не менялся между запросами
    # (тогда сервис ИИ может его закэшировать, и запрос дешевле и быстрее)
    posts = sorted(posts, key=lambda p: post_number(p[0]))
    lines = []
    for i, (link, text, date) in enumerate(posts, start=1):
        short = " ".join(text.split())  # убираем переносы строк
        if len(short) > CATALOG_CHARS:
            short = short[:CATALOG_CHARS] + "..."
        lines.append(f"[{i}] {date}: {short}")
    return posts, "\n".join(lines)




async def ask_anthropic(catalog, user_text):
    # возвращает текст ответа (JSON) или None
    extra = {}
    if AI_MODEL in FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        response = await client.beta.messages.create(
            model=AI_MODEL,
            max_tokens=4000,
            system=[
                {"type": "text", "text": SYSTEM},
                # каталог помечаем для кэша: если он не менялся, следующий запрос дешевле и быстрее
                {"type": "text", "text": "Посты канала:\n" + catalog, "cache_control": {"type": "ephemeral"}},
            ],
            output_config={
                "effort": "low",  # задача простая, долго думать не надо - отвечает быстрее
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            **extra,
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.RateLimitError:
        logging.warning("ИИ: слишком много запросов")
        return None
    except anthropic.APIError as e:
        logging.error(f"ИИ сломался: {e}")
        return None

    # refusal - модель отказалась, max_tokens - ответ обрезался и JSON будет битый
    if response.stop_reason in ("refusal", "max_tokens"):
        logging.warning(f"ИИ не ответил: {response.stop_reason}")
        return None
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text
    return text


async def ask_openai(catalog, user_text):
    # возвращает текст ответа (JSON) или None
    messages = [
        {"role": "system", "content": SYSTEM + "\n\nПосты канала:\n" + catalog},
        {"role": "user", "content": user_text},
    ]
    try:
        try:
            # json_object - просим сервис вернуть именно JSON
            response = await client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except openai.BadRequestError:
            # не все сервисы понимают response_format - пробуем без него,
            # формат ответа всё равно описан в SYSTEM
            logging.warning("ИИ: сервис не принял response_format, пробую без него")
            response = await client.chat.completions.create(model=AI_MODEL, messages=messages)
    except openai.RateLimitError:
        logging.warning("ИИ: слишком много запросов")
        return None
    except openai.APIError as e:
        logging.error(f"ИИ сломался: {e}")
        return None

    if not response.choices:
        return None
    choice = response.choices[0]
    if choice.finish_reason == "length":  # ответ обрезался - JSON будет битый
        logging.warning("ИИ не ответил: ответ слишком длинный")
        return None
    return choice.message.content


def parse_answer(text, posts):
    # превращаем ответ ИИ в {"posts": [(link, text, date, reason)], "clarify": "..."}.
    # не все сервисы гарантируют правильный формат, поэтому всё проверяем
    if not text:
        return None
    # некоторые модели оборачивают JSON в ```json ... ``` - берём от первой { до последней }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logging.error(f"ИИ вернул не JSON: {text[:200]}")
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        logging.error(f"ИИ вернул не JSON: {text[:200]}")
        return None
    if not isinstance(data, dict):
        return None

    clarify = data.get("clarify")
    if not isinstance(clarify, str):
        clarify = ""
    items = data.get("posts")
    if not isinstance(items, list):
        items = []

    result = {"posts": [], "clarify": clarify.strip()}
    used = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        n = item.get("number")
        reason = item.get("reason")
        if not isinstance(reason, str):
            reason = ""
        # номер не число, его нет в каталоге или это повтор - пропускаем
        if not isinstance(n, int) or n < 1 or n > len(posts) or n in used:
            continue
        used.add(n)
        link, post_text, date = posts[n - 1]
        result["posts"].append((link, post_text, date, reason.strip()))
    result["posts"] = result["posts"][:5]
    return result


async def smart_search(queries, posts, user_id):
    # queries - список запросов разговора, последний - новый.
    # возвращает {"posts": [(link, text, date, reason), ...], "clarify": "..."} или None, если ИИ не смог
    last_ai_request[user_id] = time.time()
    add_ai_count(today())

    if not posts:
        return {"posts": [], "clarify": ""}
    posts, catalog = make_catalog(posts)

    if len(queries) == 1:
        user_text = f"Запрос: {queries[0]}"
    else:
        user_text = "Предыдущие запросы:\n"
        for q in queries[:-1]:
            user_text += f"- {q}\n"
        user_text += f"\nНовый запрос: {queries[-1]}"

    if provider == "openai":
        text = await ask_openai(catalog, user_text)
    else:
        text = await ask_anthropic(catalog, user_text)
    return parse_answer(text, posts)
