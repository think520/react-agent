from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """Parsed tool call from an LLM response."""
    id: str
    name: str
    arguments: str  # JSON string

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolCallDelta:
    """Incremental tool call data from a streaming response."""
    index: int = 0
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class LLMStreamChunk:
    """Incremental LLM response chunk."""
    content_delta: str = ""
    tool_call_deltas: list[ToolCallDelta] = field(default_factory=list)
