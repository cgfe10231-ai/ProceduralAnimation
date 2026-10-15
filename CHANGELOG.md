# CHANGELOG: 项目变更历史

所有条目必须严格遵循客观事实纪律，未经验证的不得标记为已验证。

---

## [2026-10-16] 任务 2：建立 Git 版本控制与程序化动画工程骨架

### 新增 (Added)
* **版本控制**：
  * 初始化本地 Git 仓库 (`git init`)。
  * 创建 `.gitignore`，自动忽略 Python 缓存、日志、`output/` 及 `tests/output/` 等测试/渲染二进制产物。
* **模块化工程骨架 (`src/`)**：
  * 创建 `src/config.py`：集中配置 `PipelineConfig`（FPS 24、360 帧、1280x720 分辨率、Workbench 引擎、随机种子 42、统一输出路径）。
  * 创建 `src/scene/builder.py`：场景初始化、时间线与分辨率注入及校准标记创建。
  * 创建 `src/camera/controller.py`：标准摄像机构建与激活。
  * 创建 `src/lighting/setup.py`：基础照明布设。
  * 创建 `src/character/`、`src/rig/`、`src/motion/`：核心子系统模块规范与接口占位。
  * 创建 `src/render/engine.py`：渲染引擎设置、单帧渲染与 `.blend` 保存。
  * 创建 `src/validation/checker.py`：产物完整性与图像尺寸自动核验。
  * 创建 `src/pipeline.py`：全流程管线协调器。
  * 创建 `run_pipeline.py` 与 `run_pipeline.ps1`：统一的宿主/Blender双模调用入口。
* **架构与决策**：
  * 更新 `ARCHITECTURE.md`：详细绘制模块化结构与数据流。
  * 录入 `[DEC-009]`：模块化工程骨架与配置驱动模式。

### 状态验证 (Verification)
* **Git 隔离与跟踪范围**：实测 `git status`，`output/` 与 `tests/output/` 等产物均被准确忽略，无外部文件被追踪。
* **全管线执行与重现**：
  * 执行 `run_pipeline.ps1`，Blender 5.1.1 后台无头运行成功，返回码为 `0`。
  * 输出 `output/procedural_scene.blend`（87,440 字节，非空）。
  * 输出 `output/preview_frame_0001.png`（315,929 字节，通过二进制校验确认为 `1280 x 720`）。
  * 重复执行测试通过，管线稳定可靠。

---

## [2026-10-15] 任务 1：Blender 环境与自动执行工具链验证

### 新增 (Added)
* 测试套件：`tests/test_env.py`、`tests/verify_blend.py`、`tests/run_validation.py`、`tests/run_test.ps1`。
* 决策记录：`[DEC-008]`（Blender 5.1.1 Headless 调用规范与闭环检验基准）。

### 状态验证 (Verification)
* Blender 5.1.1 + Python 3.13.9 路径定位与无头执行成功。
* 生成 `tests/output/test_scene.blend` 与 `tests/output/test_render.png` (320x180)，二次重开场景验证通过。

---

## [2026-10-15] 任务 0.5：建立跨 AI 同步协议与上下文恢复机制

### 新增 (Added)
* 创建 `AI_SYNC.md`。
* 增加任务生命周期协议与防状态漂移原则。
* 决策记录：`[DEC-007]`。

### 状态验证 (Verification)
* 系统提示词成功自动挂载根目录规则至 `<user_rules>`。

---

## [2026-10-15] 任务 0：底层约束、持久记忆与基础设施建立

### 新增 (Added)
* 创建规则 `GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`。
* 创建文档 `PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`HANDOFF.md`、`README.md`。
