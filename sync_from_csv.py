import asyncio
import csv
import io
import re
from typing import Dict, Iterable, Optional

import requests

from db import init_db, upsert_product


# ✅ ТВОЯ ССЫЛКА НА ТАБЛИЦУ (можешь менять только её)
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1cF4KAHo5VxQQG8MvE-xSpjBf3jrAHg7yiOxZTgHyVcw/edit?usp=sharing"

# ✅ GID листа с товарами (обычно 0 для первого листа)
PRODUCTS_GID = 0


def extract_spreadsheet_id(url: str) -> str:
    """
    Достаёт ID таблицы из ссылок формата:
    https://docs.google.com/spreadsheets/d/<ID>/edit?...
    """
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("Не смогла достать spreadsheet_id из ссылки. Проверь URL.")
    return m.group(1)


def build_csv_export_url(spreadsheet_url: str, gid: int) -> str:
    """
    Делает прямую ссылку на CSV экспорт конкретного листа по gid:
    https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>
    """
    sid = extract_spreadsheet_id(spreadsheet_url)
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"


def normalize_tags(tags: str) -> str:
    # "Цитрусовый, морской, мужской" -> "цитрусовый,морской,мужской"
    if not tags:
        return ""
    parts = [p.strip().lower() for p in tags.split(",") if p.strip()]
    return ",".join(parts)


def load_csv_rows_from_url(url: str) -> Iterable[Dict]:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    content = r.content.decode("utf-8-sig")  # utf-8-sig чтобы не ломалась шапка от BOM
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        yield row


def map_row(row: Dict) -> Dict:
    """
    Ожидаемые колонки в твоём Google Sheet:
    SKU, Name, category, subtype, ingredients, description, tags, image_url

    (регистр в CSV может быть разный — мы учитываем оба варианта)
    """
    sku = (row.get("SKU") or row.get("sku") or "").strip().upper()
    name = (row.get("Name") or row.get("name") or "").strip()

    category = (row.get("category") or row.get("Category") or "").strip()
    subtype = (row.get("subtype") or row.get("Subtype") or "").strip()

    ingredients = (row.get("ingredients") or row.get("Ingredients") or "").strip()
    description = (row.get("description") or row.get("Description") or "").strip()

    tags = normalize_tags(row.get("tags") or row.get("Tags") or "")
    image_url = (row.get("image_url") or row.get("Image_url") or row.get("image") or "").strip() or None

    # SKU и name — обязательные
    if not sku or not name:
        return {}

    return {
        "sku": sku,
        "name": name,
        "category": category,
        "subtype": subtype,
        "ingredients": ingredients,
        "description": description,
        "tags": tags,
        "image_url": image_url,
    }


async def main():
    await init_db()
    from db import DB_PATH
    print("SYNC DB_PATH:", DB_PATH)
    export_url = build_csv_export_url(SPREADSHEET_URL, PRODUCTS_GID)
    print("CSV export URL:", export_url)

    rows = load_csv_rows_from_url(export_url)

    rows_iter = load_csv_rows_from_url(export_url)

    # --- DEBUG: посмотрим заголовки и первую строку ---
    first_row = None
    for row in rows_iter:
        first_row = row
        break

    if not first_row:
        print("CSV пустой или не прочитался.")
        return

    print("CSV headers:", list(first_row.keys()))
    print("First row sample:", first_row)

    # Теперь продолжаем уже с первой строкой + остальными
    count = 0

    p = map_row(first_row)
    print("Mapped first row:", p)  # DEBUG
    if p:
        await upsert_product(p)
        count += 1

    # снова создаём итератор, чтобы прочитать всё (кроме первой строки уже вставленной)
    rows_iter = load_csv_rows_from_url(export_url)
    skipped = True
    for row in rows_iter:
        if skipped:
            skipped = False
            continue
        p = map_row(row)
        if not p:
            continue
        await upsert_product(p)
        count += 1


if __name__ == "__main__":
    asyncio.run(main())