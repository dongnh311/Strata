from shop import Cart, Item, TIER_RATES


def make_cart():
    c = Cart()
    c.tier = "silver"
    c.add(Item("apple", 2.0, 3))
    c.add(Item("bread", 1.5, 2))
    return c


def test_subtotal():
    c = make_cart()
    assert c.subtotal() == 9.0


def test_tier_discount():
    c = make_cart()
    # silver tier should be 8%
    assert abs(c.discount() - 9.0 * 0.08) < 1e-9


def test_coupon_discount():
    c = make_cart()
    c.apply_coupon("SAVE10")
    assert abs(c.coupon_discount() - 0.9) < 1e-9


def test_total():
    c = make_cart()
    c.apply_coupon("SAVE10")
    # 9.0 - 0.72 (tier) - 0.90 (coupon)
    assert abs(c.total() - 7.38) < 1e-9
