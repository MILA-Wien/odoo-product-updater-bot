import functools
from decimal import Decimal

@functools.lru_cache()
def get_or_create_uom(c, num, category_id=None):
    category_id = category_id or 1
    category_name_suffix = {
        1: "Unit(s)",
        2: "kg",
    }[category_id]
    factor = Decimal("1.0") / Decimal(num)
    search_result = c.search_read(
        "uom.uom",
        cond=[
            ["factor", "=", str(factor)],
            ["rounding", "=", "1.0"],
            ["category_id", "=", category_id],
        ],
    )
    if search_result:
        return int(search_result[0]["id"])

    return c.create(
        "uom.uom",
        {
            "name": "{} {}".format(num, category_name_suffix),
            "category_id": category_id,
            "factor": str(factor),
            "rounding": "1.0",
            "uom_type": "bigger",
        },
    )
