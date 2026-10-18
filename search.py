# Поиск по триграммам.
# Слово режем на кусочки по 3 буквы: "кот" -> "  к", " ко", "кот", "от "
# Чем больше общих кусочков у двух слов, тем они похожее.
# Поэтому "рассписание" всё равно найдёт "расписание".
#
# Ещё поиск понимает:
#   "точная фраза"      - пост должен содержать эту фразу целиком
#   -слово              - посты с этим словом не показывать
#   #тег                - только посты с этим хештегом
#   октябрь, 2025       - только посты за этот месяц / год
#   последние, свежие   - сначала новые посты
#   hfcgbcfybt          - забыл переключить раскладку
#   raspisanie          - написал транслитом

import re
from functools import lru_cache

import pymorphy3

# слова, которые ничего не значат для поиска
STOP_WORDS = {
    "как", "где", "что", "когда", "это", "для", "про", "или", "был", "была", "было", "есть",
    "найди", "найти", "покажи", "подскажи", "скинь", "пост", "посты", "ссылку", "пожалуйста",
    "привет", "можно", "нужно", "надо", "какой", "какая", "какие", "там", "тут", "все",
    "плиз", "плз", "мне", "нам", "будет", "кто", "чем",
}

# если похожесть слов меньше этого числа, считаем что слова разные
MIN_SIMILARITY = 0.5

# длина кусочка поста под ссылкой - чтобы ответ оставался компактным
SNIPPET_CHARS = 60

# синонимы: если ищут левое слово, то правые тоже подходят
SYNONYMS = {
    "цена": ["стоимость", "оплата"],
    "стоит": ["стоимость", "оплата"],
    "сколько": ["стоимость"],
    "деньги": ["стоимость", "оплата"],
    "платно": ["стоимость", "оплата"],
    "бесплатно": ["бесплатный", "бесплатное"],
    "лагерь": ["смена"],
    "смена": ["лагерь"],
    "олимпа": ["олимпиада"],
    "олимп": ["олимпиада"],
    "инфа": ["информатика"],
    "прога": ["программирование"],
    "программа": ["программирование"],
    "питон": ["python"],
    "пайтон": ["python"],
    "уроки": ["занятия"],
    "пары": ["занятия"],
    "кружок": ["курс", "занятия"],
    "запись": ["регистрация", "записаться"],
    "записаться": ["регистрация", "запись"],
    "зарегаться": ["регистрация"],
    "регистрация": ["запись", "записаться"],
    "дедлайн": ["срок"],
    "препод": ["преподаватель"],
    "училка": ["преподаватель"],
}

# месяцы во всех формах, как их пишут в запросе: "октябрь", "в октябре", "до октября"
MONTH_NAMES = [
    ("январь", "января", "январе"),
    ("февраль", "февраля", "феврале"),
    ("март", "марта", "марте"),
    ("апрель", "апреля", "апреле"),
    ("май", "мая", "мае"),
    ("июнь", "июня", "июне"),
    ("июль", "июля", "июле"),
    ("август", "августа", "августе"),
    ("сентябрь", "сентября", "сентябре"),
    ("октябрь", "октября", "октябре"),
    ("ноябрь", "ноября", "ноябре"),
    ("декабрь", "декабря", "декабре"),
]
MONTHS = {}
for number, forms in enumerate(MONTH_NAMES, start=1):
    for form in forms:
        MONTHS[form] = number

# слова, после которых показываем сначала новые посты
NEW_WORDS = {
    "последний", "последняя", "последнее", "последние", "последних",
    "свежий", "свежая", "свежее", "свежие", "свежих",
    "новые", "новое", "новых", "недавний", "недавние", "недавно",
}

# раскладка: что получится, если печатать по-русски на английской раскладке
EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
LAYOUT = {}
for i in range(len(EN)):
    LAYOUT[EN[i]] = RU[i]

# транслит. сначала длинные сочетания, потом одиночные буквы
TRANSLIT = [
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("ch", "ч"), ("sh", "ш"), ("ya", "я"), ("yu", "ю"),
    ("yo", "е"), ("kh", "х"), ("ts", "ц"), ("ye", "е"),
    ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"), ("i", "и"),
    ("y", "ы"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"),
    ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"), ("c", "к"), ("j", "й"), ("x", "кс"),
    ("w", "в"), ("q", "к"),
]


def split_words(text):
    text = text.lower().replace("ё", "е")
    return re.findall(r"[a-zа-я0-9]+", text)


# lru_cache запоминает результат, чтобы не резать одно и то же слово много раз
@lru_cache(maxsize=100000)
def get_trigrams(word):
    word = "  " + word + " "
    trigrams = set()
    for i in range(len(word) - 2):
        trigrams.add(word[i:i + 3])
    # frozenset - set, который нельзя изменить. Нужен, потому что результат запоминается lru_cache
    return frozenset(trigrams)


def similarity(word1, word2):
    t1 = get_trigrams(word1)
    t2 = get_trigrams(word2)
    return len(t1 & t2) / len(t1 | t2)


# морфология: приводим слова к начальной форме, чтобы "олимпиады", "олимпиаду" и
# "олимпиада" считались одним словом. Триграммы при этом остаются - для опечаток
morph = pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=100000)
def lemma(word):
    # начальная форма слова: "олимпиады" -> "олимпиада", "уроки" -> "урок"
    return morph.parse(word)[0].normal_form.replace("ё", "е")


@lru_cache(maxsize=10000)
def text_lemmas(text):
    # все слова текста в начальной форме. Запоминаем, чтобы не разбирать пост при каждом поиске
    lemmas = set()
    for word in split_words(text):
        lemmas.add(lemma(word))
    return frozenset(lemmas)


def word_score(word, lemmas):
    # насколько слово похоже на самое похожее слово из набора: 1 - совпало, 0 - ничего общего
    word = lemma(word)
    if word in lemmas:
        return 1
    best = 0
    for other in lemmas:
        sim = similarity(word, other)
        if sim > best:
            best = sim
    return best


# те же синонимы, но в начальной форме
LEMMA_SYNONYMS = {}
for key, others in SYNONYMS.items():
    LEMMA_SYNONYMS[lemma(key)] = [lemma(other) for other in others]


def fix_layout(text):
    result = ""
    for ch in text.lower():
        result += LAYOUT.get(ch, ch)
    return result


def translit(text):
    text = text.lower()
    for en, ru in TRANSLIT:
        text = text.replace(en, ru)
    return text


def post_number(link):
    # номер поста - последнее число в ссылке. Чем больше номер, тем новее пост
    try:
        return int(link.rstrip("/").split("/")[-1])
    except ValueError:
        return 0


def parse_query(query):
    # разбираем запрос на части: обычные слова, фразы в кавычках, минус-слова, теги, даты
    q = {"words": [], "phrases": [], "minus": [], "tags": [], "month": None, "year": None, "newest": False}

    text = query.lower().replace("ё", "е").replace("«", '"').replace("»", '"')

    q["phrases"] = re.findall(r'"([^"]+)"', text)
    text = text.replace('"', " ")

    q["minus"] = re.findall(r"(?:^|\s)-([a-zа-я0-9]+)", text)
    text = re.sub(r"(?:^|\s)-[a-zа-я0-9]+", " ", text)

    q["tags"] = re.findall(r"#([a-zа-я0-9_]+)", text)

    for word in split_words(text):
        if len(word) == 4 and word.isdigit() and word.startswith("20"):
            q["year"] = word
            continue
        if word in MONTHS:
            q["month"] = MONTHS[word]
            continue
        if word in NEW_WORDS:
            q["newest"] = True
            continue
        if len(word) >= 3 and word not in STOP_WORDS and lemma(word) not in STOP_WORDS:
            q["words"].append(word)
    return q


def post_ok(q, text, date):
    # подходит ли пост под фильтры (фраза, минус-слова, тег, дата)
    low = text.lower().replace("ё", "е")
    for phrase in q["phrases"]:
        if phrase.strip() not in low:
            return False
    post_tags = re.findall(r"#([a-zа-я0-9_]+)", low)
    for tag in q["tags"]:
        if tag not in post_tags:  # именно такой тег, а не "#анонсы" вместо "#анонс"
            return False
    for minus in q["minus"]:
        if word_score(minus, text_lemmas(text)) >= MIN_SIMILARITY:
            return False
    # дата хранится как 01.09.2025
    if q["month"] and date[3:5] != "%02d" % q["month"]:
        return False
    if q["year"] and date[6:] != q["year"]:
        return False
    return True


def score_post(words, text):
    lemmas = text_lemmas(text)
    score = 0
    for query_word in words:
        best = word_score(query_word, lemmas)
        # синоним считается чуть хуже, чем само слово
        for synonym in LEMMA_SYNONYMS.get(lemma(query_word), []):
            best = max(best, word_score(synonym, lemmas) * 0.8)
        if best >= MIN_SIMILARITY:
            score += best
    return score


def search_one(query, posts, limit):
    q = parse_query(query)
    has_filters = q["phrases"] or q["tags"] or q["month"] or q["year"] or q["newest"]
    if not q["words"] and not has_filters:
        return []

    results = []
    for link, text, date in posts:
        if not post_ok(q, text, date):
            continue
        if q["words"]:
            score = score_post(q["words"], text)
            if score == 0:
                continue
        else:
            score = 1  # слов нет, только фильтры - подходит любой пост
        results.append((score, link, text, date))

    if q["newest"] or not q["words"]:
        # сначала новые, а среди одинаково новых - более похожие
        results.sort(key=lambda r: (post_number(r[1]), r[0]), reverse=True)
    else:
        results.sort(key=lambda r: r[0], reverse=True)
    return results[:limit]


def query_variants(query):
    # если в запросе есть английские буквы - может это не та раскладка или транслит,
    # поэтому пробуем ещё два варианта запроса
    if re.search("[a-z]", query.lower()):
        return [query, fix_layout(query), translit(query)]
    return [query]


def search(query, posts, limit=5):
    # ищем по каждому варианту запроса и берём тот, где нашлось лучше
    results = []
    for variant in query_variants(query):
        found = search_one(variant, posts, limit)
        if found and (not results or found[0][0] > results[0][0]):
            results = found
    return results


def did_you_mean(query, posts):
    # ищем в постах слова, похожие на слова запроса, хоть немного.
    # возвращает исправленный запрос или None
    words = parse_query(query)["words"]
    if not words:
        return None
    all_words = set()
    for link, text, date in posts:
        all_words.update(split_words(text))

    fixed = []
    changed = False
    for word in words:
        best_word = word
        best = 0.3  # меньше этого - уже совсем непохоже
        for post_word in all_words:
            sim = similarity(word, post_word)
            if sim > best:
                best = sim
                best_word = post_word
        if best_word != word:
            changed = True
        fixed.append(best_word)
    if not changed:
        return None
    return " ".join(fixed)


def get_title(text):
    # заголовок поста - его первая строчка
    title = text.strip().split("\n")[0]
    if len(title) > 60:
        title = title[:60] + "..."
    return title


def get_snippet(query, text):
    # кусочек поста, где нашлось слово из запроса (кроме заголовка)
    words = []
    for variant in query_variants(query):
        words += parse_query(variant)["words"]
    lines = text.strip().split("\n")[1:]
    for line in lines:
        for word in words:
            if word_score(word, text_lemmas(line)) >= MIN_SIMILARITY:
                line = line.strip()
                if len(line) > SNIPPET_CHARS:
                    line = line[:SNIPPET_CHARS] + "..."
                return line
    return ""


def similar_posts(link, posts, limit=5):
    # посты, похожие на пост link: у кого больше общих слов (в начальной форме)
    base = None
    for post_link, text, date in posts:
        if post_link == link:
            base = content_lemmas(text)
    if not base:
        return []
    results = []
    for post_link, text, date in posts:
        if post_link == link:
            continue
        other = content_lemmas(text)
        if not other:
            continue
        # доля общих слов от всех слов двух постов
        score = len(base & other) / len(base | other)
        if score >= 0.05:
            results.append((score, post_link, text, date))
    results.sort(key=lambda r: r[0], reverse=True)
    return results[:limit]


def content_lemmas(text):
    # значимые слова поста: без коротких слов, чисел и стоп-слов
    result = set()
    for word in text_lemmas(text):
        if len(word) >= 4 and not word.isdigit() and word not in STOP_WORDS:
            result.add(word)
    return result
