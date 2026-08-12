# Bobodan 前端品牌图片

本目录只存放可以直接由 Web 前端引用的衍生资源。无损母版位于 `docs/assets/brand/`，不要在前端运行时读取文档目录。

## 目录

| 目录 | 内容 | 推荐用法 |
|---|---|---|
| `avatar/` | 主头像 PNG 与透明 WebP | AI 回复头像、侧栏品牌入口、默认角色选择 |
| `expressions/` | 4 个 `768 × 768` 透明表情 | 低频情绪反馈，不连续动画播放 |
| `states/` | 6 个 `768 × 768` 透明学习状态 | Chat、Practice、Review、空状态 |
| `hero/` | `1536 × 960` 与 `960 × 600` WebP | Chat / Today 起始页插图 |
| `bobodan.ico` | 多尺寸应用图标（16–256） | 浏览器 favicon、Windows 桌面安装包图标（P5G.2） |

## 主头像

PNG 尺寸：`32 / 64 / 128 / 256 / 512 / 1024`。WebP 尺寸：`256 / 512 / 1024`。

```html
<img
  src="/assets/brand/avatar/bobodan-avatar-64.png"
  srcset="/assets/brand/avatar/bobodan-avatar-64.png 1x,
          /assets/brand/avatar/bobodan-avatar-128.png 2x"
  width="64"
  height="64"
  alt="Bobodan"
>
```

头像已经包含透明安全边距。圆形头像由 CSS 容器裁切，不要把圆形底板烘焙进图片。

## 表情

- `bobodan-expression-neutral`
- `bobodan-expression-friendly`
- `bobodan-expression-curious`
- `bobodan-expression-content`

主对话默认仍使用正式主头像。表情资源只在明确的反馈状态中切换，避免界面过度活泼。

## 学习状态

- `bobodan-state-listening`
- `bobodan-state-reading`
- `bobodan-state-writing`
- `bobodan-state-thinking`
- `bobodan-state-ready`
- `bobodan-state-resting`

状态图使用稳定的正方形透明画布和底部基线，可以在同一组件中直接替换，不应改变布局尺寸。
表情与状态插图按暖纸色界面优化；不要直接放在大面积墨蓝底上，以免抠图边缘显得像白色贴纸。

## Chat 场景

```html
<picture>
  <source media="(max-width: 720px)" srcset="/assets/brand/hero/bobodan-chat-hero-960x600.webp">
  <img
    src="/assets/brand/hero/bobodan-chat-hero-1536x960.webp"
    width="1536"
    height="960"
    alt="Bobodan 陪伴学习"
  >
</picture>
```

横图左侧留白用于问候与输入入口。移动端应等比缩放或使用 `object-fit: contain`，不要用 `cover` 裁掉小猫、书本或尾巴。

## 约束

- 优先使用 WebP；需要像素级透明兼容或小尺寸头像时使用 PNG。
- 不要拉伸图片，不要在运行时重新抠图，不要添加白色贴纸描边。
- 不要引用 `docs/assets/brand/candidates/`，这些路径只为历史兼容保留。
- 新增资源前先检查 `docs/DESIGN.md` 与 `docs/assets/brand/BOBODAN_MASCOT.md`。
