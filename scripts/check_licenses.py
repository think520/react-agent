"""License gate — fail when a GPL/AGPL dependency is installed.

P5G.0 发布合规：PyMuPDF（AGPL）移除后，任何 GPL / AGPL 依赖都不得
重新进入运行时。本脚本扫描当前环境（`importlib.metadata`）并按许可证
元数据拦截，可本地运行：

    .venv\\Scripts\\python.exe scripts/check_licenses.py

也作为 GitHub Actions 工作流的一部分在干净环境执行。
"""

from __future__ import annotations

import sys

from importlib import metadata

# Windows 控制台默认 GBK 编码，打印中文检查结果会 UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 精确匹配或子串命中都算违规（如 "GPL-3.0-or-later"、"AGPL-3.0"）
_FORBIDDEN = ("gpl", "agpl")
# 这些包由我们自己的依赖引入且已知许可宽松，元数据缺失时不误报
_KNOWN_PERMISSIVE = {
    "pypdf", "python-docx", "python-pptx", "fastapi", "uvicorn", "httpx",
    "pydantic", "starlette", "python-dotenv", "PyYAML", "rich",
    "prompt_toolkit", "mcp", "qdrant-client", "python-multipart",
}


def _license_text(meta: metadata.PackageMetadata) -> str:
    license_expression = meta.get("License-Expression")
    if license_expression:
        return license_expression
    license_field = meta.get("License")
    if license_field:
        return license_field
    classifier = [c for c in meta.get_all("Classifier") or [] if c.startswith("License")]
    return "; ".join(classifier)


def main() -> int:
    violations: list[tuple[str, str]] = []
    unknown: list[tuple[str, str]] = []

    for dist in metadata.distributions():
        name = (dist.metadata.get("Name") or "").lower()
        if not name or name.startswith("bobodan"):
            continue
        license_text = _license_text(dist.metadata).lower()
        if any(token in license_text for token in _FORBIDDEN):
            violations.append((name, _license_text(dist.metadata)))
        elif not license_text and name not in _KNOWN_PERMISSIVE:
            unknown.append((name, "no license metadata"))

    if unknown:
        print("未知许可证（需要人工确认）：")
        for name, reason in sorted(unknown):
            print(f"  - {name}: {reason}")

    if violations:
        print("发现 GPL/AGPL 依赖，禁止进入发布：", file=sys.stderr)
        for name, license_text in sorted(violations):
            print(f"  - {name}: {license_text}", file=sys.stderr)
        return 1

    print(f"许可证检查通过：未发现 GPL/AGPL 依赖（{len(unknown)} 个未知需人工确认）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
