import aiosqlite
from datetime import date
from typing import Optional, List, Dict
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "products.db")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    subtype TEXT,
    ingredients TEXT,
    description TEXT,
    tags TEXT,
    image_url TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS promos (
    promo_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    details TEXT,
    start_date TEXT,   -- YYYY-MM-DD
    end_date TEXT      -- YYYY-MM-DD
);

CREATE TABLE IF NOT EXISTS promo_items (
    promo_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    PRIMARY KEY (promo_id, sku),
    FOREIGN KEY (promo_id) REFERENCES promos(promo_id) ON DELETE CASCADE,
    FOREIGN KEY (sku) REFERENCES products(sku) ON DELETE CASCADE
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_SQL)
        await db.commit()

async def upsert_product(p: Dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO products (sku, name, category, subtype, ingredients, description, tags, image_url, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(sku) DO UPDATE SET
              name=excluded.name,
              category=excluded.category,
              subtype=excluded.subtype,
              ingredients=excluded.ingredients,
              description=excluded.description,
              tags=excluded.tags,
              image_url=excluded.image_url,
              is_active=1
            """,
            (
                (p.get("sku") or "").strip().upper(),
                (p.get("name") or "").strip(),
                (p.get("category") or "").strip(),
                (p.get("subtype") or "").strip(),
                (p.get("ingredients") or "").strip(),
                (p.get("description") or "").strip(),
                (p.get("tags") or "").strip(),
                (p.get("image_url") or "").strip() or None,
            ),
        )
        await db.commit()

async def get_product_by_sku(sku: str) -> Optional[Dict]:
    sku = (sku or "").strip().upper()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM products WHERE sku = ? AND is_active = 1",
            (sku,),
        )

        row = await cursor.fetchone()

        if row:
            return dict(row)

        return None

async def search_products(query: str, limit: int = 10) -> List[Dict]:
    q = (query or "").strip().lower()
    tokens = [t for t in q.replace(",", " ").split() if t]
    if not tokens:
        return []

    where_parts = []
    params = []
    for t in tokens:
        where_parts.append(
            "(lower(name) LIKE ? OR lower(description) LIKE ? OR lower(tags) LIKE ? OR lower(category) LIKE ? OR lower(subtype) LIKE ?)"
        )
        like = f"%{t}%"
        params.extend([like, like, like, like, like])

    where_sql = " AND ".join(where_parts)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""
            SELECT * FROM products
            WHERE is_active = 1 AND ({where_sql})
            LIMIT ?
            """,
            (*params, limit),
        )
        return [dict(r) for r in rows]

# --- Promos (на будущее, чтобы кнопка "Акции" работала) ---

async def get_active_promos(today: Optional[date] = None) -> List[Dict]:
    if today is None:
        today = date.today()
    today_s = today.isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """
            SELECT * FROM promos
            WHERE
              (start_date IS NULL OR start_date = '' OR start_date <= ?)
              AND
              (end_date IS NULL OR end_date = '' OR end_date >= ?)
            ORDER BY start_date DESC
            """,
            (today_s, today_s),
        )
        return [dict(r) for r in rows]

async def get_promos_for_sku(sku: str) -> List[Dict]:
    sku = (sku or "").strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """
            SELECT p.*
            FROM promos p
            JOIN promo_items pi ON pi.promo_id = p.promo_id
            WHERE pi.sku = ?
            """,
            (sku,),
        )
        return [dict(r) for r in rows]
async def get_promo_skus(promo_id: str, limit: int = 200) -> List[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT sku FROM promo_items WHERE promo_id = ? LIMIT ?",
            (promo_id, limit),
        )
        return [r[0] for r in rows]