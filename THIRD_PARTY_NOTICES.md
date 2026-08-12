# Third-Party Notices

Bobodan（波波蛋）以 Apache-2.0 发布（见根目录 `LICENSE`）。本项目运行时依赖以下第三方组件，各组件版权归其作者所有，并遵循各自许可证条款。

> 维护纪律：任何依赖的增删都必须同步更新本清单。无法确认再分发许可的资产不得进入发布安装包。首次发布前必须重新执行完整许可证审计（Python `pip-licenses` / npm `license-checker` 或等价工具）并核对此处记录。

## Python 运行时依赖

| 包 | 版本基线 | 许可证 |
|---|---|---|
| fastapi | >=0.115 | MIT |
| uvicorn | >=0.30 | BSD-3-Clause |
| httpx | >=0.27 | BSD-3-Clause |
| pydantic（fastapi 传递依赖） | — | MIT |
| starlette（fastapi 传递依赖） | — | BSD-3-Clause |
| python-dotenv | >=1.0 | BSD-3-Clause |
| PyYAML | >=6.0 | MIT |
| pypdf | >=4.0 | BSD-3-Clause |
| python-docx | >=1.1 | MIT |
| python-pptx | >=1.0 | MIT |
| python-multipart | >=0.0.9 | Apache-2.0 |
| prompt_toolkit | >=3.0 | MIT |
| rich | >=13.0 | MIT |
| mcp | >=1.0 | MIT |
| qdrant-client | >=1.12 | Apache-2.0 |

发布前须复核：`prompt_toolkit`（BSD-3-Clause）、`rich`（MIT）、`mcp`（MIT）、`qdrant-client`（Apache-2.0）的实际版本许可证。

## npm 前端依赖

| 包 | 许可证 |
|---|---|
| react / react-dom | MIT |
| react-router-dom | MIT |
| react-markdown / remark-gfm | MIT |
| zustand | MIT |
| sigma / graphology / graphology-layout-forceatlas2 | MIT |
| lucide-react | ISC |
| vite / vitest / tailwindcss / eslint / jsdom | MIT |
| typescript / @playwright/test | Apache-2.0 |

## 字体与品牌资源

| 资产 | 位置 | 许可证 / 状态 |
|---|---|---|
| Luo（LXGW WenKai Screen 衍生） | `web/frontend/public/assets/fonts/Luo-*` | SIL OFL 1.1（附 `Luo-LICENSE.txt`） |
| Noto Serif SC | `web/frontend/public/assets/fonts/noto-serif-sc/` | SIL OFL 1.1（附 `OFL.txt`） |
| 仓耳今楷 TsangerJinKai02 W04/W05 | `web/frontend/public/assets/fonts/kami-reading/` | **发布前必须核实上游字体授权条款**（来源 tw93/Kami，未附带明确许可证文件） |
| Bobodan 品牌形象（三花猫插画、Logo） | `docs/assets/brand/`、前端资源 | 本项目原创资产 |

### 发布前必办

1. `pip-licenses` 与 `npm license-checker` 全量复核，与上表对照。
2. 确认仓耳今楷字体的再分发许可；无法确认则从安装包排除并在阅读器回退到 Noto Serif SC。
3. 生成 Python / npm SBOM 与依赖许可证清单，随发布产物附 `SHA256SUMS.txt`。
4. CI 阻止任何 GPL / AGPL 依赖被重新引入（见 `.github/workflows` 许可证检查）。

## 设计参考（不构成再分发）

- **Pi**（earendil-works/pi）：架构参考，未复制代码。
- **OpenHanako**（liliMozi/openhanako）：架构与交互参考；若未来直接复用其代码，须遵守 Apache-2.0 并保留必要声明。
- **nashsu/llm_wiki**：机制参考；GPL-3.0 代码未复制。
