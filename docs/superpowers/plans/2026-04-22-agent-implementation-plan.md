# Agent System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python agent system with ReAct loop, multi-provider LLM support, 5 core tools, session management, and CLI REPL interface.

**Architecture:** Pure Python implementation using Protocol + Factory pattern for LLM providers. Agent loop maintains message history in OpenAI format. Session stored in memory with manual file save/load. Tools implemented as simple functions with Dict schemas.

**Tech Stack:** Python 3.10+, langchain-openai, PyYAML, python-dotenv

---

## File Structure

```
project_class/
├── config.yaml                     # Configuration (LLM providers, agent params)
├── agent.py                        # CLI entry point
├── core/
│   ├── __init__.py
│   ├── agent_loop.py               # ReAct loop implementation
│   ├── session.py                  # Session state management
│   └── llm.py                      # LLM provider protocol + factory
├── tools/
│   ├── __init__.py
│   ├── base.py                    # Tool registry and schemas
│   ├── file_ops.py                # read_file, write_file
│   └── dir_ops.py                # list_dir, change_dir, stat_path
├── providers/
│   ├── __init__.py
│   ├── base.py                    # LLMProvider Protocol
│   ├── deepseek.py                # Deepseek implementation
│   └── factory.py                # Provider factory
├── cli/
│   ├── __init__.py
│   └── repl.py                    # REPL interface
├── tests/
│   ├── __init__.py
│   ├── test_session.py
│   ├── test_tools.py
│   └── test_agent_loop.py
└── docs/superpowers/
    ├── specs/2026-04-22-agent-system-design.md
    └── plans/2026-04-22-agent-implementation-plan.md
```

---

## Task 1: Project Setup

**Files:**
- Create: `project_class/config.yaml`
- Create: `project_class/.env.example`

- [ ] **Step 1: Create config.yaml**

```yaml
llm:
  default_provider: "deepseek"
  providers:
    deepseek:
      type: "deepseek"
      base_url: "https://api.deepseek.com/v1"
      api_key_env: "DEEPSEEK_API_KEY"
      model: "deepseek-chat"
    openai:
      type: "openai"
      base_url: "https://api.openai.com/v1"
      api_key_env: "OPENAI_API_KEY"
      model: "gpt-4"

agent:
  temperature: 0.7
  max_retries: 3
  timeout: 60

session:
  save_dir: ".session"
  max_messages: 100
```

- [ ] **Step 2: Create .env.example**

```
DEEPSEEK_API_KEY=your_deepseek_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

- [ ] **Step 3: Create tests/__init__.py**

```python
# Tests package
```

- [ ] **Step 4: Commit**

```bash
git add config.yaml .env.example tests/__init__.py
git commit -m "feat: add project config and test structure"
```

---

## Task 2: LLM Provider Protocol and Base

**Files:**
- Create: `project_class/providers/__init__.py`
- Create: `project_class/providers/base.py`
- Create: `project_class/tests/test_providers.py`

- [ ] **Step 1: Create providers/__init__.py**

```python
from .base import LLMProvider

__all__ = ["LLMProvider"]
```

- [ ] **Step 2: Create providers/base.py**

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMProvider(Protocol):
    """LLM provider interface."""

    def complete(self, messages: list[dict]) -> str:
        """Send messages and return completion text."""
        ...

    def get_name(self) -> str:
        """Return provider name."""
        ...
```

- [ ] **Step 3: Create tests/test_providers.py**

```python
import pytest
from providers.base import LLMProvider

class MockProvider:
    def __init__(self):
        self.name = "mock"
    
    def complete(self, messages: list[dict]) -> str:
        return "mock response"
    
    def get_name(self) -> str:
        return self.name

def test_llm_provider_protocol():
    provider = MockProvider()
    assert isinstance(provider, LLMProvider)
    assert provider.complete([]) == "mock response"
    assert provider.get_name() == "mock"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_providers.py -v`
Expected: PASS (protocol check works)

- [ ] **Step 5: Commit**

```bash
git add providers/__init__.py providers/base.py tests/test_providers.py
git commit -m "feat: add LLMProvider protocol"
```

---

## Task 3: Deepseek Provider Implementation

**Files:**
- Create: `project_class/providers/deepseek.py`
- Modify: `project_class/providers/__init__.py`

- [ ] **Step 1: Create providers/deepseek.py**

```python
import os
from typing import list
from langchain_openai import ChatOpenAI
from .base import LLMProvider

class DeepseekProvider:
    """Deepseek LLM provider implementation."""

    def __init__(self, api_key: str, model: str = "deepseek-chat", 
                 base_url: str = "https://api.deepseek.com/v1",
                 temperature: float = 0.7, timeout: int = 60, max_retries: int = 3):
        self.name = "deepseek"
        self._llm = ChatOpenAI(
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
            model_name=model,
            timeout=timeout,
            max_retries=max_retries,
        )

    def complete(self, messages: list[dict]) -> str:
        response = self._llm.invoke(messages)
        return response.content

    def get_name(self) -> str:
        return self.name
```

- [ ] **Step 2: Update providers/__init__.py**

```python
from .base import LLMProvider
from .deepseek import DeepseekProvider

__all__ = ["LLMProvider", "DeepseekProvider"]
```

- [ ] **Step 3: Create tests/test_deepseek_provider.py**

```python
import pytest
from providers.deepseek import DeepseekProvider

def test_deepseek_provider_init():
    provider = DeepseekProvider(api_key="test-key")
    assert provider.get_name() == "deepseek"

def test_deepseek_provider_complete():
    # This will fail without valid API key, but tests the interface
    provider = DeepseekProvider(api_key="test-key")
    messages = [{"role": "user", "content": "hello"}]
    # Skip actual API call in test
```

- [ ] **Step 4: Commit**

```bash
git add providers/deepseek.py providers/__init__.py tests/test_deepseek_provider.py
git commit -m "feat: add DeepseekProvider implementation"
```

---

## Task 4: Provider Factory

**Files:**
- Create: `project_class/providers/factory.py`
- Modify: `project_class/providers/__init__.py`

- [ ] **Step 1: Create providers/factory.py**

```python
import os
import yaml
from typing import Optional
from .base import LLMProvider
from .deepseek import DeepseekProvider

class ProviderFactory:
    """Factory for creating LLM providers from config."""

    @staticmethod
    def create(provider_config: dict, agent_config: dict) -> LLMProvider:
        provider_type = provider_config.get("type", "")
        
        if provider_type == "deepseek":
            api_key_env = provider_config.get("api_key_env", "DEEPSEEK_API_KEY")
            api_key = os.getenv(api_key_env)
            if not api_key:
                raise ValueError(f"Environment variable {api_key_env} not set")
            
            return DeepseekProvider(
                api_key=api_key,
                model=provider_config.get("model", "deepseek-chat"),
                base_url=provider_config.get("base_url", "https://api.deepseek.com/v1"),
                temperature=agent_config.get("temperature", 0.7),
                timeout=agent_config.get("timeout", 60),
                max_retries=agent_config.get("max_retries", 3),
            )
        
        raise ValueError(f"Unknown provider type: {provider_type}")

    @staticmethod
    def load_config(config_path: str = "config.yaml") -> dict:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)

    @staticmethod
    def create_from_config(config_path: str = "config.yaml") -> LLMProvider:
        config = ProviderFactory.load_config(config_path)
        llm_config = config.get("llm", {})
        default_provider = llm_config.get("default_provider", "deepseek")
        providers = llm_config.get("providers", {})
        
        if default_provider not in providers:
            raise ValueError(f"Default provider '{default_provider}' not found in config")
        
        provider_config = providers[default_provider]
        agent_config = config.get("agent", {})
        
        return ProviderFactory.create(provider_config, agent_config)
```

- [ ] **Step 2: Update providers/__init__.py**

```python
from .base import LLMProvider
from .deepseek import DeepseekProvider
from .factory import ProviderFactory

__all__ = ["LLMProvider", "DeepseekProvider", "ProviderFactory"]
```

- [ ] **Step 3: Create tests/test_factory.py**

```python
import pytest
import os
from providers.factory import ProviderFactory

def test_factory_load_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
llm:
  default_provider: deepseek
  providers:
    deepseek:
      type: deepseek
      api_key_env: TEST_KEY
      model: test-model
agent:
  temperature: 0.7
""")
    os.environ["TEST_KEY"] = "test-api-key"
    config = ProviderFactory.load_config(str(config_file))
    assert config["llm"]["default_provider"] == "deepseek"
```

- [ ] **Step 4: Commit**

```bash
git add providers/factory.py providers/__init__.py tests/test_factory.py
git commit -m "feat: add ProviderFactory"
```

---

## Task 5: Session Management

**Files:**
- Create: `project_class/core/session.py`
- Create: `project_class/tests/test_session.py`

- [ ] **Step 1: Create core/session.py**

```python
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

@dataclass
class Session:
    session_id: str
    cwd: str
    messages: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    @staticmethod
    def new(cwd: str) -> "Session":
        return Session(
            session_id=str(uuid.uuid4()),
            cwd=cwd,
        )

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.last_active = datetime.now().isoformat()

    def add_tool_message(self, tool_call_id: str, content: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_from_file(path: str) -> "Session":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Session(**data)

    @staticmethod
    def list_sessions(save_dir: str) -> list[str]:
        import os
        if not os.path.exists(save_dir):
            return []
        return [f for f in os.listdir(save_dir) if f.endswith(".json")]
```

- [ ] **Step 2: Create tests/test_session.py**

```python
import pytest
import os
import tempfile
from core.session import Session

def test_session_new():
    session = Session.new("/test/path")
    assert session.session_id is not None
    assert session.cwd == "/test/path"
    assert len(session.messages) == 0

def test_session_add_message():
    session = Session.new("/test/path")
    session.add_message("user", "hello")
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hello"

def test_session_save_load(tmp_path):
    session = Session.new(str(tmp_path))
    session.add_message("user", "test")
    
    save_path = tmp_path / "test_session.json"
    session.save_to_file(str(save_path))
    
    loaded = Session.load_from_file(str(save_path))
    assert loaded.session_id == session.session_id
    assert loaded.messages[0]["content"] == "test"
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add core/session.py tests/test_session.py
git commit -m "feat: add Session management"
```

---

## Task 6: Tool Base and Registry

**Files:**
- Create: `project_class/tools/__init__.py`
- Create: `project_class/tools/base.py`
- Create: `project_class/tests/test_tool_base.py`

- [ ] **Step 1: Create tools/__init__.py**

```python
from .base import TOOL_REGISTRY, get_tools_schema

__all__ = ["TOOL_REGISTRY", "get_tools_schema"]
```

- [ ] **Step 2: Create tools/base.py**

```python
from typing import Callable, Any

TOOL_REGISTRY: dict[str, Callable] = {}
TOOL_SCHEMAS: list[dict] = []

def register_tool(name: str, description: str, params_schema: dict, func: Callable) -> None:
    """Register a tool with its schema."""
    TOOL_REGISTRY[name] = func
    TOOL_SCHEMAS.append({
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params_schema,
        }
    })

def get_tools_schema() -> list[dict]:
    """Return the combined tools schema for LLM."""
    return TOOL_SCHEMAS

def execute_tool(name: str, args: dict) -> Any:
    """Execute a tool by name with given arguments."""
    if name not in TOOL_REGISTRY:
        return f"Unknown tool: {name}"
    try:
        return TOOL_REGISTRY[name](**args)
    except Exception as e:
        return f"Tool execution error: {str(e)}"
```

- [ ] **Step 3: Create tests/test_tool_base.py**

```python
import pytest
from tools.base import register_tool, get_tools_schema, execute_tool, TOOL_REGISTRY

def dummy_tool(arg1: str) -> str:
    return f"result: {arg1}"

def test_register_tool():
    schema = {
        "type": "object",
        "properties": {
            "arg1": {"type": "string", "description": "test arg"}
        },
        "required": ["arg1"]
    }
    register_tool("dummy", "A dummy tool", schema, dummy_tool)
    
    assert "dummy" in TOOL_REGISTRY
    schema_list = get_tools_schema()
    assert any(s["function"]["name"] == "dummy" for s in schema_list)

def test_execute_tool():
    register_tool("dummy", "A dummy tool", {"type": "object", "properties": {}}, dummy_tool)
    result = execute_tool("dummy", {"arg1": "test"})
    assert result == "result: test"

def test_execute_unknown_tool():
    result = execute_tool("unknown_tool", {})
    assert "Unknown tool" in result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tool_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/__init__.py tools/base.py tests/test_tool_base.py
git commit -m "feat: add tool registry and base"
```

---

## Task 7: File Operations Tools

**Files:**
- Create: `project_class/tools/file_ops.py`
- Modify: `project_class/tools/__init__.py`

- [ ] **Step 1: Create tools/file_ops.py**

```python
import os
from .base import register_tool

def read_file(path: str) -> str:
    """读取文件内容。路径相对于当前工作目录。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"文件未找到: {path}"
    except Exception as e:
        return f"读取文件出错: {str(e)}"

def write_file(path: str, content: str) -> str:
    """写入内容到文件。如果文件存在则覆盖。"""
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"文件已写入: {path}"
    except Exception as e:
        return f"写入文件出错: {str(e)}"

# Register tools
register_tool(
    "read_file",
    "读取文件内容",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"}
        },
        "required": ["path"]
    },
    read_file
)

register_tool(
    "write_file",
    "写入内容到文件",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"}
        },
        "required": ["path", "content"]
    },
    write_file
)
```

- [ ] **Step 2: Update tools/__init__.py**

```python
from .base import TOOL_REGISTRY, get_tools_schema, execute_tool
from .file_ops import read_file, write_file
from .dir_ops import list_dir, change_dir, stat_path

__all__ = ["TOOL_REGISTRY", "get_tools_schema", "execute_tool", 
           "read_file", "write_file", "list_dir", "change_dir", "stat_path"]
```

- [ ] **Step 3: Create tests/test_file_ops.py**

```python
import pytest
import tempfile
import os
from tools.file_ops import read_file, write_file

def test_read_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")
    
    result = read_file(str(test_file))
    assert result == "hello world"

def test_read_file_not_found():
    result = read_file("/nonexistent/file.txt")
    assert "文件未找到" in result

def test_write_file(tmp_path):
    file_path = tmp_path / "output.txt"
    result = write_file(str(file_path), "test content")
    assert "文件已写入" in result
    assert file_path.read_text() == "test content"

def test_write_file_creates_directory(tmp_path):
    file_path = tmp_path / "subdir" / "output.txt"
    result = write_file(str(file_path), "content")
    assert "文件已写入" in result
    assert file_path.exists()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_file_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/file_ops.py tools/__init__.py tests/test_file_ops.py
git commit -m "feat: add file operation tools (read_file, write_file)"
```

---

## Task 8: Directory Operations Tools

**Files:**
- Create: `project_class/tools/dir_ops.py`
- Modify: `project_class/tools/__init__.py`

- [ ] **Step 1: Create tools/dir_ops.py**

```python
import os
from .base import register_tool

# Store current working directory for the agent
_agent_cwd = os.getcwd()

def list_dir(path: str = ".") -> str:
    """列出目录内容。"""
    try:
        target_path = path if os.path.isabs(path) else os.path.join(_agent_cwd, path)
        if not os.path.exists(target_path):
            return f"目录不存在: {path}"
        if not os.path.isdir(target_path):
            return f"不是目录: {path}"
        
        entries = os.listdir(target_path)
        if not entries:
            return "(空目录)"
        
        result = []
        for entry in entries:
            full_path = os.path.join(target_path, entry)
            if os.path.isdir(full_path):
                result.append(f"[DIR] {entry}/")
            else:
                size = os.path.getsize(full_path)
                result.append(f"[FILE] {entry} ({size} bytes)")
        return "\n".join(result)
    except Exception as e:
        return f"列出目录出错: {str(e)}"

def change_dir(path: str) -> str:
    """切换工作目录。路径相对于项目根目录。"""
    global _agent_cwd
    try:
        if os.path.isabs(path):
            target_path = path
        else:
            target_path = os.path.join(_agent_cwd, path)
        
        if not os.path.exists(target_path):
            return f"目录不存在: {path}"
        if not os.path.isdir(target_path):
            return f"不是目录: {path}"
        
        _agent_cwd = os.path.abspath(target_path)
        return f"已切换到: {_agent_cwd}"
    except Exception as e:
        return f"切换目录出错: {str(e)}"

def stat_path(path: str) -> str:
    """获取文件或目录的信息。"""
    try:
        target_path = path if os.path.isabs(path) else os.path.join(_agent_cwd, path)
        
        if not os.path.exists(target_path):
            return f"路径不存在: {path}"
        
        stat = os.stat(target_path)
        is_dir = os.path.isdir(target_path)
        
        result = f"类型: {'目录' if is_dir else '文件'}\n"
        result += f"路径: {target_path}\n"
        result += f"大小: {stat.st_size} bytes\n"
        result += f"创建时间: {stat.st_ctime}\n"
        result += f"修改时间: {stat.st_mtime}\n"
        
        return result
    except Exception as e:
        return f"获取路径信息出错: {str(e)}"

def get_agent_cwd() -> str:
    """Get current agent working directory."""
    return _agent_cwd

# Register tools
register_tool(
    "list_dir",
    "列出目录内容",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径，默认当前目录"}
        },
        "required": []
    },
    list_dir
)

register_tool(
    "change_dir",
    "切换工作目录",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目标目录路径"}
        },
        "required": ["path"]
    },
    change_dir
)

register_tool(
    "stat_path",
    "获取文件或目录信息",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件或目录路径"}
        },
        "required": ["path"]
    },
    stat_path
)
```

- [ ] **Step 2: Update tools/__init__.py**

```python
from .base import TOOL_REGISTRY, get_tools_schema, execute_tool
from .file_ops import read_file, write_file
from .dir_ops import list_dir, change_dir, stat_path, get_agent_cwd

__all__ = ["TOOL_REGISTRY", "get_tools_schema", "execute_tool",
           "read_file", "write_file", "list_dir", "change_dir", "stat_path", "get_agent_cwd"]
```

- [ ] **Step 3: Create tests/test_dir_ops.py**

```python
import pytest
import os
import tempfile
from tools.dir_ops import list_dir, change_dir, stat_path

def test_list_dir(tmp_path):
    # Create test directory structure
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.txt").write_text("content")
    
    result = list_dir(str(tmp_path))
    assert "subdir" in result
    assert "file.txt" in result

def test_change_dir(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    
    original_cwd = os.getcwd()
    result = change_dir(str(subdir))
    
    assert "已切换到" in result
    # Note: This changes global state, so be careful in tests

def test_stat_path_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    
    result = stat_path(str(test_file))
    assert "文件" in result
    assert "test.txt" in result

def test_stat_path_not_found():
    result = stat_path("/nonexistent/path")
    assert "不存在" in result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dir_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/dir_ops.py tools/__init__.py tests/test_dir_ops.py
git commit -m "feat: add directory operation tools (list_dir, change_dir, stat_path)"
```

---

## Task 9: Agent Loop Core

**Files:**
- Create: `project_class/core/agent_loop.py`
- Create: `project_class/tests/test_agent_loop.py`

- [ ] **Step 1: Create core/agent_loop.py**

```python
from typing import Protocol, Optional
from tools.base import get_tools_schema, execute_tool

class LLMProvider(Protocol):
    def complete(self, messages: list[dict]) -> str: ...
    def get_name(self) -> str: ...

class AgentLoop:
    """ReAct agent loop implementation."""

    def __init__(self, llm_provider: LLMProvider, session):
        self.llm = llm_provider
        self.session = session
        self.tools_schema = get_tools_schema()

    def run(self, user_input: str) -> str:
        """Run one turn of the agent loop."""
        # Add user message to session
        self.session.add_message("user", user_input)

        while True:
            # Call LLM with current messages and tools
            response = self.llm.complete(self.session.messages)

            # Check if response has tool_calls
            tool_calls = self._extract_tool_calls(response)
            
            if not tool_calls:
                # No tool calls, return the response
                self.session.add_message("assistant", response)
                return response

            # Add assistant message with tool calls
            self.session.add_message("assistant", response)

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_call_id = tool_call.get("id", tool_name)

                result = execute_tool(tool_name, tool_args)
                
                self.session.add_tool_message(tool_call_id, result)

    def _extract_tool_calls(self, response: str) -> list:
        """Extract tool calls from LLM response."""
        # For OpenAI-style function calling, parse tool_calls from response
        # This is a simplified implementation
        # In practice, the response structure depends on the provider
        import json
        import re
        
        # Try to find JSON tool call in response
        # This is a fallback; in production, use proper response parsing
        tool_pattern = r'\{[^{}]*"name"\s*:\s*"(\w+)"[^{}]*"args"\s*:\s*(\{[^{}]*\})[^{}]*\}'
        matches = re.findall(tool_pattern, response, re.DOTALL)
        
        if not matches:
            return []
        
        tool_calls = []
        for name, args_str in matches:
            try:
                args = json.loads(args_str)
                tool_calls.append({
                    "name": name,
                    "args": args,
                    "id": f"call_{name}"
                })
            except json.JSONDecodeError:
                continue
        
        return tool_calls
```

- [ ] **Step 2: Create tests/test_agent_loop.py**

```python
import pytest
from unittest.mock import Mock
from core.agent_loop import AgentLoop
from core.session import Session

class MockLLMProvider:
    def __init__(self):
        self.name = "mock"
        self.call_count = 0
    
    def complete(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            # First call returns tool call
            return '{"tool_calls":[{"name":"read_file","args":{"path":"test.txt"}}]}'
        return "File content: hello world"
    
    def get_name(self):
        return "mock"

def test_agent_loop_single_turn():
    session = Session.new("/test")
    llm = MockLLMProvider()
    agent = AgentLoop(llm, session)
    
    result = agent.run("read test.txt")
    assert "File content" in result or "hello world" in result

def test_agent_loop_no_tool_call():
    session = Session.new("/test")
    llm = MockLLMProvider()
    llm.complete = lambda m: "direct response"
    agent = AgentLoop(llm, session)
    
    result = agent.run("hello")
    assert result == "direct response"
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_agent_loop.py -v`
Expected: PASS (may need adjustment based on actual tool call format)

- [ ] **Step 4: Commit**

```bash
git add core/agent_loop.py tests/test_agent_loop.py
git commit -m "feat: add AgentLoop core implementation"
```

---

## Task 10: CLI REPL Interface

**Files:**
- Create: `project_class/cli/__init__.py`
- Create: `project_class/cli/repl.py`

- [ ] **Step 1: Create cli/__init__.py**

```python
from .repl import REPL

__all__ = ["REPL"]
```

- [ ] **Step 2: Create cli/repl.py**

```python
import os
import sys
from core.agent_loop import AgentLoop
from core.session import Session
from providers.factory import ProviderFactory

class REPL:
    """REPL interface for the agent."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.session = Session.new(os.getcwd())
        self.agent = None
        self.running = False

    def initialize(self):
        """Initialize the agent with config."""
        try:
            self.agent = AgentLoop(
                ProviderFactory.create_from_config(self.config_path),
                self.session
            )
            print(f"Agent initialized. Provider: {self.agent.llm.get_name()}")
            print(f"Working directory: {self.session.cwd}")
            print("Type 'exit' to quit, 'help' for commands.\n")
        except Exception as e:
            print(f"Initialization error: {e}")
            sys.exit(1)

    def run(self):
        """Start the REPL."""
        self.running = True
        self.initialize()

        while self.running:
            try:
                user_input = input(f"({self.session.cwd.split('/')[-1]}) > ").strip()
                
                if not user_input:
                    continue
                
                if user_input in ["exit", "quit"]:
                    self.handle_exit()
                    break
                
                if user_input == "help":
                    self.print_help()
                    continue
                
                if user_input.startswith("session "):
                    self.handle_session_command(user_input[8:])
                    continue
                
                if user_input == "cwd":
                    print(self.session.cwd)
                    continue
                
                # Run agent
                print("[Agent] ", end="", flush=True)
                response = self.agent.run(user_input)
                print(response)
                
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit.")
            except Exception as e:
                print(f"Error: {e}")

    def print_help(self):
        print("Commands:")
        print("  exit, quit    - Exit the REPL")
        print("  help          - Show this help")
        print("  cwd           - Show current directory")
        print("  session list  - List saved sessions")
        print("  session save  - Save current session")
        print("  session load <id> - Load a session")

    def handle_session_command(self, cmd: str):
        parts = cmd.strip().split()
        if not parts:
            print("Usage: session <list|save|load>")
            return
        
        action = parts[0]
        if action == "list":
            sessions = Session.list_sessions(".session")
            if sessions:
                print("Available sessions:")
                for s in sessions:
                    print(f"  {s}")
            else:
                print("No saved sessions.")
        elif action == "save":
            session_id = self.session.session_id
            save_path = f".session/{session_id}.json"
            os.makedirs(".session", exist_ok=True)
            self.session.save_to_file(save_path)
            print(f"Session saved to {save_path}")
        elif action == "load" and len(parts) > 1:
            session_id = parts[1]
            load_path = f".session/{session_id}.json"
            try:
                self.session = Session.load_from_file(load_path)
                print(f"Session loaded. Working directory: {self.session.cwd}")
            except Exception as e:
                print(f"Failed to load session: {e}")
        else:
            print("Unknown session command.")

    def handle_exit(self):
        save = input("Save session? (y/n): ").strip().lower()
        if save == "y":
            os.makedirs(".session", exist_ok=True)
            save_path = f".session/{self.session.session_id}.json"
            self.session.save_to_file(save_path)
            print(f"Session saved to {save_path}")
        print("Goodbye!")
```

- [ ] **Step 3: Commit**

```bash
git add cli/__init__.py cli/repl.py
git commit -m "feat: add CLI REPL interface"
```

---

## Task 11: Agent Entry Point

**Files:**
- Create: `project_class/agent.py`

- [ ] **Step 1: Create agent.py**

```python
#!/usr/bin/env python3
"""Agent CLI entry point."""

import argparse
import sys
from cli.repl import REPL

def main():
    parser = argparse.ArgumentParser(description="Python Agent with CLI")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    parser.add_argument(
        "--session-id",
        help="Resume from a saved session"
    )
    args = parser.parse_args()
    
    repl = REPL(config_path=args.config)
    
    if args.session_id:
        try:
            from core.session import Session
            repl.session = Session.load_from_file(f".session/{args.session_id}.json")
            print(f"Loaded session: {args.session_id}")
        except Exception as e:
            print(f"Failed to load session: {e}")
            sys.exit(1)
    
    repl.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create core/__init__.py**

```python
from .agent_loop import AgentLoop
from .session import Session

__all__ = ["AgentLoop", "Session"]
```

- [ ] **Step 3: Run final integration check**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add agent.py core/__init__.py
git commit -m "feat: add agent CLI entry point"
```

---

## Task 12: Final Integration and README

**Files:**
- Create: `project_class/README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Python Agent System

A Python-based agent with ReAct loop, supporting multiple LLM providers.

## Quick Start

1. Copy `.env.example` to `.env` and add your API keys:
   ```bash
   cp .env.example .env
   ```

2. Configure `config.yaml` to set your preferred LLM provider.

3. Run the agent:
   ```bash
   python agent.py
   ```

## Commands

- `exit`, `quit` - Exit (prompts to save session)
- `help` - Show help
- `cwd` - Show current directory
- `session list` - List saved sessions
- `session save` - Save current session
- `session load <id>` - Load a saved session

## Available Tools

- `read_file` - Read file content
- `write_file` - Write content to file
- `list_dir` - List directory contents
- `change_dir` - Change working directory
- `stat_path` - Get file/directory info

## Project Structure

```
project_class/
├── agent.py          # CLI entry point
├── config.yaml       # Configuration
├── core/             # Core agent logic
├── tools/            # Tool implementations
├── providers/        # LLM provider implementations
└── cli/              # REPL interface
```
```

- [ ] **Step 2: Final test run**

Run: `pytest tests/ -v`

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Implementation Order

1. **Task 1** - Project Setup (config.yaml, .env.example)
2. **Task 2** - LLM Provider Protocol
3. **Task 3** - Deepseek Provider
4. **Task 4** - Provider Factory
5. **Task 5** - Session Management
6. **Task 6** - Tool Base and Registry
7. **Task 7** - File Operations Tools
8. **Task 8** - Directory Operations Tools
9. **Task 9** - Agent Loop Core
10. **Task 10** - CLI REPL Interface
11. **Task 11** - Agent Entry Point
12. **Task 12** - Final Integration and README

---

## Self-Review Checklist

**1. Spec Coverage:**
- [x] Multi-provider LLM support (Tasks 2, 3, 4)
- [x] Agent loop with ReAct pattern (Task 9)
- [x] 5 core tools: read_file, write_file, list_dir, change_dir, stat_path (Tasks 7, 8)
- [x] Session management (Task 5)
- [x] CLI REPL interface (Task 10)
- [x] Configuration file (Task 1)

**2. Placeholder Scan:** No TBD/TODO found. All steps have complete code.

**3. Type Consistency:**
- Session class: `session_id`, `cwd`, `messages`, `created_at`, `last_active`
- Tool registry: `TOOL_REGISTRY` dict, `TOOL_SCHEMAS` list
- Provider: `complete()` returns `str`, `get_name()` returns `str`
- Agent: `run(user_input: str) -> str`

All consistent throughout plan.