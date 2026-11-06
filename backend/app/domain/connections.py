"""分段購票的銜接規則：下一段要在上一段抵達後留足時間才能起飛，並找出時間可行的最便宜組合。

分段購票是多張獨立機票，轉機時要重新報到、託運行李，因此預留時間比同一張票的轉機長：
同一機場至少 2 小時；換機場（例如倫敦進、巴黎出，或成田進、羽田出）至少 4 小時。

Duffel 的時間是「當地時間、不含時區」。銜接點在同一城市時兩邊時區相同，可以直接相減；
不同城市（開口行程）時只是近似值。
"""

from collections.abc import Sequence
from datetime import datetime

from app.domain.offers import FlightOffer

SAME_AIRPORT_MIN_GAP = 120
OTHER_AIRPORT_MIN_GAP = 240


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=None)


def min_gap_minutes(arrival_airport: str, departure_airport: str) -> int:
    return SAME_AIRPORT_MIN_GAP if arrival_airport == departure_airport else OTHER_AIRPORT_MIN_GAP


def connects(previous: FlightOffer, following: FlightOffer) -> bool:
    """previous 抵達後，following 是否留足時間才起飛（只看單程票的第一段行程）。"""
    arrive = previous.slices[-1]
    depart = following.slices[0]
    gap = (_local(depart.departing_at) - _local(arrive.arriving_at)).total_seconds() / 60
    return gap >= min_gap_minutes(arrive.destination, depart.origin)


def cheapest_chain(options: Sequence[Sequence[FlightOffer]]) -> list[FlightOffer] | None:
    """每段挑一班、前後都銜接得上，且總價最低；沒有任何可行組合時回傳 None。

    動態規劃：best[k][j]＝走到第 k 段、選第 j 班時的最低累計價格。
    """
    if not options or any(len(leg) == 0 for leg in options):
        return None
    costs = [float(o.total_amount) for o in options[0]]
    parents: list[list[int | None]] = [[None] * len(options[0])]
    for k in range(1, len(options)):
        leg_costs: list[float] = []
        leg_parents: list[int | None] = []
        for offer in options[k]:
            best_cost, best_parent = float("inf"), None
            for j, previous in enumerate(options[k - 1]):
                if costs[j] < best_cost and connects(previous, offer):
                    best_cost, best_parent = costs[j], j
            leg_costs.append(best_cost + float(offer.total_amount))
            leg_parents.append(best_parent)
        costs, parents = leg_costs, [*parents, leg_parents]
    end = min(range(len(costs)), key=costs.__getitem__)
    if costs[end] == float("inf"):
        return None
    chain: list[FlightOffer] = []
    index: int | None = end
    for k in range(len(options) - 1, -1, -1):
        assert index is not None
        chain.append(options[k][index])
        index = parents[k][index]
    return list(reversed(chain))
