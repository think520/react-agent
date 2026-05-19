---
name: weather
description: "查询天气信息。当用户问天气、温度、是否下雨、出行建议涉及天气时使用。"
---

# Weather Skill

通过 wttr.in 查询天气信息，无需 API key。

## 使用场景

- "北京今天天气怎么样"
- "上海会下雨吗"
- "明天适合出门吗"

## 查询命令

```bash
# 当前天气
curl -s "wttr.in/Beijing?format=3"

# 详细天气
curl -s "wttr.in/Beijing?lang=zh"

# 3天预报
curl -s "wttr.in/Beijing?format=v2&lang=zh"
```

## 注意事项

- 城市名用英文拼音，如 Beijing、Shanghai、Guangzhou
- `format=3` 返回一行简要信息
- `lang=zh` 返回中文
- `format=v2` 返回详细格式化预报
