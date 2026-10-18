from handlers import messages


def test_commands_before_any_text():
    # aiogram проверяет обработчики по порядку. on_text ловит любой текст,
    # поэтому если команда окажется ниже него - она никогда не сработает
    names = [h.callback.__name__ for h in messages.router.message.handlers]
    on_text = names.index("on_text")
    for command in ("help_command", "ai_command", "search_command"):
        assert names.index(command) < on_text, command
