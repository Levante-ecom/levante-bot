import asyncio
import os
import re
from datetime import date
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db import (
    init_db,
    get_product_by_sku,
    search_products,
    get_active_promos,
    get_promo_skus,
    get_promos_for_sku,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Проверь .env (BOT_TOKEN=...)")

dp = Dispatcher()

MARKETING_TEXT = """
📈 Маркетинг-стратегия
Маркетинг план Levante включает в себя различные бонусы и программы для поддержки и мотивации партнеров. Основные элементы плана:

⦁ Премия Наставника: 15% от товарооборота первого поколения.
⦁ Главный Бонус: До 65% от товарооборота.
⦁ START Бонус: До 60% от Главного Бонуса.
⦁ Премия «Звезда»: 50 Алтын, с последующими выплатами.
⦁ Товарный и Оптовый Кешбэк: До 20% и 26% соответственно.
⦁ АЖС: От 40 Алтынов в месяц до автомобиля или квартиры в подарок.

План отличается простотой, честностью и глубокой оплатой, поддерживая командную работу и постоянных покупателей. Участие в бизнесе начинается с покупки на 50 баллов, что открывает доступ к различным бонусам и скидкам. Каждый партнер может воспользоваться реферальными ссылками для привлечения новых клиентов и получения дополнительных преимуществ. Компания также проводит акции, розыгрыши и путешествия для своих партнеров.
""".strip()

# SKU: 1–3 буквы + 2–4 цифры (ты так описала) — но в твоём CSV есть LV701 (2 буквы + 3 цифры) => ок.
# Я добавила небольшой запас: до 5 букв и до 6 цифр, чтобы не ломалось, если появятся варианты.
SKU_REGEX = re.compile(r"^[A-ZА-Я]{1,5}\d{2,6}$", re.IGNORECASE)

def normalize_sku(text: str) -> str:
    return text.strip().replace(" ", "").replace("-", "").replace("_", "").upper()

def looks_like_sku(text: str) -> bool:
    return bool(SKU_REGEX.fullmatch(normalize_sku(text)))

def menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Маркетинг", callback_data="menu:marketing")
    kb.button(text="🛍 Каталог", callback_data="menu:catalog")
    kb.button(text="🔥 Акции", callback_data="menu:promos")
    kb.adjust(2, 1)
    return kb.as_markup()

class Flow(StatesGroup):
    catalog = State()

def product_caption(p: dict, promo_titles: list[str] | None = None) -> str:
    sku = p.get("sku", "—")
    name = p.get("name", "—")
    category = (p.get("category") or "").strip()
    subtype = (p.get("subtype") or "").strip()
    tags = (p.get("tags") or "").strip()
    ingredients = (p.get("ingredients") or "").strip()
    description = (p.get("description") or "").strip()

    parts = [f"📦 {name}", f"Артикул: {sku}"]

    if category:
        parts.append(f"Категория: {category}")
    if subtype:
        parts.append(f"Тип: {subtype}")
    if tags:
        parts.append(f"Теги: {tags}")

    if promo_titles:
        parts.append("🔥 Акции: " + "; ".join(promo_titles))

    if ingredients:
        parts.append(f"\nСостав:\n{ingredients}")
    if description:
        parts.append(f"\nОписание:\n{description}")

    text = "\n".join(parts)
    if len(text) > 3500:
        text = text[:3500].rstrip() + "…"
    return text

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выбери раздел:", reply_markup=menu_kb())

@dp.callback_query(F.data == "menu:marketing")
async def cb_marketing(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer(MARKETING_TEXT)
    await cb.message.answer("Меню:", reply_markup=menu_kb())
    await cb.answer()

@dp.callback_query(F.data == "menu:catalog")
async def cb_catalog(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Flow.catalog)
    await cb.message.answer(
        "🛍 Каталог\n\n"
        "Напиши:\n"
        "• артикул (пример: LV701)\n"
        "• или запрос (пример: мужской парфюм / древесный / цитрусовый)\n\n"
        "Чтобы вернуться — напиши «меню»."
    )
    await cb.answer()

@dp.callback_query(F.data == "menu:promos")
async def cb_promos(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    promos = await get_active_promos(date.today())
    if not promos:
        await cb.message.answer("Сейчас активных акций нет.")
        await cb.message.answer("Меню:", reply_markup=menu_kb())
        await cb.answer()
        return

    # Покажем список акций (коротко)
    lines = ["🔥 Акции сейчас:"]
    for p in promos[:10]:
        title = p.get("title", "Акция")
        sd = (p.get("start_date") or "").strip()
        ed = (p.get("end_date") or "").strip()
        period = ""
        if sd or ed:
            period = f" ({sd or '...'} — {ed or '...'})"
        lines.append(f"• {title}{period}")

    lines.append("\nЕсли хочешь товары по акции — напиши название акции (или ключевое слово) в каталоге, или скажи мне — добавим режим выбора акции.")
    await cb.message.answer("\n".join(lines))
    await cb.message.answer("Меню:", reply_markup=menu_kb())
    await cb.answer()

@dp.message(Flow.catalog, F.text)
async def catalog_handler(message: Message, state: FSMContext):
    text = message.text.strip()
    low = text.lower()

    if low in ("меню", "/start", "назад"):
        await state.clear()
        await message.answer("Меню:", reply_markup=menu_kb())
        return

    # 1) Артикул
    if looks_like_sku(text):
        sku = normalize_sku(text)
        p = await get_product_by_sku(sku)
        if not p:
            await message.answer("Не нашла товар по этому артикулу. Проверь написание.")
            return

        promos = await get_promos_for_sku(sku)
        promo_titles = [x.get("title", "") for x in promos if x.get("title")]

        caption = product_caption(p, promo_titles=promo_titles)
        image_url = p.get("image_url")

        if image_url:
            # URL должен быть прямой картинкой по https (Drive 'view' может не сработать)
            await message.answer_photo(image_url, caption=caption)
        else:
            await message.answer(caption)
        return

    # 2) Поисковый запрос
    results = await search_products(text, limit=10)
    if not results:
        await message.answer(
            "Ничего не нашла.\n"
            "Попробуй проще: «мужской», «древесный», «цитрусовый», «парфюм» или введи артикул."
        )
        return

    shown = results[:5]
    await message.answer(f"Нашла {len(results)} товаров. Показываю первые {len(shown)}:")

    for p in shown:
        sku = p.get("sku", "")

        # (если ты добавляла акции к карточкам — оставь как было)
        promos = await get_promos_for_sku(sku)
        promo_titles = [x.get("title", "") for x in promos if x.get("title")]

        caption = product_caption(p, promo_titles=promo_titles)
        image_url = (p.get("image_url") or "").strip()

        try:
            if image_url:
                # caption у фото ограничен (1024), поэтому подстрахуемся
                safe_caption = caption[:1000] if len(caption) > 1000 else caption
                await message.answer_photo(image_url, caption=safe_caption)
            else:
                await message.answer(caption)
        except Exception as e:
            # если фото не отправилось — отправим текстом и продолжим
            print(f"Failed to send product {sku} with photo_url={image_url!r}. Error: {e}")
            await message.answer(caption)
            return
    if len(results) > 5:
        await message.answer("Уточни запрос (например: «мужской древесный»), и я покажу точнее.")

@dp.message(F.text)
async def fallback(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню:", reply_markup=menu_kb())

async def main():
    await init_db()
    bot = Bot(TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())