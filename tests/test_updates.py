from handlers import updates


def test_parse_link(monkeypatch):
    monkeypatch.setattr(updates, "CHANNEL_ID", "-1001234567890")
    monkeypatch.setattr(updates, "CHANNEL_USERNAME", "")
    assert updates.parse_link("https://t.me/c/1234567890/7") == 7
    assert updates.parse_link("обнови t.me/c/1234567890/12?comment=5") == 12
    assert updates.parse_link("https://t.me/c/1111111111/7") is None  # чужой канал
    assert updates.parse_link("https://t.me/mshp/7") is None
    assert updates.parse_link("просто текст 123") is None

    monkeypatch.setattr(updates, "CHANNEL_ID", "")
    monkeypatch.setattr(updates, "CHANNEL_USERNAME", "mshp")
    assert updates.parse_link("https://t.me/MSHP/850") == 850
    assert updates.parse_link("https://t.me/other/850") is None


def test_is_update_request():
    assert updates.is_update_request("обнови")
    assert updates.is_update_request("Update")
    assert updates.is_update_request("обнови https://t.me/c/1234567890/7")
    # это обычный поиск, а не обновление
    assert not updates.is_update_request("обновить расписание")
    assert not updates.is_update_request("расписание")
    assert not updates.is_update_request("")
