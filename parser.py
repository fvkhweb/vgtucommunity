# -*- coding: utf-8 -*-
"""
Парсер расписания СПО КССГЕУ (cchgeu.ru) -> schedule.json
Группы 2024 года набора (первые 2 цифры после букв = год, напр. КСК-241о = 2024).

Формат вывода (как на сайте, index.html):
  День|№пары|TOP/BOTTOM|sub|ауд|week_only|Название (Препод)
TOP = числитель (содержимое на строке времени),
BOTTOM = знаменатель (содержимое строки под временем).
sub: 0 = вся группа (общая пара), 1/2/3 = подгруппа.
Запуск:  python parser.py [выходная_папка]
"""
import re
import io
import json
import sys
import time
import urllib.request

import xlrd

BASE = "https://cchgeu.ru/studentu/schedule/spo/"
ORIGIN = "https://cchgeu.ru"

GROUPS_24_RE = re.compile(r"^([А-ЯЁ]{2,4}-24\dо)\.xls$", re.I)
DAY_RE = re.compile(r"^(Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье)\b", re.I)
DAYS_NORM = {"Понедельник": "Понедельник", "Вторник": "Вторник", "Среда": "Среда",
             "Четверг": "Четверг", "Пятница": "Пятница", "Суббота": "Суббота",
             "Воскресенье": "Воскресенье"}
TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2}):\d{2}\s*-\s*\d{1,2}:\d{2}:\d{2}\s*$")
PAIR_START = {"8:30": 0, "10:15": 1, "12:00": 2,
              "14:00": 3, "14:20": 3,   # сдвинутая сетка некоторых групп
              "15:45": 4, "16:05": 4,
              "17:30": 5, "17:50": 5,
              "19:15": 6, "19:35": 6}


def pair_for(start):
    """Индекс пары по времени начала; сдвинутые сетки (+20 мин) мапятся на ту же пару."""
    if start in PAIR_START:
        return PAIR_START[start]
    try:
        h, m = [int(x) for x in start.split(":")]
    except ValueError:
        return None
    mins = h * 60 + m
    best, best_d = None, 10 ** 9
    for k, v in PAIR_START.items():
        a, b = [int(x) for x in k.split(":")]
        d = abs(mins - (a * 60 + b))
        if d < best_d:
            best, best_d = v, d
    return best if best_d <= 30 else None
WEEK_RE = re.compile(r"(\d+)\s*нед", re.I)
LINK_RE = re.compile(r"""href=['"]([^'"]+?\.xls)['"][^>]*>\s*([^<.]+?\.xls)""", re.I)
UPDATED_RE = re.compile(r"обновлено\s+([0-9.,: ]+)")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) vgtucommunity-schedule"}


def norm(s):
    if s is None:
        return ""
    s = str(s).replace("\r", " ").replace("\n", " ")
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def http_get(url, binary=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", "replace")


def get_group_links():
    html = http_get(BASE)
    out = {}
    for m in LINK_RE.finditer(html):
        url, label = m.group(1).strip(), norm(m.group(2))
        gm = GROUPS_24_RE.match(label)
        if not gm:
            continue
        group = norm_group(gm.group(1))
        upd = UPDATED_RE.search(html[m.end(): m.end() + 120])
        out[group] = {"url": url if url.startswith("http") else ORIGIN + url,
                      "updated": upd.group(1).strip(") ,") if upd else ""}
    return out


def norm_group(name):
    """Верхний регистр для аббревиатуры, 'о' в конце остаётся строчной (КСК-241о)."""
    name = name.strip().upper()
    if re.match(r"^[А-ЯЁ]{2,4}-\d{3}О$", name):
        return name[:-1] + "о"
    return name


def celltext(grid, r, c):
    if r >= len(grid) or c >= len(grid[r]):
        return ""
    return grid[r][c]


def parse_xls(raw, group_hint):
    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_index(0)
    nrows, ncols = sheet.nrows, sheet.ncols
    grid = [[norm(sheet.cell_value(r, c)) for c in range(ncols)] for r in range(nrows)]

    # --- шапка: строка, где A == "Время" ---
    header_r = None
    for r in range(min(10, nrows)):
        if grid[r][0].lower().startswith("время"):
            header_r = r
            break
    if header_r is None:
        return {}, "нет шапки"

    hrow, hrow2 = grid[header_r], grid[header_r + 1] if header_r + 1 < nrows else []

    # подгруппы: колонки, где во второй строке шапки есть "п/г"
    content_cols = []   # (col, group_name)
    for c in range(2, ncols):
        if "п/г" in hrow2[c]:
            content_cols.append(c)
    general_col = None
    for c in range(ncols - 1, 1, -1):
        if hrow[c] == "Ауд" and c not in content_cols:
            general_col = c
            break
    if general_col is None:
        general_col = 4 + 2 * len(content_cols) - 2 + 2  # запасной расчёт
        general_col = min(general_col, ncols - 1)

    # группа: самое частое имя группы в шапке (имя повторяется для каждой п/г)
    names = [hrow[c] for c in content_cols if hrow[c]]
    group = norm_group(group_hint)
    if names:
        groups_in_file = sorted(set(norm_group(n) for n in names))
        if len(groups_in_file) == 1:
            group = groups_in_file[0]
    else:
        groups_in_file = [group]

    def extract(r, day, pair_no, lst):
        if r >= nrows:
            return
        items = []  # (sub, title, aud)
        for i, cc in enumerate(content_cols):
            t = norm(celltext(grid, r, cc))
            if not t:
                continue
            items.append((i + 1, t, norm(celltext(grid, r, cc + 1))))
        if not items:
            return
        # одинаковый текст в нескольких п/г с одинаковой/пустой аудиторией = общая пара (sub=0)
        if len(items) > 1 and len(set(t for _, t, _ in items)) == 1 \
                and len(set(a for _, _, a in items)) <= 1:
            aud = next((a for _, _, a in items if a), "")
            items = [(0, items[0][1], aud)]
        for sub, t, aud in items:
            if not aud and general_col is not None:
                ga = norm(celltext(grid, r, general_col))
                if ga:
                    aud, sub = ga, 0   # общая пара: аудитория в общем столбце
            if aud == "Ауд":
                aud = ""
            if not aud:
                aud = "—"
            title = t.replace(" / ", " ")
            title = re.sub(r"\s+", " ", title).strip()
            wk = WEEK_RE.search(title)
            week_only = wk.group(1) if wk else "0"
            lst.append("%s|%d|%s|%d|%s|%s|%s" % (day, pair_no, pos, sub, aud, week_only, title))

    lessons = []
    unknown_starts = set()
    day = None
    r = header_r + 1
    while r < nrows:
        a, b = grid[r][0], grid[r][1]
        tm = TIME_RE.match(b)
        if tm:
            hh, mm = tm.group(1), tm.group(2)
            start = hh + ":" + mm   # как в ячейке ('8:30', '14:20'), без ведущего нуля
            if a and DAY_RE.match(a):
                dm = DAY_RE.match(a)
                day = DAYS_NORM[dm.group(1).capitalize()] if dm.group(1).capitalize() in DAYS_NORM else dm.group(1)
            if day is None:
                r += 1
                continue
            pair_no = pair_for(start)
            if pair_no is None:
                unknown_starts.add(start)
                r += 2
                continue
            pos = "TOP"
            extract(r, day, pair_no, lessons)
            pos = "BOTTOM"
            extract(r + 1, day, pair_no, lessons)
            if not [l for l in lessons if l.startswith(day + "|")]:
                pass
            pos = "TOP"
            r += 2
            continue
        if a and DAY_RE.match(a) and not tm:
            dm = DAY_RE.match(a)
            day = dm.group(1)
        r += 1

    out = {}
    for g in groups_in_file:
        out[norm_group(g)] = sorted(set(lessons))
    if unknown_starts:
        print("    (незнакомые времена пары, пропущены: %s)" % ", ".join(sorted(unknown_starts)))
    return out, "ok"


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    links = get_group_links()
    print("Групп 24-набора на странице: %d" % len(links))
    result = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": BASE, "groups": {}}
    failed = []
    for order, g in enumerate(sorted(links)):
        info = links[g]
        try:
            raw = http_get(info["url"], binary=True)
            parsed, status = parse_xls(raw, g)
            if status != "ok" or g not in parsed:
                failed.append(g + ": " + status)
                continue
            result["groups"][g] = {"updated": info["updated"], "lessons": parsed[g]}
            print("%s — %d пар (обновлено %s)" % (g, len(parsed[g]), info["updated"]))
        except Exception as e:
            failed.append("%s: %s" % (g, e))
        time.sleep(0.3)
    result["errors"] = failed
    path = outdir.rstrip("/") + "/schedule.json"
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("OK ->", path, "| групп:", len(result["groups"]), "| ошибок:", len(failed))


if __name__ == "__main__":
    main()
