"""检索降级的原因与下一步（W2 降级可见性）。

为什么要有这个模块：向量腿不可用时，系统只把它**记进日志**，对外只有
`retrieval_mode=fts_only`。用户看到「检索不到」，却分不清是后端没起来、
索引是别的模型建的、还是压根还没建索引 —— 三种原因的下一步完全不同。

设计取舍：
- 纯函数：输入是「探活结果 + 已记录的签名信息 + 索引里有几份向量」，输出四段
  `code / title / detail / action`，可直接进 JSON 给界面；
- **不猜**：信息不足时返回 `unknown`，仍然给一个可行动的建议；
- 事实照抄：签名不匹配时把 `mismatch_reason` 的原文带进 detail，不转述成模糊说法。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

#: 语义检索可用。
OK = "ok"
#: 索引里的向量不是当前配置的模型产生的 —— 混用会比「没有语义检索」更糟，所以停用。
SIGNATURE_MISMATCH = "embedding_signature_mismatch"
#: 配了 embedding 后端，但探活失败（服务没起、密钥失效、网络不通）。
PROVIDER_UNAVAILABLE = "embedding_provider_unavailable"
#: 压根没有可用的 embedding 后端（例如 embedding_backend: local，或 openai_compat 缺 key）。
NOT_CONFIGURED = "embedding_not_configured"
#: 后端有响应，但返回了空向量（兼容 API 返回 {"embedding": []} 这类）。
RETURNED_NOTHING = "embedding_returned_nothing"
#: 还没建过向量（0 份资料完成向量化）。
NO_VECTORS = "no_vectors_indexed"
#: 本地向量库被另一个进程占用（本地 Qdrant 是单进程存储）。
VECTOR_STORE_LOCKED = "vector_store_locked"
#: 向量库/嵌入调用报了别的错。
VECTOR_STORE_ERROR = "vector_store_error"
#: 信息不足，不猜。
UNKNOWN = "unknown"


#: 进用户可见载荷前的脱敏规则（审查 F2）。只做模式化遮蔽：
#: 保留下文里有用的部分（状态码、错误消息），把长得像密钥的片段换成 ***。
#: 正则里用 \x22 表示引号，避免这个文件本身被引号形态绊住。
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}"), "sk-***"),
    (re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 ***"),
    (re.compile(r"(?i)((?:authorization|api[_-]?key|x-api-key)\x22?\s*[:=]\s*\x22?)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    (re.compile(r"(?i)((?:secret|token|password|passwd|access[_-]?key)\s*[:=]\s*\x22?)[A-Za-z0-9._\-]{8,}"), r"\1***"),
)


def redact_secrets(text: str) -> str:
    # 遮蔽文本里长得像密钥的片段；普通文本原样返回。
    cleaned = str(text or "")
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


@dataclass(frozen=True)
class SemanticStatus:
    """给人和给界面看的一段状态：结论 + 事实 + 下一步。"""

    code: str
    title: str
    detail: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def _backend(detail_parts: list[str], provider: str, model: str, dim: int | None) -> None:
    if provider or model:
        name = " / ".join(part for part in (provider, model) if part)
        if dim:
            name += f"（dim {dim}）"
        detail_parts.append(f"当前配置的 embedding 后端：{name}。")


def build_semantic_status(**kwargs) -> SemanticStatus:
    # 对外唯一出口：先按事实构造，再统一脱敏（审查 F2：原始报错会进浏览器与模型上下文）。
    return _redact_status(_build_semantic_status(**kwargs))


def _redact_status(status: SemanticStatus) -> SemanticStatus:
    return SemanticStatus(
        code=status.code,
        title=redact_secrets(status.title),
        detail=redact_secrets(status.detail),
        action=redact_secrets(status.action),
    )


def _build_semantic_status(
    *,
    available: bool,
    provider: str = "",
    model: str = "",
    dim: int | None = None,
    signature_mismatch: str = "",
    indexed_documents: int | None = 0,
    vector_error: str = "",
    vector_error_detail: str = "",
    provider_reason: str = "",
) -> SemanticStatus:
    """把「可用与否 + 已知事实」翻成结论 / 事实 / 下一步。"""
    provider = str(provider or "")
    model = str(model or "")

    if available:
        return SemanticStatus(
            code=OK,
            title="语义检索可用",
            detail="向量腿已启用：检索会在关键词之外再用向量召回。",
            action="",
        )

    if signature_mismatch:
        details = [
            "索引里的向量不是当前配置的模型产生的，混用会产生「看起来像语义检索、其实是错的」结果，"
            "所以已停用向量腿。",
            f"签名检查的结论（原文）：{signature_mismatch}",
        ]
        _backend(details, provider, model, dim)
        return SemanticStatus(
            code=SIGNATURE_MISMATCH,
            title="当前是纯文本检索（向量腿已停用：索引与当前模型不一致）",
            detail="".join(details),
            action="把 embedding 配置换回产生这批向量的那个模型，或重建索引（重新同步资料）。",
        )

    # 向量腿自己报了种类 —— 比"探活失败"这类推断准确得多，优先用它。
    if vector_error == VECTOR_STORE_LOCKED:
        details = [
            "本地向量库（Qdrant 目录）正被「另一个进程」占用：本地存储同一时刻只能被一个进程打开。",
        ]
        if vector_error_detail:
            details.append(f"原始报错：{vector_error_detail}")
        details.append(f"（索引里有 {int(indexed_documents or 0)} 份向量，数据是好的。）")
        return SemanticStatus(
            code=VECTOR_STORE_LOCKED,
            title="当前是纯文本检索（向量库被另一个进程占用）",
            detail="".join(details),
            action="关掉另一个占用该知识库的进程（例如另开的服务或脚本），再重试；应用自身的检索不受影响。",
        )

    # 「后端有响应但返回空向量」与「探活失败」是两件事：别让前者背后者的文案。
    if vector_error == RETURNED_NOTHING:
        details = [
            f"embedding 后端有响应，但「返回了空向量」（索引里有 {int(indexed_documents or 0)} 份向量）。",
            "这通常意味着该兼容 API 的响应格式与预期不符（例如 embedding 字段为空数组）。",
        ]
        _backend(details, provider, model, dim)
        if vector_error_detail:
            details.append(f"原始信息：{vector_error_detail}")
        return SemanticStatus(
            code=RETURNED_NOTHING,
            title="当前是纯文本检索（embedding 返回了空向量）",
            detail="".join(details),
            action="检查该 provider 的返回格式/模型名是否被服务端支持，或在「设置 → 模型」换一个可用的 embedding provider。",
        )

    # provider 探活失败 ≠ 没配后端：先看后端是不是那个"不可用"占位实现。
    if vector_error == PROVIDER_UNAVAILABLE or (not vector_error and provider):
        configured = bool(provider) and provider != "unavailable"
        if not configured:
            details = ["没有可用的 embedding 后端（当前 provider 是占位实现，未真正配置）。"]
            if provider_reason:
                details.append(f"provider 自己给的原因：{provider_reason}")
            if provider and provider != "unavailable":
                details.append(f"当前 provider 名称：{provider}。")
            return SemanticStatus(
                code=NOT_CONFIGURED,
                title="当前是纯文本检索（还没有配置 embedding 后端）",
                detail="".join(details),
                action="在「设置 → 模型」配置一个 embedding provider（例如 SiliconFlow / 智谱 / OpenAI 兼容接口），配置好后重新同步资料即可建立向量。",
            )

    if vector_error == PROVIDER_UNAVAILABLE:
        details = [
            f"探活失败 —— 配置了 embedding 后端（{provider or '未知'}），但它现在没有响应",
            f"（索引里有 {int(indexed_documents or 0)} 份向量）。",
        ]
        _backend(details, provider, model, dim)
        return SemanticStatus(
            code=PROVIDER_UNAVAILABLE,
            title="当前是纯文本检索（embedding 后端探活失败）",
            detail="".join(details),
            action=("启动该服务（例如本地 Ollama）、检查它的地址/密钥，或在「设置 → 模型」换一个可用的 "
                    "embedding provider；修好后重新同步资料即可补上向量。"),
        )

    if vector_error == VECTOR_STORE_ERROR:
        details = ["向量腿在查询时报错，已退回纯文本检索。"]
        if vector_error_detail:
            details.append(f"原始报错：{vector_error_detail}")
        return SemanticStatus(
            code=VECTOR_STORE_ERROR,
            title="当前是纯文本检索（向量查询出错）",
            detail="".join(details),
            action="按上面的原始报错排查向量库；也可以先重新同步资料重建向量。",
        )

    if indexed_documents is None:
        details = ["拿不到足够信息判断向量腿为什么不可用。"] if not provider else []
        _backend(details, provider, model, dim)
        return SemanticStatus(
            code=UNKNOWN,
            title="当前是纯文本检索（原因未知）",
            detail="".join(details) or "拿不到足够信息判断向量腿为什么不可用。",
            action="在「设置 → 模型」确认 embedding 配置，然后重新同步资料并查看同步报错。",
        )

    if int(indexed_documents) <= 0:
        details = ["索引里还没有任何完成向量化的资料（0 份）。"]
        _backend(details, provider, model, dim)
        return SemanticStatus(
            code=NO_VECTORS,
            title="当前是纯文本检索（还没有向量索引）",
            detail="".join(details),
            action="运行一次资料同步建立向量；若同步里向量这一腿失败，汇总里会给出原因。",
        )

    # 走到这里说明「向量腿不可用」但没有任何一条**被验证过**的原因 ——
    # 审查（Codex P1）指出旧实现把这里写成「探活失败」，而这条兜底在
    # 「没配后端」「返回空向量」等路径上都是错的事实。现在只承认不知道。
    details = []
    _backend(details, provider, model, dim)
    if indexed_documents:
        details.append(f"索引里有 {int(indexed_documents)} 份向量，但没有拿到具体的不可用原因。")
    return SemanticStatus(
        code=UNKNOWN,
        title="当前是纯文本检索（原因未知）",
        detail="".join(details) or "拿不到足够信息判断向量腿为什么不可用。",
        action="在「设置 → 模型」确认 embedding 配置，然后重新同步资料并查看同步汇总里的原因。",
    )
