from search import did_you_mean, fix_layout, get_snippet, lemma, parse_query, search, similar_posts, similarity, translit

POSTS = [
    ("https://t.me/test/1", "Расписание занятий на осень\nPython по вторникам и четвергам", "01.09.2025"),
    ("https://t.me/test/2", "Олимпиада по информатике\nРегистрация открыта до конца октября", "15.10.2025"),
    ("https://t.me/test/3", "Стоимость обучения и скидки\nОплата помесячно", "03.09.2025"),
    ("https://t.me/test/4", "Летняя смена в лагере\nПрограммирование и походы", "20.05.2025"),
    ("https://t.me/test/5", "Обновлённое рассписание кружка робототехники", "10.10.2025"),
    ("https://t.me/test/6", "Олимпиада для школьников #анонс\nШкольная олимпиада по программированию", "02.10.2024"),
]


def first_link(query):
    results = search(query, POSTS)
    return results[0][1] if results else None


def test_normal_search():
    assert first_link("олимпиада информатика") == "https://t.me/test/2"
    assert first_link("стоимость обучения") == "https://t.me/test/3"
    assert first_link("летняя смена") == "https://t.me/test/4"


def test_typos_in_query():
    assert first_link("олимпиаад по инфарматике") == "https://t.me/test/2"
    assert first_link("стоимасть обучения") == "https://t.me/test/3"


def test_typo_in_post():
    # в посте написано "рассписание", а ищут правильно
    assert first_link("расписание робототехники") == "https://t.me/test/5"


def test_nothing_found():
    assert search("квантовая физика", POSTS) == []
    assert search("где", POSTS) == []


def test_similarity():
    assert similarity("расписание", "расписание") == 1
    assert similarity("расписание", "рассписание") > 0.5
    assert similarity("расписание", "описание") < 0.5


def links(query):
    return [r[1] for r in search(query, POSTS)]


def test_wrong_layout():
    assert fix_layout("hfcgbcfybt") == "расписание"
    assert first_link("jkbvgbflf byajhvfnbrf") == "https://t.me/test/2"  # олимпиада информатика


def test_translit():
    assert translit("raspisanie") == "расписание"
    assert first_link("stoimost obucheniya") == "https://t.me/test/3"


def test_synonyms():
    # в посте "стоимость", а спрашивают "цена"
    assert first_link("цена") == "https://t.me/test/3"


def test_phrase():
    assert links('"летняя смена"') == ["https://t.me/test/4"]
    assert links('"смена летняя"') == []


def test_minus_word():
    assert "https://t.me/test/6" in links("олимпиада")
    assert "https://t.me/test/6" not in links("олимпиада -школьников")


def test_hashtag():
    assert links("#анонс") == ["https://t.me/test/6"]


def test_month_and_year():
    assert links("олимпиада 2024") == ["https://t.me/test/6"]
    assert links("олимпиада октябрь 2025") == ["https://t.me/test/2"]
    assert set(links("май")) == {"https://t.me/test/4"}


def test_newest_first():
    # без слов, только "последние" - все посты, новые сверху
    assert links("последние")[0] == "https://t.me/test/6"


def test_did_you_mean():
    assert did_you_mean("роботахник", POSTS) == "робототехники"
    assert did_you_mean("квантовая", POSTS) is None


def test_snippet():
    assert get_snippet("python", POSTS[0][1]) == "Python по вторникам и четвергам"


def test_month_only_exact_words():
    # "мартышка" - не месяц март, а обычное слово
    assert parse_query("мартышка")["month"] is None
    assert parse_query("олимпиада в марте")["month"] == 3


def test_hashtag_exact():
    posts = [("https://t.me/test/1", "Пост #анонсы", "01.01.2025")]
    assert search("#анонс", posts) == []


def test_snippet_wrong_layout():
    # запрос в английской раскладке, а кусочек всё равно находится
    assert get_snippet("ghjuhfvvbhjdfybt", POSTS[3][1]) == "Программирование и походы"


def test_word_forms():
    assert lemma("олимпиады") == "олимпиада"
    assert lemma("уроки") == "урок"
    assert first_link("олимпиаду по информатике") == "https://t.me/test/2"
    assert first_link("занятие") == "https://t.me/test/1"  # в посте "занятий"
    assert first_link("смены") == "https://t.me/test/4"


def test_similar_posts():
    posts = [
        ("https://t.me/test/1", "Олимпиада по программированию для школьников", "01.01.2025"),
        ("https://t.me/test/2", "Результаты олимпиады по программированию", "02.01.2025"),
        ("https://t.me/test/3", "Стоимость обучения", "03.01.2025"),
    ]
    similar = similar_posts("https://t.me/test/1", posts)
    assert [r[1] for r in similar] == ["https://t.me/test/2"]
    assert similar_posts("https://t.me/test/404", posts) == []
