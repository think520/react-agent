# Round 2 Review: HTTP Tool 后的新一轮迭代建议

评审日期：2026-05-09
修复日期：2026-05-10
当前测试结果：`108 passed`
新增重点：项目已加入 `http_request` 工具，上一轮评审里的核心结构问题基本已经完成修复。

这一轮不再重复上一份文档里的旧问题，只记录当前版本继续重度使用时最值得优先处理的 4 个点。

---

## 修复状态总览

| # | 问题 | 状态 | 测试 |
|---|------|------|------|
| 1 | workspace_root 与 cwd 分离 | ✅ 已修复 | +3 session, +1 dir_ops, +1 agent_loop |
| 2 | HTTP SSRF 防护 | ✅ 已修复 | +8 http_req (SSRF 系列) |
| 3 | REPL 超时事务化 | ✅ 已修复 | +2 repl |
| 4 | HTTP 响应按 bytes/content-type 处理 | ✅ 已修复（随 #2 一并完成） | +3 http_req |

变更文件：
- `core/session.py` — 增加 `workspace_root` 字段，`new()` 初始化，`load_from_file()` 兼容旧格式
- `tools/base.py` — `execute_tool()` 注入 `workspace=session.workspace_root`
- `tools/http_req.py` — SSRF 防护（DNS 解析后检查 IP）、手动 redirect 处理、二进制 content-type 检测、bytes 截断、headers 摘要
- `cli/repl.py` — `run_agent()` 使用 session 深拷贝，成功才替换主 session；启动/status 显示 workspace_root
- `tests/test_session.py` — workspace_root 相关 3 个测试
- `tests/test_dir_ops.py` — workspace 边界测试
- `tests/test_agent_loop.py` — workspace_root 不变测试
- `tests/test_http_req.py` — 重写，22 个测试（含 SSRF、二进制、bytes 截断）
- `tests/test_repl.py` — 超时不改 session、成功提交 session 2 个测试

## 1. 固定 workspace root，避免 cwd 越切越窄

当前 `execute_tool()` 给工具注入参数时使用：

```python
call_args.setdefault("workspace", session.cwd)
```

这会导致 workspace root 等于“当前工作目录”，而不是“项目根目录”。结果是：

1. 启动时在项目根目录，可以访问整个项目。
2. 执行 `change_dir("core")` 后，`session.cwd` 变成 `project/core`。
3. 下一次工具调用时，workspace 也变成 `project/core`。
4. 此时 `change_dir("..")` 或读取项目根目录文件可能会被拒绝，因为它们已经在新的 workspace 外。

这不是测试容易暴露的问题，但真实 REPL 使用时很容易遇到。

建议修改：

- 给 `Session` 增加 `workspace_root` 字段，创建 session 时固定为启动目录。
- `cwd` 表示当前目录，`workspace_root` 表示安全边界，二者不要混用。
- `execute_tool()` 注入 `workspace=session.workspace_root`。
- 加测试：切到子目录后仍然能 `change_dir("..")` 回到根目录，但不能离开根目录。

验收标准：

```text
start cwd = project
change_dir("core") -> ok
change_dir("..") -> ok, cwd back to project
change_dir("..") -> denied
```

> **✅ 已修复** (2026-05-10)
>
> - `Session` 增加 `workspace_root` 字段，`new()` 时设为启动目录
> - `execute_tool()` 注入 `workspace=session.workspace_root`（不再用 `session.cwd`）
> - `load_from_file()` 兼容旧 session（无 `workspace_root` 时回退到 `cwd`）
> - REPL 启动画面和 `/status` 显示 workspace_root
> - 新增测试：`test_session_workspace_root_set_on_new`, `test_session_workspace_root_persists_on_save_load`, `test_session_load_old_format_without_workspace_root`, `test_change_dir_subdir_then_back_to_root`, `test_agent_loop_updates_session_cwd_on_change_dir`（验证 workspace_root 不变）

## 2. HTTP/curl 工具需要 SSRF 防护

`http_request()` 现在限制了协议只能是 `http://` 和 `https://`，这是好的第一步。但对于一个由模型自主调用的 HTTP 工具来说，还需要防止 SSRF。

当前风险：

- 可以访问 `http://localhost:...`
- 可以访问 `http://127.0.0.1:...`
- 可以访问内网地址，如 `10.0.0.0/8`、`192.168.0.0/16`、`172.16.0.0/12`
- 可以访问云服务元数据地址，如 `169.254.169.254`
- `follow_redirects=True` 可能先访问公网 URL，再重定向到内网地址

建议修改：

- 默认拒绝 localhost、loopback、link-local、private network、multicast。
- DNS 解析后检查最终 IP，而不是只检查 URL 字符串。
- 禁止或限制 redirect，至少每次 redirect 后重新校验目标地址。
- 增加配置项，例如：

```yaml
tools:
  http_request:
    allow_private_network: false
    follow_redirects: false
```

验收测试建议：

- `http://localhost:8000` 默认拒绝。
- `http://127.0.0.1:8000` 默认拒绝。
- `http://169.254.169.254/latest/meta-data` 默认拒绝。
- 公网 URL 302 到内网地址时默认拒绝。

> **✅ 已修复** (2026-05-10)
>
> - `http_request()` 新增 SSRF 防护：`_is_private_ip()` 检查 loopback/private/link-local/multicast
> - DNS 解析后检查最终 IP（`socket.getaddrinfo`），不只是 URL 字符串
> - 手动处理 redirect（`follow_redirects=False`），每次 redirect 重新校验目标地址，最多 5 次
> - `localhost` 和 `0.0.0.0` 直接拒绝（不依赖 DNS）
> - 新增 `allow_private_network` 参数（默认 `False`），可配置放行
> - 新增 8 个 SSRF 测试：localhost、127.x、10.x、192.168.x、169.254.x、allow_private 绕过、公网放行、redirect 到内网拦截

## 3. REPL 超时提示和真实行为不一致

`cli/repl.py` 超时时会打印：

```text
Session not modified.
```

但实际后台线程已经开始执行：

```python
result_holder[0] = self.agent.run(user_input)
```

而 `AgentLoop.run()` 一开始就会：

```python
self.session.add_message("user", user_input)
```

所以一旦超时，session 很可能已经被修改。更麻烦的是线程是 daemon，超时返回后后台请求仍可能继续执行，并继续写入 session。

建议修改：

- 不要承诺 `Session not modified`，除非真的做到事务化。
- 更好的做法是引入 per-turn 临时 session：
  1. 深拷贝当前 session。
  2. 在线程里对临时 session 运行 agent。
  3. 只有成功完成时才替换主 session。
  4. 超时或错误时丢弃临时 session。
- 或者暂时把提示改成更准确的：

```text
Agent timed out. The background request may still finish; consider restarting the REPL before continuing.
```

验收测试建议：

- mock provider sleep 超时后，主 session 不新增 user message。
- 超时后再次输入不会和旧线程交错写 session。

> **✅ 已修复** (2026-05-10)
>
> - `run_agent()` 改为用 `copy.deepcopy(session)` 创建临时 session，在临时 session 上运行 agent
> - 成功完成后才用 `set_session(session_copy)` 替换主 session
> - 超时时主 session 完全不受影响（无 user message，无后台写入）
> - 超时提示改为准确描述："Session not modified. The background request may still be running..."
> - 新增 2 个测试：`test_repl_timeout_does_not_modify_session`, `test_repl_success_commits_session`

## 4. HTTP 响应截断应按 bytes 和 content-type 处理

`http_request()` 当前使用：

```python
body_text = resp.text
if len(body_text) > MAX_RESPONSE_SIZE:
    body_text = body_text[:MAX_RESPONSE_SIZE]
```

这里的 `MAX_RESPONSE_SIZE` 注释是 10KB，但 `len(body_text)` 是字符数，不是字节数。遇到中文、emoji、压缩内容、二进制响应时，限制会不准确。

另外，`resp.text` 会尝试把响应解码成文本。对于图片、PDF、zip、音频等二进制内容，这会产生无意义输出，甚至把大量乱码塞进 session。

建议修改：

- 优先检查 `Content-Type`。
- 对明显二进制类型只返回摘要，不返回 body：

```text
HTTP/1.1 200 OK
Content-Type: application/pdf
Body omitted: binary response, 348291 bytes
```

- 截断基于 `resp.content` 的 bytes 长度。
- 文本响应再按编码解码，失败时返回安全摘要。
- 返回 headers 摘要，至少包含 `content-type`、`content-length`、`location`。

验收测试建议：

- UTF-8 中文响应按 bytes 截断。
- `application/pdf` 不输出二进制 body。
- 无 charset 响应也不会抛异常。
- 截断提示显示真实 byte size。

> **✅ 已修复** (2026-05-10，随 SSRF 防护一并完成)
>
> - `_is_binary_content()` 检测 image/video/audio/pdf/zip 等二进制 Content-Type
> - 二进制响应只返回摘要："Body omitted: binary response ({type}), {bytes} bytes"
> - 截断基于 `resp.content`（bytes）而非 `resp.text`（字符）
> - 文本解码用 `decode("utf-8", errors="replace")`，不会因编码异常崩溃
> - 响应包含 headers 摘要：content-type、content-length、location
> - 新增 3 个测试：`test_binary_content_type_omits_body`, `test_utf8_chinese_truncated_by_bytes`, `test_response_headers_summary`

## 推荐下一步顺序

1. 先修 `workspace_root`，这是文件/目录工具的基础安全模型。
2. 再修 HTTP SSRF 防护，因为 curl 工具一旦开放给模型调用，风险比普通读文件更外放。
3. 然后修 REPL 超时事务化，避免“看起来超时了，实际上后台还在写状态”。
4. 最后优化 HTTP 响应处理，让工具输出更稳定、更适合长期进入 session。

这 4 个点修完后，这个项目就更接近一个可以长期使用的本地 Agent，而不是只适合 demo 的工具调用框架。
