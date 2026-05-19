# Skills 系统

Skills 是波波蛋的扩展能力系统。每个 skill 是一组针对特定任务的专业指令，agent 可以自动发现并使用。

## 目录结构

```
skills/
  weather/
    SKILL.md      # skill 定义文件
  github/
    SKILL.md
  ...
```

## SKILL.md 格式

每个 skill 必须包含一个 `SKILL.md` 文件，格式为 YAML frontmatter + Markdown body：

```yaml
---
name: weather
description: "查询天气信息。当用户问天气、温度、是否下雨时使用。"
---

# Weather Skill

通过 wttr.in 查询天气信息。

## 使用场景
- "北京今天天气怎么样"
- "上海会下雨吗"

## 查询命令
\`\`\`bash
curl -s "wttr.in/Beijing?format=3"
\`\`\`
```

### Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | skill 名称，用于 `/skill` 命令 |
| `description` | 是 | 一句话描述，用于模型判断是否使用该 skill |

### Body 内容

Markdown 正文，包含 skill 的详细指令。模型在决定使用某个 skill 后，会通过 `read_file` 工具读取完整内容并遵循指令。

## 工作机制

1. **启动加载**: agent 启动时扫描 `skills/` 目录，解析所有 `SKILL.md` 的 frontmatter
2. **注入提示词**: 将 skill 目录格式化为 XML 注入 system message：
   ```xml
   <available_skills>
     <skill>
       <name>weather</name>
       <description>查询天气信息</description>
       <location>/path/to/skills/weather/SKILL.md</location>
     </skill>
   </available_skills>
   ```
3. **模型自主判断**: 模型看到目录后，根据用户输入判断是否需要某个 skill
4. **读取执行**: 如果匹配，模型调用 `read_file` 读取完整 SKILL.md 并遵循指令

## REPL 命令

```
/skill list         # 列出所有可用 skill
/skill <name>       # 查看指定 skill 的内容
/skill run <name>   # 将 skill 作为 agent 任务执行
```

## 配置

在 `config.yaml` 中配置：

```yaml
skills:
  enabled: true    # 是否启用 skills
  dir: "skills"    # skills 目录路径
```

## 创建新 Skill

1. 在 `skills/` 下创建子目录（如 `skills/my-skill/`）
2. 在子目录中创建 `SKILL.md`
3. 填写 frontmatter（`name` + `description`）
4. 在 body 中写入详细指令
5. 重启 agent 即可生效

## 示例

参考 `skills/weather/SKILL.md`。
