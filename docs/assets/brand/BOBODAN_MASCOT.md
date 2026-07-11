# Bobodan 三花猫品牌角色

## 1. 主参考图

角色与场景主参考图：

```text
docs/assets/brand/bobodan-calico-mascot-primary.png
```

文件信息：

- 尺寸：`1254 × 1254`
- 格式：PNG
- SHA-256：`8c9e828eabaf4153fe4e883c9c1ef41f3491b5d1e1400c0326c10eb4666e04bd`
- 用途：角色外观、线条、配色和气质的 source of truth
- 当前限制：图片带暖纸色背景，不是透明底；更适合作为风格参考和大尺寸插图，不直接作为所有 UI 图标使用

正式 UI 头像母版：

```text
docs/assets/brand/bobodan-calico-avatar-master.png
```

- 尺寸：`2048 × 2048`
- 格式：透明 PNG
- 用途：UI 头像构图、脸型、神态和三花左右分区的 source of truth
- 已清理右下角孤立残留像素；不得再次使用旧棋盘格或带水印版本覆盖

文档侧标准导出：

```text
docs/assets/brand/bobodan-calico-avatar-primary.png
docs/assets/brand/bobodan-calico-avatar-512.png
docs/assets/brand/bobodan-calico-avatar-256.png
docs/assets/brand/bobodan-calico-avatar-128.png
docs/assets/brand/bobodan-calico-avatar-64.png
docs/assets/brand/bobodan-calico-avatar-32.png
```

- `primary` 是 `1024 × 1024` 透明底母版。
- 其他尺寸均从正式母版导出，不要在浏览器里长期缩放超大原图。
- 前端代码统一使用 `web/frontend/public/assets/brand/` 下的资源，不直接引用 `docs/`。

## 2. 固定识别特征

后续所有图片必须保持同一只三花猫，而不是重新设计角色：

- 白色身体为主。
- 画面左侧额头、左耳和左脸是橘棕色斑块。
- 画面右侧额头、右耳和右眼周围是深墨蓝斑块。
- 背部有明显深墨蓝斑块，身体有少量橘棕斑块。
- 尾巴由深墨蓝与橘棕色分段组成，末端偏深墨蓝。
- 眼睛为低饱和灰绿色，神态安静、聪明、好奇。
- 主轮廓使用墨蓝手绘线条，线条有轻微粗细变化。
- 只使用少量低饱和平涂，不做复杂体积光和写实毛发。
- 角色气质成熟、温和、克制，不幼儿化，不靠夸张卖萌。

品牌配色继续使用 `docs/DESIGN.md`：墨蓝 `#1B365D`、橘棕 `#B86F4B`、暖纸色 `#F5F4ED`、植物绿 `#7A9B76`。

## 3. 品牌与人设边界

Bobodan 小猫是默认品牌载体，不是不可修改的助手人格。

- 固定：产品名称、品牌标志、默认小猫、事实与来源标注、安全边界。
- 可配置：助手称呼、表达语气、教学方式、反馈强度、对话头像和陪伴方式。
- 用户可以选择默认小猫、自定义头像、极简图标或不显示头像。
- 当用户替换对话角色时，Bobodan 小猫仍可保留在产品 Logo、启动页和系统空状态中。

## 4. 已完成的首批资产

首批 Web UI 所需品牌图片已完成，不再处于“待生成”状态：

| 资产 | 母版 | 前端用途 |
|---|---|---|
| 主头像 | `bobodan-calico-avatar-master.png` | 侧栏、AI 回复、用户选择默认角色 |
| 四表情 | `bobodan-calico-avatar-expressions-master.png` | neutral / friendly / curious / content |
| 六学习状态 | `bobodan-calico-states-master.png` | listening / reading / writing / thinking / ready / resting |
| Chat 起始插图 | `bobodan-chat-hero-master.png` | Today / Chat 空状态，保留左侧文案留白 |

前端衍生资源与引用说明统一位于：

```text
web/frontend/public/assets/brand/
```

只有在新增明确场景时才继续生成图片。不要为了“更丰富”扩充大量重复姿态，也不要重新设计主头像。

## 5. 通用负面提示词

每次生成都附加：

```text
不要改变三花斑纹，不要左右交换脸部颜色，不要生成另一只猫，不要增加或减少尾巴，不要 3D，不要照片写实，不要动漫大眼，不要 Emoji，不要幼儿卡通，不要潮玩，不要毛绒玩具，不要拟人身体，不要穿复杂服装，不要夸张笑脸，不要霓虹色，不要紫色渐变，不要复杂背景，不要猫爪图案背景，不要文字，不要水印，不要边框，不要高饱和色，不要厚重投影，不要多只猫，不要变形肢体。
```

## 6. 接收新图片时

新图片放入本目录前必须检查：

1. 与主参考图是否是同一只猫。
2. 斑纹方向和尾巴花纹是否一致。
3. 线条与颜色是否符合 `docs/DESIGN.md`。
4. 背景是否满足目标用途：UI 小图优先透明底，场景插图可以使用暖纸底。
5. 缩小后是否仍能辨认，是否存在多余肢体、错误书本结构或伪文字。

## 7. 2026-07-10 正式资产接收记录

四张用户确认的无水印图片已保存为正式母版。`candidates/` 仅保留旧路径兼容副本，后续文档与代码不得继续把它们当作候选标准：

```text
docs/assets/brand/candidates/
```

| 正式母版 | 检查结果 | 用途结论 |
|---|---|---|
| `bobodan-calico-avatar-master.png` | 真实 alpha、四角透明；已清理右下角孤立残留点 | 唯一正式 UI 主头像母版 |
| `bobodan-calico-avatar-expressions-master.png` | 真实 alpha；四个表情可独立裁切 | 作为辅助情绪状态，不替代主头像 |
| `bobodan-calico-states-master.png` | 真实 alpha；六个角色对象完整分离 | 用于学习过程与空状态反馈 |
| `bobodan-chat-hero-master.png` | 暖纸背景、无文字、左侧留白完整 | 用于 Chat 起始页和学习空状态 |

接收检查已覆盖透明角、主体边界、`32px / 64px` 识别度、深色背景白边和横图缩放。正式开发优先使用 Web 目录中的导出文件。
