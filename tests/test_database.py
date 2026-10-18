import database


def test_ai_count():
    database.init_db(":memory:")
    assert database.get_ai_count("01.10.2025") == 0
    database.add_ai_count("01.10.2025")
    database.add_ai_count("01.10.2025")
    database.add_ai_count("02.10.2025")
    assert database.get_ai_count("01.10.2025") == 2
    assert database.get_ai_count("02.10.2025") == 1


def test_save_post():
    database.init_db(":memory:")
    assert database.save_post("https://t.me/test/1", "текст", "01.10.2025") == "new"
    assert database.save_post("https://t.me/test/1", "текст", "01.10.2025") == "same"
    assert database.save_post("https://t.me/test/1", "новый текст", "01.10.2025") == "changed"
    assert database.delete_post("https://t.me/test/1")
    assert database.get_posts() == []
