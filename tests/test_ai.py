# Тесты умного поиска. Настоящий ИИ не вызывается - вместо него подставной клиент,
# который возвращает заранее заданный ответ и запоминает, что ему отправили.

import asyncio
import json
from types import SimpleNamespace

import ai
import database

POSTS = [
    ("https://t.me/test/2", "Летняя смена в лагере\nПрограммирование и походы", "20.05.2025"),
    ("https://t.me/test/1", "Расписание занятий на осень", "01.09.2025"),
]


class FakeClient:
    def __init__(self, answer, stop_reason="end_turn"):
        self.answer = answer
        self.stop_reason = stop_reason
        self.sent = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.sent = kwargs
        block = SimpleNamespace(type="text", text=self.answer)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[block])


class FakeOpenAI:
    # подставной клиент в стиле библиотеки openai
    def __init__(self, answer, finish_reason="stop"):
        self.answer = answer
        self.finish_reason = finish_reason
        self.sent = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.sent = kwargs
        message = SimpleNamespace(content=self.answer)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=self.finish_reason)])


def run(answer, queries=("хочу летом покодить",), stop_reason="end_turn"):
    database.init_db(":memory:")
    ai.last_ai_request.clear()
    ai.provider = "anthropic"
    ai.client = FakeClient(answer, stop_reason)
    result = asyncio.run(ai.smart_search(list(queries), POSTS, user_id=1))
    return result, ai.client.sent


def test_catalog_sorted_by_post_number():
    posts, catalog = ai.make_catalog(POSTS)
    assert posts[0][0] == "https://t.me/test/1"
    assert catalog.startswith("[1] 01.09.2025: Расписание занятий на осень")
    assert "[2] 20.05.2025: Летняя смена в лагере Программирование и походы" in catalog


def test_smart_search_returns_links_from_numbers():
    answer = json.dumps({"posts": [{"number": 2, "reason": "Про летний лагерь"}], "clarify": ""})
    result, sent = run(answer)
    assert result["posts"] == [(POSTS[0][0], POSTS[0][1], POSTS[0][2], "Про летний лагерь")]
    assert result["clarify"] == ""
    assert sent["messages"][0]["content"] == "Запрос: хочу летом покодить"
    assert database.get_ai_count(ai.today()) == 1


def test_wrong_and_repeated_numbers_are_skipped():
    answer = json.dumps({"posts": [
        {"number": 7, "reason": "такого поста нет"},
        {"number": 0, "reason": "и такого"},
        {"number": 1, "reason": "расписание"},
        {"number": 1, "reason": "повтор"},
    ], "clarify": ""})
    result, sent = run(answer)
    assert len(result["posts"]) == 1
    assert result["posts"][0][3] == "расписание"


def test_history_goes_to_ai():
    answer = json.dumps({"posts": [], "clarify": "Для какого класса?"})
    result, sent = run(answer, queries=["курсы", "для 7 класса"])
    assert result["clarify"] == "Для какого класса?"
    assert sent["messages"][0]["content"] == "Предыдущие запросы:\n- курсы\n\nНовый запрос: для 7 класса"


def test_broken_answers():
    assert run("это не json")[0] is None
    assert run("{}", stop_reason="refusal")[0] is None
    assert run('{"posts": [', stop_reason="max_tokens")[0] is None


def test_dialogs():
    ai.dialogs.clear()
    ai.save_dialog(chat_id=10, message_id=5, user_id=1, queries=["курсы"])
    assert ai.get_dialog(10, 5, 1) == ["курсы"]
    assert ai.get_dialog(10, 5, 2) is None  # чужой разговор
    assert ai.get_dialog(10, 6, 1) is None  # другое сообщение
    # старый разговор забывается
    ai.dialogs[(10, 5)]["time"] -= ai.DIALOG_MINUTES * 60 + 1
    assert ai.get_dialog(10, 5, 1) is None


def test_openai_provider():
    database.init_db(":memory:")
    ai.provider = "openai"
    ai.client = FakeOpenAI(json.dumps({"posts": [{"number": 2, "reason": "лагерь"}], "clarify": ""}))
    result = asyncio.run(ai.smart_search(["хочу летом покодить"], POSTS, user_id=1))
    assert result["posts"][0][0] == "https://t.me/test/2"
    sent = ai.client.sent
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][0]["role"] == "system"
    assert "Посты канала:" in sent["messages"][0]["content"]
    assert sent["messages"][1]["content"] == "Запрос: хочу летом покодить"

    ai.client = FakeOpenAI("{}", finish_reason="length")
    assert asyncio.run(ai.smart_search(["курсы"], POSTS, user_id=1)) is None
    ai.provider = "anthropic"


def test_parse_answer_is_careful():
    posts, catalog = ai.make_catalog(POSTS)
    # JSON в ```json ... ``` - тоже понимаем
    result = ai.parse_answer('```json\n{"posts": [{"number": 1, "reason": "да"}], "clarify": ""}\n```', posts)
    assert result["posts"][0][3] == "да"
    # кривые поля не ломают бота
    result = ai.parse_answer('{"posts": [{"number": "1"}, 5, {"number": 2}], "clarify": null}', posts)
    assert [p[0] for p in result["posts"]] == ["https://t.me/test/2"]
    assert result["clarify"] == ""
    assert ai.parse_answer("", posts) is None
    assert ai.parse_answer("[1, 2]", posts) is None
