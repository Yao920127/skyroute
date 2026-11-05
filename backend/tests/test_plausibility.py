"""剔除明顯虛構的模擬航班：航司母國不在起訖兩地才剔除；正式報價、共享班號、未知航司保留。"""

import pytest

from app.domain.offers import FlightOffer
from app.services.plausibility import drop_obviously_fake, is_obviously_fake
from tests.factories import make_offer

pytestmark = pytest.mark.unit


def offer(
    airline: str,
    origin: str = "TPE",
    destination: str = "NRT",
    simulated: bool = True,
    operating: str | None = None,
) -> FlightOffer:
    base = make_offer(airline=airline)
    slice_ = base.slices[0]
    segment = slice_.segments[0].model_copy(
        update={
            "carrier_code": airline,
            "origin": origin,
            "destination": destination,
            "operating_code": operating,
        }
    )
    return base.model_copy(
        update={
            "is_simulated": simulated,
            "slices": (slice_.model_copy(update={"segments": (segment,)}),),
        }
    )


@pytest.mark.parametrize(
    ("airline", "origin", "destination", "operating", "fake"),
    [
        ("AA", "TPE", "NRT", None, True),  # 美國航空不飛台北－成田
        ("HR", "TPE", "NRT", None, True),  # Hahn Air（德國）
        ("BR", "TPE", "NRT", None, False),  # 長榮：起點在臺灣
        ("JL", "TPE", "NRT", None, False),  # 日航：終點在日本
        ("AA", "TPE", "NRT", "JL", False),  # AA 掛號、JL 營運的共享班號
        ("FR", "MAD", "FCO", None, False),  # Ryanair 歐洲境內航線
        ("UA", "NRT", "GUM", None, False),  # 聯合航空飛關島（美國屬地）
        ("ZZ9", "TPE", "NRT", None, False),  # 不認得的航司：保留
    ],
)
def test_rule(
    airline: str, origin: str, destination: str, operating: str | None, fake: bool
) -> None:
    assert is_obviously_fake(offer(airline, origin, destination, operating=operating)) is fake


def test_live_offers_are_never_dropped() -> None:
    assert is_obviously_fake(offer("AA", simulated=False)) is False


def test_drop_keeps_order_of_remaining() -> None:
    kept = drop_obviously_fake((offer("AA"), offer("BR"), offer("JL")))
    assert [o.slices[0].segments[0].carrier_code for o in kept] == ["BR", "JL"]
