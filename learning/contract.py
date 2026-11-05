"""E6.2：掌握度的唯一消费契约。

三件事必须分开，谁都不许彼此冒充：

1. **事实** —— ``mastery_attempts`` 里的逐次作答。只增不改语义，靠 ``evidence_key``
   保证同一条证据不会被重复计数。
2. **估计** —— 由事实算出的掌握度与状态。纯函数（``learning.engine``），带算法版本，
   同一份历史无论回放多少次都得到同一个结果。
3. **调度** —— ``next_review`` / ``interval_days`` / ``ease_factor``。这是 SM-2 的
   结果，回答「什么时候再来一次」，不回答「他学会了没有」。

用户显式标记（``manual_status`` / ``manual_at``）属于第二类里的一个独立来源：
在它之后没有新证据时优先于推导结果 —— 用户说了算，但系统不假装那是自己算的
（``status_source == "manual"``）。

所有读掌握度的入口（复习队列、进度概览、计划完成判定、Agent 工具、CLI、Web API、
个性化上下文）都必须经过这里，不再各自拼字段。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .engine import MASTERY_ALGORITHM_VERSION, derived_status, weighted_mastery
from .schema import MASTERY_UNSEEN
from .store import LearningStore

# 推导窗口：与 engine.ATTEMPT_WEIGHTS 等长。
WINDOW = 5

# 列表推导的扫描上限。掌握度概念数量远小于此值；用上限而不是分页，是因为
# 「最弱优先」必须在全量上排序，不能在旧口径的 score 排序结果上截断。
_LIST_CAP = 5000


@dataclass(frozen=True)
class MasteryState:
    """一个概念在某次读取时的完整解释。"""

    concept: str
    status: str
    status_source: str      # manual | history | stored | none
    mastery: float          # 0..1，推导值；没有历史时回退到存量分数
    mastery_source: str     # history | stored | none
    evidence: int           # 推导实际用到几次作答（≤ WINDOW）
    attempts_total: int     # 累计作答证据条数
    algorithm: str          # 算法版本，改规则必须改它
    next_review: str | None = None
    interval_days: int = 0
    review_count: int = 0
    last_reviewed: str | None = None
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def unseen_state(concept: str) -> MasteryState:
    return MasteryState(
        concept=concept,
        status=MASTERY_UNSEEN,
        status_source="none",
        mastery=0.0,
        mastery_source="none",
        evidence=0,
        attempts_total=0,
        algorithm=MASTERY_ALGORITHM_VERSION,
    )


def _manual_wins(manual_status: str | None, manual_at: str | None, latest_attempt_at: str | None) -> bool:
    """用户标记是否仍然有效：标记过，且之后没有新的作答证据。

    时间戳都是同一格式的 UTC ISO 字符串，可以直接比大小。
    """
    if not manual_status:
        return False
    if not manual_at or not latest_attempt_at:
        return True
    return manual_at >= latest_attempt_at


def state_from_row(
    store: LearningStore,
    record,
    *,
    attempts: list[dict] | None = None,
    stats: dict[str, Any] | None = None,
) -> MasteryState:
    """把一行聚合记录（或已读出的 Mastery）补成完整契约。

    ``record`` 可以是 ``learning.schema.Mastery``，也可以是映射（队列条目那种）。
    ``attempts`` / ``stats`` 由批量调用方预取，避免每个概念各查三次库。
    """
    get = record.get if isinstance(record, dict) else (lambda key, default=None: getattr(record, key, default))
    concept = str(get("concept") or "")
    if not concept:
        return unseen_state("")

    if attempts is None:
        attempts = store.recent_mastery_attempts(concept, limit=WINDOW)
    if stats is None:
        attempts_total = store.count_mastery_attempts(concept)
        latest_at = store.latest_attempt_at(concept)
    else:
        attempts_total = int(stats.get("total") or 0)
        latest_at = stats.get("latest_at")

    manual_status = get("manual_status")
    manual_at = get("manual_at")

    if _manual_wins(manual_status, manual_at, latest_at):
        status, status_source = str(manual_status), "manual"
    elif attempts:
        status, status_source = derived_status(attempts), "history"
    else:
        status, status_source = str(get("status") or MASTERY_UNSEEN), "stored"

    if attempts:
        mastery, mastery_source = weighted_mastery(attempts), "history"
    else:
        mastery, mastery_source = round(float(get("score") or 0.0), 4), "stored"

    return MasteryState(
        concept=concept,
        status=status,
        status_source=status_source,
        mastery=mastery,
        mastery_source=mastery_source,
        evidence=len(attempts),
        attempts_total=attempts_total,
        algorithm=MASTERY_ALGORITHM_VERSION,
        next_review=get("next_review"),
        interval_days=int(get("interval_days") or 0),
        review_count=int(get("review_count") or 0),
        last_reviewed=get("last_reviewed"),
        updated_at=str(get("updated_at") or ""),
    )


def mastery_state(store: LearningStore, concept: str) -> MasteryState:
    """读取一个概念的掌握度契约。没有记录时返回 unseen。

    稳健性：如果只有证据、没有聚合行（写入在两步之间失败），仍然从证据推导，
    不因为少了一行聚合就把“做过题”误报成“从未接触”。
    """
    name = str(concept or "")
    if not name:
        return unseen_state("")
    record = store.get_mastery(name)
    if record is None:
        if not store.count_mastery_attempts(name):
            return unseen_state(name)
        record = {"concept": name}
    return state_from_row(store, record)


def mastery_states(
    store: LearningStore,
    *,
    status: str | None = None,
    limit: int | None = None,
) -> list[MasteryState]:
    """列出掌握度，按推导值从弱到强排序（最该推进的在前）。

    ``status`` 过滤用的是**推导出来的**状态，不是库里那份历史快照。
    整表只查三次库：聚合行、每概念最近 5 条证据、每概念证据统计。
    """
    rows = store.list_mastery(limit=_LIST_CAP)
    attempts_map = store.recent_attempts_by_concept(WINDOW)
    stats_map = store.mastery_attempt_stats()
    states = [
        state_from_row(
            store,
            row,
            attempts=attempts_map.get(row.concept, []),
            stats=stats_map.get(row.concept, {}),
        )
        for row in rows
    ]
    # 有证据但没有聚合行的概念也要出现（否则列表与单读会不一致）。
    known = {row.concept for row in rows}
    states.extend(
        state_from_row(
            store,
            {"concept": concept},
            attempts=attempts,
            stats=stats_map.get(concept, {}),
        )
        for concept, attempts in attempts_map.items()
        if concept not in known
    )
    if status:
        states = [item for item in states if item.status == status]
    states.sort(key=lambda item: (item.mastery, item.concept))
    if limit is not None:
        states = states[: max(0, int(limit))]
    return states


def status_counts(store: LearningStore) -> dict[str, int]:
    """按推导状态统计。未出现过的状态不返回（与旧 count_by_status 一致）。"""
    counts: dict[str, int] = {}
    for item in mastery_states(store):
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts
