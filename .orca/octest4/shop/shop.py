"""Tiny shop package: cart, pricing tiers, coupons."""

TIER_RATES = {"bronze": 0.05, "silver": 0.08, "gold": 0.12}


class Item:
    def __init__(self, name, price, qty=1):
        self.name = name
        self.price = price
        self.qty = qty


class Cart:
    def __init__(self):
        self.items = []
        self.coupon = None

    def add(self, item):
        self.items.append(item)

    def apply_coupon(self, code):
        self.coupon = code

    def subtotal(self):
        return sum(i.price * i.qty for i in self.items)

    def discount(self):
        tier = getattr(self, "tier", "bronze")
        return self.subtotal() * TIER_RATES[tier]

    def coupon_discount(self):
        if self.coupon == "SAVE10":
            return self.subtotal() * 0.10
        return 0.0

    def total(self):
        return self.subtotal() - self.discount() - self.coupon_discount()
