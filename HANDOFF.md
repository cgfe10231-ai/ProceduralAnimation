# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 3（程序化三维场景、灯光与摄像机基础系统）后，等待指示开启任务 4（程序化角色网格与骨骼装配）。

## 2. 已完成
* 确认环境隔离（保护桌面无关 Unity 及实验报告等工程）。
* 建立统一世界坐标约定（$Z$ 轴向上，地表精准对齐 $Z=0.0\text{ m}$，单位米）。
* 实现纯 Python 确定性几何布局生成器（`src/scene/layout.py`）与 $\ge 2.4\text{ m}$ 走廊净空算法。
* 实现程序化地台、6 座建筑体块、8 根圆柱障碍物与航标标记（`src/scene/builder.py`）。
* 实现 2500W 主光 + 800W 辅光 + 世界环境光系统（`src/lighting/setup.py`）。
* 实现 50mm、Track-To 自动追踪、第 1/180/360 帧关键帧位移运镜系统（`src/camera/controller.py`）。
* 输出并核验第 1 帧与第 180 帧两张 1280x720 预览渲染图与 `output/procedural_scene.blend`。
* 全套持久文档更新完毕。

## 3. 已验证
* 地面高度实测：$Z_{\text{top}} = 0.000000\text{ m}$。
* 走廊净空：3 个运动路标及路径与所有障碍物距离均严格 $\ge 2.4\text{ m}$，无穿插。
* 种子可复现性与变异性：Seed 42 两次输出完全相同；Seed 99 产生不同布局。
* 相机动态运镜：第 1 帧与第 180 帧位移达 $11.3578\text{ m}$。
* 产物生成与核验：
  * `output/procedural_scene.blend`（105,272 字节，无头重开核验通过）。
  * `output/preview_frame_0001.png`（306,427 字节，1280x720，远景大景别）。
  * `output/preview_frame_0180.png`（248,321 字节，1280x720，中景跟拍新视角）。
* 确认未改动任何外部文件，未提前制作正式角色与角色动画。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`test_task3_spatial.py`、`verify_task3_blend.py`、`test_env.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 规则分级机制中，`.agents/rules/` 独立加载及外部新会话自动恢复状态按纪律保持为“未完整验证”。

## 6. 下一步
* 等待用户指示开启任务 4（程序化人形占位角色生成与骨骼装配基础）。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-009] 保持有效。
* [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制。
