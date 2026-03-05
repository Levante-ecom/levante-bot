import asyncio
import aiosqlite
from db import DB_PATH, init_db

async def main():
    print("DB_PATH:", DB_PATH)

    await init_db()

    # 2) открываем и проверяем, какие таблицы реально есть
    db = await aiosqlite.connect(DB_PATH)

    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = await cur.fetchall()
    print("Tables:", [t[0] for t in tables])

    # 3) проверяем количество товаров
    cur = await db.execute("SELECT COUNT(*) FROM products;")
    row = await cur.fetchone()
    print("Количество товаров:", row[0])

    # 4) печатаем 3 примера
    cur = await db.execute("SELECT sku, name, tags FROM products LIMIT 3;")
    rows = await cur.fetchall()
    print("Примеры товаров:")
    for r in rows:
        print(r)

    await db.close()

asyncio.run(main())