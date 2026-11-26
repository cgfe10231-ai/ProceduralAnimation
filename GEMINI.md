# ProceduralAnimation — Agent 永久执行入口

此文件只负责锁定执行规则，不记录阶段进度、单个 BUG、特定模块修改或测试成绩。

1. 开始前必须阅读 WORKFLOW_GOVERNANCE.md、ARCHITECTURE.md、PROJECT_SPEC.md、docs/ARCHITECTURE_CHANGE_GATE.md；读取失败或规则冲突立即停止。
2. 当前状态必须核实 PROJECT_STATE.md、ARCHITECTURE_SYNC.md、docs/audit/production_interface/OPEN_FINDINGS.md 和 Git HEAD，不得从历史交接或旧证据自行取得权限。
3. **Antigravity 对仓库全部 .md 默认只读；未经项目负责人主动、明确且限定文件范围的授权，禁止创建、修改、追加、覆盖、移动、重命名、删除或自动同步 Markdown。获得授权时，仅允许逐字执行 ChatGPT 已审定的指定内容及相应 Git 收尾，禁止自主编写或扩展；授权任务结束后恢复默认只读。**
4. Agent 只能执行已经冻结并明确批准的机械代码/测试任务；不得自行审计、定性漏洞、增加新函数或模块、扩充范围、改断言或变更架构。
5. 编码和测试必须分离；代码变更经 ChatGPT 独立审查后才能执行测试；测试失败立即停止保留现场，不得就地修改。
6. 新函数默认禁止；经负责人特批时，必须在定义紧邻上一行记录真实时间、任务节点、函数名称、职责、解决问题和引入必要性。
7. 禁止第二套姿态控制器、恢复状态机、虚假物理指标、硬编码特殊错误帧、静默错误及历史动作无关改写。
8. 禁止自动推送或合并 master，必须先由负责人批准。只暂存获授权文件，严禁盲目暂存。
9. 任何任务或历史文件都不得为某一执行 Agent、模块、BUG 或测试设立例外条款。
