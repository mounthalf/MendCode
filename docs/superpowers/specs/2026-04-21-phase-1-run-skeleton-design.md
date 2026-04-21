# MendCode Phase 1 Run Skeleton Design

## 1. 背景

Phase 0 已经完成基础工程骨架，当前仓库已经具备以下稳定能力：

- Python 包结构与 `pyproject.toml`
- CLI 基础命令
- FastAPI 健康检查接口
- `TaskSpec` / `TraceEvent` 基础 schema
- JSONL trace 记录器
- 覆盖这些能力的单元测试与集成测试

接下来的目标不是立刻做完整修复链，而是先补上一个真正的“运行态骨架”。这个骨架需要让 MendCode 从“能校验任务文件”升级为“能运行一次最小任务流程并留下结构化运行结果”。

这一刀必须保持克制，避免提前引入 worktree、工具系统、模型推理或命令执行，把简单问题做复杂。

## 2. 目标

本设计只交付一个最小 `task run` 闭环：

`读取任务文件 -> 创建 RunState -> 记录开始 trace -> 记录结束 trace -> 输出摘要`

完成后系统应具备以下能力：

- CLI 支持 `mendcode task run <file>`
- 运行时生成稳定的 `run_id`
- 构造最小 `RunState`
- 记录 `run.started` / `run.completed` 两类 trace 事件
- 输出面向用户的运行摘要

## 3. 非目标

本阶段明确不做：

- 不执行 `verification_commands`
- 不创建或切换 Git worktree
- 不读取目标仓库代码文件
- 不调用 `read_file`、`search_code`、`apply_patch` 等工具
- 不进行模型推理
- 不引入 service 层、任务队列或 API 任务提交

这些能力属于后续 Phase 1 扩展项，当前只需要建立执行主链的最小骨架。

## 4. 设计原则

### 4.1 先建立执行态，再扩工具

当前最缺的不是工具数量，而是统一的运行入口和状态对象。先补上执行主链骨架，后续工具和 workspace 才有稳定挂载点。

### 4.2 结构独立，但不过度抽象

运行逻辑不应继续堆进 `app/cli/main.py`，但也不需要提前抽象出 application service。当前只新增：

- `app/schemas/run_state.py`
- `app/orchestrator/runner.py`

这样既保持边界清晰，也避免超前设计。

### 4.3 状态字段按当前需要最小化

方案文档中的完整 `RunState` 最终仍然成立，但这一刀不必一次引入所有未来字段。先定义当前必需字段，后续再逐步扩展。

### 4.4 trace 先服务于可观察性

当前 trace 的目的不是精细回放复杂执行链，而是明确记录一次任务运行已经开始和结束，并能被 CLI 和后续评测逻辑引用。

## 5. 模块设计

### 5.1 `app/schemas/run_state.py`

职责：

- 定义最小 `RunState`
- 为 runner 和 CLI 提供统一运行结果结构

建议字段：

- `run_id`
- `task_id`
- `task_type`
- `status`
- `current_step`
- `summary`
- `trace_path`

约束：

- `status` 当前只需要 `running`、`completed`、`failed`
- `current_step` 当前只需要表达最小运行阶段，不提前复刻完整状态机
- `trace_path` 使用字符串形式，便于直接展示到 CLI 输出中

### 5.2 `app/orchestrator/runner.py`

职责：

- 提供最小运行入口
- 构造开始态和结束态
- 写入开始/结束 trace

建议对外暴露一个纯 Python 函数接口：

`run_task_preview(task: TaskSpec, traces_dir: Path) -> RunState`

执行流固定为：

1. 生成 `run_id`
2. 构造开始态 `RunState(status="running")`
3. 记录 `run.started`
4. 直接构造结束态 `RunState(status="completed")`
5. 记录 `run.completed`
6. 返回结束态给 CLI

该模块不负责：

- 任务文件解析
- CLI 输出格式
- 环境变量读取

### 5.3 `app/cli/main.py`

职责新增：

- 增加 `task run <file>` 命令
- 复用现有任务文件加载和错误处理逻辑
- 调用 runner
- 将返回的 `RunState` 以表格或简洁文本输出

CLI 摘要至少展示：

- `run_id`
- `task_id`
- `task_type`
- `status`
- `current_step`
- `trace_path`
- `summary`

## 6. 数据流

`task run` 的完整数据流如下：

1. CLI 接收任务文件路径
2. CLI 复用现有 `_load_task_spec_or_exit`
3. CLI 读取 `settings` 并确保 trace 目录存在
4. CLI 调用 `run_task_preview(task, settings.traces_dir)`
5. runner 写入两条 trace 事件
6. runner 返回结束态 `RunState`
7. CLI 输出运行摘要

这里不引入异步、不引入长时运行状态、不引入后台执行。当前所有流程都保持同步完成。

## 7. Trace 事件设计

当前只增加两类事件：

- `run.started`
- `run.completed`

每条事件的 `payload` 保持最小化，只包含：

- `task_id`
- `task_type`
- `status`
- `summary`

不提前加入文件列表、命令输出、补丁摘要、模型思考等后续字段。

## 8. 错误处理

错误处理只覆盖当前阶段真实会发生的问题。

### 8.1 CLI 层负责的错误

继续复用现有逻辑处理：

- 任务文件不存在
- JSON 非法
- schema 校验失败
- 普通 `OSError`

### 8.2 runner 层负责的错误

runner 只负责运行期写 trace 相关错误：

- trace 文件写入失败
- 运行过程中的未预期异常

处理策略：

- 失败时返回 `failed` 状态或抛出异常给 CLI
- CLI 输出简洁错误信息并以非零退出码结束

当前不做重试、补偿写入或半完成恢复逻辑。

## 9. 测试策略

本阶段测试保持小而直接。

### 9.1 单元测试

`tests/unit/test_run_state.py`

- 校验 `RunState` 可正确构造
- 校验默认或受限字段行为

`tests/unit/test_runner.py`

- 校验 runner 会生成 `run_id`
- 校验返回状态为 `completed`
- 校验 trace 文件存在
- 校验 trace 文件至少包含两条事件
- 校验事件类型为 `run.started` / `run.completed`

### 9.2 集成测试

在 `tests/integration/test_cli.py` 增加：

- `task run` 命令成功执行
- 输出包含 `run_id`、`status`、`trace_path`
- trace 文件落盘成功

## 10. 验收标准

这一刀完成的标准是：

- `python -m app.cli.main task run data/tasks/demo.json` 可运行
- 命令输出包含 `run_id`、`task_id`、`status`、`trace_path`
- trace 文件存在，且至少包含 `run.started` 和 `run.completed`
- 全量测试继续通过

## 11. 后续衔接

这一刀完成后，下一步优先顺序建议为：

1. 扩展 `RunState` 到真实执行链字段
2. 增加 `run_verification` 工具并接入 runner
3. 引入 workspace / worktree 管理
4. 再接入 `read_file`、`search_code`、`apply_patch`

这样可以保持主链按“先执行框架、再验证、再仓库操作、最后补丁修改”的顺序推进，避免在早期阶段把系统做散。
