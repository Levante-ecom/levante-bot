import asyncio
from db import get_product_by_sku

async def main():
    p = await get_product_by_sku("LV701")
    print(p)

asyncio.run(main())