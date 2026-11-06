"""分段購票銜接：下一段要在上一段抵達後留足時間；找時間可行的最便宜組合。"""

import pytest

from app.domain.connections import cheapest_chain, connects
from app.domain.offers import FlightOffer
from tests.factories import make_offer

pytestmark = pytest.mark.unit


def flight(offer_id: str, amount: str, origin: str, dest: str, dep: str, arr: str) -> FlightOffer:
    base = make_offer(offer_id, amount)
    slice_ = base.slices[0].model_copy(
        update={"origin": origin, "destination": dest, "departing_at": dep, "arriving_at": arr}
    )
    return base.model_copy(update={"slices": (slice_,)})


# 截圖中的情境：12/12 NRT→CTS 19:40 才到，CTS→NRT 卻選了 13:40 起飛
TO_CTS = flight("a", "100", "NRT", "CTS", "2026-12-12T17:50:00", "2026-12-12T19:40:00")
BACK_EARLY = flight("b", "50", "CTS", "NRT", "2026-12-12T13:40:00", "2026-12-12T15:30:00")
BACK_TIGHT = flight("c", "60", "CTS", "NRT", "2026-12-12T21:00:00", "2026-12-12T22:50:00")
BACK_OK = flight("d", "90", "CTS", "NRT", "2026-12-12T21:45:00", "2026-12-12T23:35:00")
BACK_NEXT_DAY = flight("e", "70", "CTS", "NRT", "2026-12-13T09:00:00", "2026-12-13T10:50:00")


def test_needs_two_hours_at_the_same_airport() -> None:
    assert not connects(TO_CTS, BACK_EARLY)  # 抵達前就起飛
    assert not connects(TO_CTS, BACK_TIGHT)  # 只隔 80 分
    assert connects(TO_CTS, BACK_OK)  # 隔 125 分


def test_needs_four_hours_when_changing_airports() -> None:
    to_hnd = flight("x", "1", "TPE", "HND", "2026-12-05T08:00:00", "2026-12-05T12:00:00")
    from_nrt_3h = flight("y", "1", "NRT", "CTS", "2026-12-05T15:00:00", "2026-12-05T17:00:00")
    from_nrt_4h = flight("z", "1", "NRT", "CTS", "2026-12-05T16:00:00", "2026-12-05T18:00:00")
    assert not connects(to_hnd, from_nrt_3h)
    assert connects(to_hnd, from_nrt_4h)


def test_cheapest_chain_skips_impossible_combinations() -> None:
    chain = cheapest_chain([[TO_CTS], [BACK_EARLY, BACK_TIGHT, BACK_OK, BACK_NEXT_DAY]])
    assert chain is not None and [o.id for o in chain] == ["a", "e"]  # 70 比 90 便宜


def test_chain_is_optimal_across_legs_not_greedy() -> None:
    cheap_late = flight("p", "10", "TPE", "NRT", "2026-12-05T18:00:00", "2026-12-05T22:00:00")
    pricey_early = flight("q", "40", "TPE", "NRT", "2026-12-05T06:00:00", "2026-12-05T10:00:00")
    evening = flight("r", "20", "NRT", "CTS", "2026-12-05T20:00:00", "2026-12-05T22:00:00")
    next_day = flight("s", "100", "NRT", "CTS", "2026-12-06T09:00:00", "2026-12-06T11:00:00")
    chain = cheapest_chain([[cheap_late, pricey_early], [evening, next_day]])
    # 貪婪法會先選 10 元的晚班，只能接 100 元的隔天班（共 110）；最佳解是 40＋20＝60
    assert chain is not None and [o.id for o in chain] == ["q", "r"]


def test_no_feasible_chain() -> None:
    assert cheapest_chain([[TO_CTS], [BACK_EARLY, BACK_TIGHT]]) is None
    assert cheapest_chain([[TO_CTS], []]) is None
