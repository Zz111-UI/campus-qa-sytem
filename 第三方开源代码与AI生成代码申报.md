# 百花学习与生活顾问系统

# 第三方开源代码与 AI 生成代码申报说明

| 项目 | 内容 |
|---|---|
| 软件名称 | 百花学习与生活顾问系统（Baihua Advisor） |
| 版本 | V2.6（优化版 · 已标注） |
| 编写日期 | 2026 年 10 月 7 日 |
| 适用材料 | 大赛参赛申报：第三方开源代码清单 + AI 生成代码标注说明 |
| 标注方式 | 源代码内逐处注释标记（本包所有 AI 代码段均已就地标注，见第二章清单） |

---

## 一、第三方开源代码清单

本系统使用的所有第三方开源库、框架清单如下。版本号为本项目运行环境（Python 3.11 venv + 本地化前端资源）实测采集，非估算。

### 1.1 直接依赖（requirements.txt 声明）

| # | 名称 | 版本 | 许可证 | 来源 | 在本系统中的用途 |
|---|---|---|---|---|---|
| 1 | **FastAPI** | 0.141.1 | MIT | github.com/fastapi/fastapi | Web 后端框架：路由定义、请求校验、静态文件挂载（app.py 全部 @app 路由、education/demo 路由器挂载） |
| 2 | **Uvicorn** | 0.53.0 | BSD-3-Clause | github.com/encode/uvicorn | ASGI 服务器：python app.py 启动时承载应用（config.py HOST/PORT 即其参数） |
| 3 | **Requests** | 2.34.2 | Apache-2.0 | github.com/psf/requests | HTTP 客户端：llm.py 调用百炼大模型接口、advisor.py 联网探测 |
| 4 | **python-multipart** | 0.0.32 | Apache-2.0 | github.com/andrew-d/python-multipart | 表单/文件解析：支持 /api/erke/upload 二课佐证图片上传（FastAPI 文件上传依赖） |

### 1.2 传递依赖（由上述库自动引入，随 pip 安装）

| # | 名称 | 版本 | 许可证 | 来源 | 引入路径 |
|---|---|---|---|---|---|
| 5 | Starlette | 1.7.0 | BSD-3-Clause | github.com/encode/starlette | FastAPI 底层的 ASGI 工具集（StaticFiles 即来自它） |
| 6 | Pydantic | 2.13.5 | MIT | github.com/pydantic/pydantic | FastAPI 的请求/响应模型校验（app.py 中全部 BaseModel） |
| 7 | anyio | 4.15.1 | MIT | github.com/agronholm/anyio | Starlette 异步运行时 |
| 8 | click | 8.5.0 | BSD-3-Clause | github.com/pallets-eco/click | Uvicorn 命令行入口 |
| 9 | h11 | 0.16.0 | MIT | github.com/python-hyper/h11 | Uvicorn 的 HTTP/1.1 协议解析 |

### 1.3 前端第三方库（已本地化随包分发）

| # | 名称 | 版本 | 许可证 | 来源 | 用途与说明 |
|---|---|---|---|---|---|
| 10 | **Apache ECharts** | 5.6.1 | Apache-2.0 | github.com/apache/echarts | 课程图谱可视化（培养方案先修关系图）。文件位置：`web/echarts.min.js`（1.0MB，原为 CDN 同步加载，性能优化轮改为本地异步加载，文件头部保留 Apache 官方许可声明） |

**前端未使用任何其他框架/库**：页面（index.html/app.js/style.css）为原生 JavaScript + CSS 手写，无 jQuery、无 Bootstrap、无构建工具；字体仅引用系统自带字体族名（仿宋等），未引入 webfont 库。

### 1.4 AI 服务（非代码依赖，按 API 调用）

阿里云百炼平台（dashscope，qwen-plus 对话模型）：仅通过 HTTP API 调用，**不构成代码引入**；未配置 API Key 时系统自动降级为本地规则引擎，功能照常。

### 1.5 使用方式与合规声明

- 上述库均通过 `pip install -r requirements.txt` 从 PyPI 官方源安装，未修改任何开源库源码；
- ECharts 以官方发布产物原样引入（web/echarts.min.js），保留其原始 License 头；
- 所有许可证（MIT / BSD-3-Clause / Apache-2.0）均允许商用与再分发，本清单即履行其署名义务；
- 除以上 10 项外，系统不含其他第三方代码。

---

## 二、AI 生成代码标注说明

### 2.1 标注规则（已落实到源码注释）

1. **文件头声明**：每个含 AI 代码的文件首行插入总声明——"本文件由团队编写为主；标注 [AI编写] 的段落为开发迭代过程中由 AI（千问工作助理）生成的代码，均已标注。"
2. **段落标记**：AI 编写/改造的每一处代码段**上方**插入 `# [AI编写] 说明（所属迭代轮）`（py）、`// [AI编写]`（js）、`/* [AI编写] */`（css/html）注释；
3. 标注覆盖 AI 真实编写的全部改动，无遗漏；原团队编写的代码段一律未标注（标注过程中曾对 1 处启动钩子误标，已复核撤销）。

### 2.2 AI 生成代码全清单（25 处段落标注，按文件与行号）

**app.py**（主服务，12 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L23 | `import security / education / demo_data` 个性化模块挂载 | 合并轮 |
| L35 | `include_router(education.router / demo_data.router)` 路由注册 | 合并轮 |
| L40 | `_personal_snapshot()` 读取学生已同步修读快照（未授权返回 None） | 学分待同步轮 |
| L60 | `_mirror_session()` 会话桥接：本站令牌镜像到个性化安全层 | 合并轮 |
| L79 | `@app.on_event("startup") _init_personal()` 个性化启动初始化 | 合并轮 |
| L182 | 登录成功后调用 `_mirror_session` 一行 | 合并轮 |
| L582 | 目标规划回答追加"待同步"提示块 | 学分待同步轮 |
| L604 | 问答链路 `_snap/_credit_note` 待同步口径准备 | 学分待同步轮 |
| L606 | 课表类回答追加待同步说明（防推算学分冒充实绩） | 学分待同步轮 |
| L624 | 问答上下文按同步状态分支组装 | 学分待同步轮 |
| L688 | 本地兜底回答传入快照参数 | 学分待同步轮 |
| L717 | `/api/plan` 接口按同步状态返回学分 | 学分待同步轮 |

**advisor.py**（顾问引擎，2 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L334 | `plan_overview()` 签名扩展 snapshot 参数 + 待同步 None 语义（含同步核算分支） | 学分待同步轮 |
| L398 | `local_study_answer()` 待同步显示与开启引导模板 | 学分待同步轮 |

**config.py**（1 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L17 | 写入百炼 API Key 的赋值行（含安全提示注释） | 性能优化轮 |

**web/app.js**（前端主逻辑，3 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L272 | `switchTab()` 面板列表补 education + 登录引导 | UI 修复轮 |
| L306 | `loadPlan()` 统计卡"待同步"态渲染与引导 | 学分待同步轮 |
| L1166 | `renderGraph()` 等待图表库延迟加载就绪 | 性能优化轮 |

**web/education.js**（个性化前端，1 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L146 | `eduLoadTimetable()`：函数改名隔离 + 空值守卫（避免覆盖本站课表） | 合并轮 |

**web/style.css**（样式表，2 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L485 | `.personal-entry` 个性化入口按钮样式 | 合并轮 |
| L525 | **自本行起至文件末尾的全部 UI 主题规则**：浅绿荷花主题、全站仿宋、文字加深、卡片花朵图标、各轮字号/配色微调（约 100 行连续 AI 生成区） | UI 迭代轮 |

**web/index.html**（页面结构，4 处）

| 行号 | 内容 | 迭代轮 |
|---|---|---|
| L8 | 样式/图表库本地化引用行（style.css 版本参数 + echarts 本地 defer） | 性能优化轮 |
| L25 | 登录表单演示账号占位提示（placeholder 两处） | 文案修订轮 |
| L81 | 登录页演示账号 hint 说明文案 | 文案修订轮 |
| L116 | 欢迎页右侧「✦ 个性化服务」入口按钮 | 合并轮 |

### 2.3 关于第二个代码包的归属说明

"百花-个性化服务与数据库"包中的后端代码（security.py、education.py、demo_data.py、academic.py、buct_sync.py、school_data.py、原版 education.js）**为队友编写的原始交付物**，本系统按原样并入，其内容不属于本包标注范围；上述文件中仅有的 AI 改动即 2.2 清单所列（并入挂载、eduLoadTimetable 改名隔离、密码摘要统一为 123456 的数据操作）。UI 图片素材（荷花/花朵透明 PNG）为 AI 按团队提供的原图抠图生成，随包标注于文件命名（lotus-*.png / flower-*.png）。

### 2.4 核验结论

- 标注后全部 Python 模块通过语法编译（py_compile），重启服务实测 27 项端到端回归**全部通过**，标注不影响任何功能；
- 在源码根目录执行 `grep "AI编写"`（或编辑器全局搜索）可逐处复核本清单；
- 文件头声明共 7 处（每标注文件一处），段落标注 25 处，合计 32 处 AI 注释。
