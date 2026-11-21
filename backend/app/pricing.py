"""Deterministic pricing. No model ever produces a number that reaches a customer: it comes from here.

Rules (start kit, same on every sheet; the portal behaves the same, see docs/challenges/5u-facts.md):
- chargeable weight = max(actual kg, cbm x 167);
- the rate is the one of the highest break at or below the billed weight;
- billing at a higher break is allowed and is often cheaper: we take the cheapest billed weight >= chargeable;
- the minimum applies to the freight before surcharges; fuel and security are per kg of billed weight.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

KG_PER_CBM = Decimal("167")
CENT = Decimal("0.01")


def money(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(amount: Decimal, currency: str = "EUR") -> str:
    """The one way a total is written to a customer: `1026.00 EUR` (no thousands separator to misread)."""
    return f"{money(amount):.2f} {currency}"


def chargeable(weight_kg: Decimal, volume_cbm: Decimal | None) -> Decimal:
    vol = (volume_cbm or Decimal(0)) * KG_PER_CBM
    return max(Decimal(weight_kg), vol)


def sheet_price(lane: dict, weight_kg: Decimal, volume_cbm: Decimal | None) -> tuple[Decimal, Decimal]:
    """(total EUR, billed kg) for one sheet lane, billed at the cheapest admissible weight."""
    cw = chargeable(weight_kg, volume_cbm)
    breaks = [Decimal(str(b)) for b in lane["breaks_kg"]]
    rates = [Decimal(str(r)) for r in lane["rates_eur_per_kg"]]
    surcharge = Decimal(str(lane["fuel_eur_per_kg"])) + Decimal(str(lane["security_eur_per_kg"]))
    minimum = Decimal(str(lane["minimum_eur"]))
    best: tuple[Decimal, Decimal] | None = None
    for billed in [cw] + [b for b in breaks if b > cw]:
        idx = max(i for i, b in enumerate(breaks) if b <= billed)
        total = money(max(minimum, billed * rates[idx]) + billed * surcharge)
        if best is None or total < best[0]:
            best = (total, billed)
    assert best is not None
    return best


def next_break(breaks: list[int], cw: Decimal) -> Decimal | None:
    above = [Decimal(b) for b in breaks if Decimal(b) > cw]
    return min(above) if above else None


@dataclass
class Offer:
    """One way to fly it (air leg) or to bring it to the airport (pickup leg). Totals in EUR."""
    leg: str                     # air | pickup
    carrier: str
    total: Decimal
    days: Decimal                # transit (air) or pickup time in days (pickup)
    source: str                  # portal | email | sheet
    rate_id: str | None = None   # portal / airline reference to book with
    billed_kg: Decimal | None = None
    reply_mail: int | None = None
    email: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"leg": self.leg, "carrier": self.carrier, "total": str(self.total), "days": str(self.days),
                "source": self.source, "rate_id": self.rate_id,
                "billed_kg": str(self.billed_kg) if self.billed_kg is not None else None,
                "reply_mail": self.reply_mail, "email": self.email, "extra": self.extra}

    @staticmethod
    def of(d: dict) -> "Offer":
        return Offer(d["leg"], d["carrier"], Decimal(d["total"]), Decimal(d["days"]), d["source"], d.get("rate_id"),
                     Decimal(d["billed_kg"]) if d.get("billed_kg") else None, d.get("reply_mail"), d.get("email"),
                     d.get("extra") or {})


def pick(offers: list[Offer], preference: str) -> Offer | None:
    """cheapest: lowest total, then fastest. fastest: fewest days, then cheapest.
    Otherwise the most balanced: price and speed weigh 50/50, each relative to the best on offer."""
    if not offers:
        return None
    if preference == "cheapest":
        return min(offers, key=lambda o: (o.total, o.days))
    if preference == "fastest":
        return min(offers, key=lambda o: (o.days, o.total))
    p0 = min(o.total for o in offers) or Decimal(1)
    d0 = min(o.days for o in offers) or Decimal("0.1")
    return min(offers, key=lambda o: (o.total / p0 + o.days / d0, o.total))


def best_by_carrier(offers: list[Offer]) -> list[Offer]:
    """One offer per carrier. What a carrier quotes now (portal, mail) beats its sheet, which may be stale;
    the sheet only stands in for a carrier that did not answer. Several live prices (two weights): the cheapest."""
    live = {(o.leg, o.carrier.lower()) for o in offers if o.source != "sheet"}
    best: dict[tuple[str, str], Offer] = {}
    for o in offers:
        k = (o.leg, o.carrier.lower())
        if o.source == "sheet" and k in live:
            continue
        # equal price: prefer the offer that carries a reference we can book with
        if k not in best or (o.total, o.rate_id is None) < (best[k].total, best[k].rate_id is None):
            best[k] = o
    return list(best.values())


def quote(air: list[Offer], pickup: list[Offer], preference: str, needs_pickup: bool) -> dict | None:
    """The one option we offer: best air leg (+ best pickup leg for door-to-port). None if it can't be priced."""
    a = pick(best_by_carrier(air), preference)
    if a is None:
        return None
    p = None
    if needs_pickup:
        p = pick(best_by_carrier(pickup), "fastest" if preference == "fastest" else "cheapest")
        if p is None:
            return None
    total = money(a.total + (p.total if p else 0))
    return {"total": str(total), "currency": "EUR", "air": a.as_dict(), "pickup": p.as_dict() if p else None,
            "transit_days": str(a.days)}
