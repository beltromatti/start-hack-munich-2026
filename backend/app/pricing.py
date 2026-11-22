"""Deterministic pricing. No model ever produces a number that reaches a customer: it comes from here.

Rules (start kit, same on every sheet; the portal behaves the same, see docs/challenges/5u-facts.md):
- chargeable weight = max(actual kg, cbm x 167);
- the rate is the one of the highest break at or below the billed weight;
- billing at a higher break is allowed and is often cheaper: we take the cheapest billed weight >= chargeable;
- the minimum applies to the freight before surcharges; fuel and security are per kg of billed weight.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .config import settings

KG_PER_CBM = Decimal("167")
CENT = Decimal("0.01")


def money(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


DATE = "%a %d %b %Y"


def schedule(ready_date: Any, pickup_hours: Any, transit_days: Any, booked_at: datetime | None = None):
    """When a shipment leaves and arrives, estimated from our dates: it leaves when the goods are ready (09:00 on the
    ready date, or now if that is later) plus the pickup time, and arrives transit days after. The one place for
    every date a customer reads, so the quote, the booking and the tracking answer agree."""
    booked = booked_at or datetime.now(timezone.utc)
    ready = booked
    try:
        ready = max(booked, datetime.fromisoformat(str(ready_date)[:10]).replace(hour=9, tzinfo=timezone.utc))
    except ValueError:
        pass
    departure = ready + timedelta(hours=float(pickup_hours or 0))
    return ready, departure, departure + timedelta(days=float(transit_days))


def fmt(amount: Decimal, currency: str = "EUR") -> str:
    """The one way a total is written to a customer: `1026.00 EUR` (no thousands separator to misread)."""
    return f"{money(amount):.2f} {currency}"


def to_eur(amount: Any, currency: str | None, fx: Any, rates: dict[str, Decimal]) -> Decimal | None:
    """Any price in EUR, or None when it cannot be converted (never guessed).
    `fx` is the rate stated with this price: EUR per 1 unit of its currency (the portal's `fx_eur_per_usd` field
    carries it for whatever currency the price is in). `rates` remembers the last stated rate per currency and
    stands in when a later price in that currency states none."""
    cur = (currency or "EUR").upper()
    if cur == "EUR":
        return money(amount)
    try:
        rate = Decimal(str(fx)) if fx else None
    except ArithmeticError:
        rate = None
    if rate and rate > 0:
        rates[cur] = rate
    rate = rates.get(cur)
    return money(Decimal(str(amount)) * rate) if rate else None


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


COMMON_BREAKS = (45, 100, 250, 300, 500, 1000, 2000)  # every break on the 10 sheets and the 15 portal airlines


def breaks_to_try(cw: Decimal, factor: Decimal = Decimal("1.35")) -> list[Decimal]:
    """For a carrier whose breaks we do not know (no sheet, not on the portal): the breaks above the chargeable
    weight at which billing can still be cheaper. Rate plus surcharges never falls by more than 1.33x between
    two breaks on any sheet, so a break further away than `factor` cannot win."""
    return [Decimal(b) for b in COMMON_BREAKS if cw < b < cw * factor]


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


def pick(offers: list[Offer], preference: str, balance: str | None = None) -> Offer | None:
    """cheapest: lowest total, then fastest. fastest: fewest days, then cheapest.
    Anything else: the most balanced, price and speed weigh 50/50 (see `balanced`)."""
    if not offers:
        return None
    if preference == "cheapest":
        return min(offers, key=lambda o: (o.total, o.days))
    if preference == "fastest":
        return min(offers, key=lambda o: (o.days, o.total))
    return balanced(offers, balance or settings.balance_rule)


def balanced(offers: list[Offer], rule: str = "ratio") -> Offer:
    """Price and speed 50/50. The brief does not say how the two are made comparable, and the rules disagree:
    ratio   each relative to the best on offer (total / lowest + days / fewest). Speed dominates when one
            offer is much faster (3 h against 26 h), so it mostly picks the fastest.
    minmax  each scaled 0..1 between the best and the worst on offer. Picks a middle offer when there is one;
            cheapest and fastest tie at 0.5, the tie goes to the cheaper."""
    p_lo, p_hi = min(o.total for o in offers), max(o.total for o in offers)
    d_lo, d_hi = min(o.days for o in offers), max(o.days for o in offers)
    if rule == "minmax":
        def score(o: Offer) -> Decimal:
            p = (o.total - p_lo) / (p_hi - p_lo) if p_hi > p_lo else Decimal(0)
            d = (o.days - d_lo) / (d_hi - d_lo) if d_hi > d_lo else Decimal(0)
            return p + d
    else:
        def score(o: Offer) -> Decimal:
            return o.total / (p_lo or Decimal(1)) + o.days / (d_lo or Decimal("0.1"))
    return min(offers, key=lambda o: (score(o), o.total))


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


def quote(air: list[Offer], pickup: list[Offer], preference: str, needs_pickup: bool,
          pickup_rule: str | None = None, balance: str | None = None, unspecified: str | None = None) -> dict | None:
    """The one option we offer: best air leg (+ best pickup leg for door-to-port). None if it can't be priced.

    pickup_rule  which trucker goes into the all-in total: `asked` (cheapest, or the fastest when the customer
                 asked for fastest), `cheapest` (always) or `balanced` (always the 50/50 pick).
    unspecified  what a request without "cheapest" or "fastest" gets: `balanced`, `cheapest` or `fastest`."""
    pickup_rule, balance = pickup_rule or settings.pickup_rule, balance or settings.balance_rule
    if preference not in ("cheapest", "fastest"):
        preference = unspecified or settings.unspecified_rule
    a = pick(best_by_carrier(air), preference, balance)
    if a is None:
        return None
    p = None
    if needs_pickup:
        how = {"asked": "fastest" if preference == "fastest" else "cheapest", "cheapest": "cheapest"}.get(
            pickup_rule, "balanced")
        p = pick(best_by_carrier(pickup), how, balance)
        if p is None:
            return None
    total = money(a.total + (p.total if p else 0))
    return {"total": str(total), "currency": "EUR", "air": a.as_dict(), "pickup": p.as_dict() if p else None,
            "transit_days": str(a.days)}


def insurance_premium(ins: dict | None) -> Decimal | None:
    """Cargo insurance on the customer's own terms (round 91: "goods value 22000 EUR, insured at 110 % of that
    value, premium rate 0.40 %" = 96.80): value x insured share x rate, at least the minimum. In EUR only; another
    currency is not converted here (None), never guessed."""
    if not ins or ins.get("goods_value") in (None, "") or ins.get("premium_percent") in (None, ""):
        return None
    if (ins.get("currency") or "EUR").upper() not in ("EUR", "€", "EURO", "EUROS"):
        return None
    share = Decimal(str(ins.get("insured_percent") or 100)) / 100
    premium = Decimal(str(ins["goods_value"])) * share * Decimal(str(ins["premium_percent"])) / 100
    if ins.get("minimum_premium") not in (None, ""):
        premium = max(premium, Decimal(str(ins["minimum_premium"])))
    return money(premium)
