# ProceduralAnimation: 全程序化 3D 连续动画系统

本项目是一个基于 Blender 与 Python (`bpy`) 的全程序化 3D 连续动画生成系统。整个流程涵盖从场景生成、人形角色占位网格、程序化骨骼绑定、8 阶段连续运动学控制、摄像机追踪、灯光材质布设到自动化低成本预览与正式渲染输出。

---

## 项目结构

```text
ProceduralAnimation/
├── .agents/
│   └── rules/
│       └── project_rules.md       # Antigravity 工作区规则规范
├── AGENTS.md                      # Antigravity / Agents 规则镜像
├── GEMINI.md                      # Antigravity 核心项目规则与纪律约束
├── PROJECT_SPEC.md                # 总体目标与第一阶段原型验收规格 (15s/360帧/8动作)
├── ARCHITECTURE.md                # 模块化架构规划蓝图与数据流设计
├── DECISIONS.md                   # 架构与技术决策记录 (ADR)
├── PROJECT_STATE.md               # 真实系统状态跟踪 (遵循严格六态纪律)
├── CHANGELOG.md                   # 变更历史日志
├── HANDOFF.md                     # 会话交接说明书
└── README.md                      # 本说明文件
```

---

## 核心设计与执行原则

1. **全程序化自动化**：所有 3D 资产、动画关键帧和渲染设置均由 Python 代码驱动，支持命令行/无头 (Headless) 自动运行。
2. **确定性与可复现**：采用固定随机种子，确保任意时刻重复生成结果完全一致。
3. **分级验证**：采用低成本预览先行（Workbench / Eevee 低采样快速预览），经自动化验证通过后再触发高质量正式渲染。
4. **严格事实纪律**：所有任务状态严格区分为“已实现、已执行但未完整验证、已验证、未实现、已知缺陷、理论可行但尚未测试”。
5. **安全隔离**：本工程为完全独立的目录，严禁影响任何外部工程与文件。
