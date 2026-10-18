import sqlite3

conn = None


def init_db(path):
    global conn
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            link TEXT PRIMARY KEY,
            text TEXT,
            date TEXT
        )
    """)
    # сколько раз спрашивали ИИ в каждый день, чтобы лимит не сбрасывался при перезапуске бота
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage (
            date TEXT PRIMARY KEY,
            count INTEGER
        )
    """)
    # простые счётчики для /stats, например сколько раз нажали «Помогло»
    conn.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER
        )
    """)
    conn.commit()


def save_post(link, text, date):
    # возвращает "new" - новый пост, "changed" - текст поменялся, "same" - ничего не поменялось
    row = conn.execute("SELECT text FROM posts WHERE link = ?", (link,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO posts (link, text, date) VALUES (?, ?, ?)", (link, text, date))
        conn.commit()
        return "new"
    if row[0] == text:
        return "same"
    conn.execute("UPDATE posts SET text = ? WHERE link = ?", (text, link))
    conn.commit()
    return "changed"


def delete_post(link):
    cursor = conn.execute("DELETE FROM posts WHERE link = ?", (link,))
    conn.commit()
    return cursor.rowcount > 0


def get_posts():
    # список кортежей (link, text, date)
    return conn.execute("SELECT link, text, date FROM posts").fetchall()


def get_ai_count(date):
    row = conn.execute("SELECT count FROM ai_usage WHERE date = ?", (date,)).fetchone()
    if row is None:
        return 0
    return row[0]


def add_ai_count(date):
    if get_ai_count(date) == 0:
        conn.execute("INSERT OR REPLACE INTO ai_usage (date, count) VALUES (?, 1)", (date,))
    else:
        conn.execute("UPDATE ai_usage SET count = count + 1 WHERE date = ?", (date,))
    conn.commit()


def get_counter(name):
    row = conn.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()
    if row is None:
        return 0
    return row[0]


def add_counter(name):
    if get_counter(name) == 0:
        conn.execute("INSERT OR REPLACE INTO counters (name, value) VALUES (?, 1)", (name,))
    else:
        conn.execute("UPDATE counters SET value = value + 1 WHERE name = ?", (name,))
    conn.commit()


def make_link(username, chat_id, message_id):
    # ссылка на пост: у публичного канала через username, у приватного через /c/
    if username:
        return f"https://t.me/{username.lower()}/{message_id}"
    chat_id = str(chat_id).replace("-100", "", 1)
    return f"https://t.me/c/{chat_id}/{message_id}"
