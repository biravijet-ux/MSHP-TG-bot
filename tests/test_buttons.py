import database
from handlers.buttons import PAGE_SIZE, search_page


def make_posts(count):
    database.init_db(":memory:")
    for i in range(1, count + 1):
        database.save_post(f"https://t.me/test/{i}", f"Олимпиада номер {i}", "01.10.2025")


def test_pages():
    make_posts(12)
    text, markup, links = search_page("олимпиада", 0)
    assert len(links) == PAGE_SIZE
    assert text.startswith("Вот что нашёл:")
    buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert buttons == ["more", "helped", "similar"]

    text, markup, links = search_page("олимпиада", 2)
    assert len(links) == 2  # 12 постов: 5 + 5 + 2
    assert "11." in text  # нумерация продолжается
    buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert buttons == ["back", "helped", "similar"]  # дальше листать некуда


def test_nothing_found():
    make_posts(3)
    text, markup, links = search_page("квантовая физика", 0)
    assert links == []
