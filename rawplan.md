
## **MendCode**

**面向企业本地代码仓的 CI / PR 维护闭环 Agent**

这样定题最稳。因为公开资料已经很清楚：当前成熟的 **coding agent** 都在围绕“**读代码仓、改文件、跑命令、接工具、可追踪、可评测**”演进；同时，**MCP** 2026 年的重点也已经转向 **Agent Communication、Governance、Enterprise Readiness**，说明企业化接入、治理和可控性才是下一阶段重点。([Claude][1])

---

## 1. 项目目标与边界

### **项目目标**

系统接收来自企业本地代码仓的维护任务，完成这条闭环：

**输入任务 → 定位问题 → 选取上下文 → 生成最小补丁/审查意见 → 运行验证 → 生成结果摘要/PR 草稿 → 保留 trace 与评测记录**

这里的“输入任务”优先只支持四类：

1. **CI 失败修复**
2. **测试回归修复**
3. **PR 风险审查**
4. **小型依赖升级/兼容性修复**

这样做的原因很简单：**Anthropic** 明确建议先从**简单可控的 agent 设计**开始，先靠评测把单 Agent 跑稳，再逐步增加复杂度；**OpenAI** 也强调先用清晰的工作流和评测达成准确率目标，而不是一开始就堆复杂多 Agent。([Anthropic][2])

### **明确不做什么**

首版不要做：

* 通用聊天助手
* 浏览器自动化
* 多仓大规模联动
* 自动 merge / 自动发版
* 复杂 **multi-agent** 编排
* 全量向量库 + 大而全 RAG

原因不是这些不重要，而是它们会拖慢第一版落地。对 **vibe coding** 来说，最危险的不是技术难，而是边界失控。

---

## 2. 总体架构：先单主循环，后加子代理

### **核心原则**

首版采用：

**一个主 Orchestrator + 一组明确工具 + 一套可追踪状态**

暂时不引入真正的多 Agent 编排。

这个判断是当前最可靠的。**Claude Code Agent SDK** 的核心就是同一个自主 **agent loop**：模型评估提示、调用工具、接收结果、继续循环直到任务完成；**Anthropic** 也明确说，先用简单提示和评测，只有简单方法不够时再上多步 Agent 系统。([Claude][3])

### **建议的系统分层**

我建议按 6 层来做：

1. **Interface Layer**
   CLI + 简单 Web Trace 面板

2. **Orchestrator Layer**
   单主循环，负责状态推进

3. **Context Layer**
   **repo map**、文件选择、日志蒸馏、记忆加载

4. **Tool Layer**
   读写文件、符号查询、测试运行、diff、PR 草稿等

5. **Workspace Layer**
   本地仓 / **git worktree** / Docker 隔离工作区

6. **Eval & Trace Layer**
   每次运行的 **trace**、评分、回放

这种分层的依据很强：**aider** 证明了 **repo map** 对大仓理解很关键；**Claude Code** 文档把 **hooks、memory、subagents、MCP、Agent SDK** 都做成独立能力；**OpenHands SDK** 则明确把 **workspace** 抽象成既可本地也可 **ephemeral**。([Aider][4])

---

## 3. 最终推荐的核心工作流

首版只实现一条主链：

### **主链：Triage → Locate → Patch/Review → Verify → Summarize**

#### **Step 1: Triage**

输入：

* CI 日志
* PR diff
* issue 文本
* 失败测试输出

动作：

* 抽取第一层核心错误
* 消除重复堆栈和噪声
* 形成 **root cause candidates**

这里强烈建议加 **Hook-based Log Distillation**。
因为 **Claude Code hooks** 是**确定性**执行点，适合在模型看到日志前先做日志裁剪；官方文档明确说它们能提供 deterministic control，而不是依赖模型“记得去做”。([Claude][5])

#### **Step 2: Locate**

动作：

* 根据错误关键词、测试名、文件路径定位候选模块
* 查询 **repo map**
* 拉取有限数量的相关文件与符号摘要

这里必须采用 **repo map + selective read**，而不是“把整个仓库喂进去”。
**aider** 的 **repo map** 就是把全仓最重要的类、函数、签名压缩成简洁地图，帮助模型理解代码关系。([Aider][4])

#### **Step 3A: Patch**

如果任务类型是修复类：

* 生成**最小补丁**
* 输出变更摘要
* 进入 sandbox/worktree

#### **Step 3B: Review**

如果任务类型是审查类：

* 生成结构化 review comments
* 标注风险级别和证据

#### **Step 4: Verify**

动作：

* 跑测试 / lint / typecheck
* 记录通过与失败
* 回填到主循环

#### **Step 5: Summarize**

输出：

* 根因分析
* 修改文件
* 验证结果
* 风险等级
* PR 草稿或 review 报告
* trace 链接

---

## 4. 首版数据流设计

### **输入对象**

统一定义成 `TaskSpec`：

* `task_id`
* `task_type`
* `repo_path`
* `entry_artifacts`
  例如日志、PR diff、issue 文本
* `allowed_tools`
* `verification_commands`
* `risk_level`

### **运行时状态**

定义成 `RunState`：

* `task_spec`
* `step_index`
* `current_plan`
* `selected_context`
* `tool_history`
* `patch_artifact`
* `verification_result`
* `status`

### **可持久化对象**

定义成 4 类：

* `Session`
* `TraceEvent`
* `MemoryEntry`
* `EvalRecord`

这样设计，是为了后续自然支持 **durable execution**、中断恢复和人工介入。
如果后续你想升级成长会话系统，**LangGraph** 官方能力正好覆盖 **durable execution、human-in-the-loop、short-term/long-term memory**；但首版不建议先引入它，先用自己的轻量状态机更适合 **vibe coding**。([LangChain 文档][6])

---

## 5. 上下文工程：这是项目成败关键

这部分要严格按“分层”做。

### **L0：任务原始证据**

包括：

* 日志
* 测试输出
* PR diff
* issue 文本

### **L1：局部文件上下文**

直接读取少量候选文件的关键片段。

### **L2：仓库结构上下文**

由 **repo map** 提供：

* 关键模块
* 类/函数签名
* 调用关系摘要

### **L3：长期记忆**

包括：

* 项目构建命令
* 常见目录规范
* 团队风格约定
* 历史失败模式

这样做，和 **Claude Code memory** 的设计完全一致：它区分不同类型的记忆，并在每次会话开始加载；但官方也明确说，memory 是上下文，不是强制配置，所以你的实现也要保持“可更新、可回退、可覆盖”。([Claude][7])

### **首版建议**

首版先不要上向量数据库。
先做：

* **repo map**
* 简单关键词/路径检索
* 日志裁剪
* 长期记忆文件

这是最稳的。因为 **repo agent** 的第一瓶颈通常不是语义 embedding，而是上下文选择失控。

---

## 6. 工具系统：工具少而准

首版工具只保留 10 个以内。

### **必备工具**

1. `read_file`
2. `search_code`
3. `get_repo_map`
4. `apply_patch`
5. `run_command`
6. `run_tests`
7. `show_diff`
8. `write_review_report`
9. `write_pr_draft`
10. `load_memory`

### **工具设计原则**

**Anthropic** 在工具设计文章里讲得很明确：Agent 的效果高度依赖工具质量，工具应该先快速原型，再通过系统评测不断优化。你的工具接口要：

* 输入输出稳定
* 参数名清楚
* 错误返回结构化
* 不要把多个动作混进一个黑盒函数

这对 **vibe coding** 特别重要，因为大模型最怕调用“语义模糊”的工具。([Anthropic][8])

### **高风险工具**

这些动作必须走审批：

* 删除文件
* 批量替换
* 修改 CI workflow
* 外网请求
* 执行危险 shell

---

## 7. Workspace 与隔离策略

首版推荐两种运行模式：

### **模式 A：本地开发模式**

直接对本地 repo 操作，但必须通过 **git worktree** 或临时副本隔离。

### **模式 B：隔离执行模式**

使用 Docker 启动临时执行目录。

这个设计不是多余的。**OpenHands SDK** 明确支持两种工作区模式：本地工作区和 **ephemeral workspaces**；这正是后续从单机原型升级到企业部署的关键接口。([GitHub][9])

### **首版推荐**

先实现：

**本地 repo + git worktree**

原因：

* 实现简单
* 调试方便
* 非常适合 **vibe coding**
* 后续能平滑切到 Docker

---

## 8. Trace、评测与简历结果

这一块必须从 Day 1 做。

### **Trace 最少记录**

每一步记录：

* 当前状态
* 模型输入摘要
* 模型输出摘要
* 工具名
* 工具参数
* 工具结果
* token/cost
* 时间戳

这是因为 **OpenAI** 官方已经把 **trace → checks → score** 当成 Agent eval 的标准思路；他们也明确建议对工作流优先看 **trace**，再做评分。([OpenAI 开发者][10])

### **首版评测指标**

你只需要先做 6 个：

1. **Verification Pass Rate**
2. **First-pass Fix Rate**
3. **Localization Accuracy**
4. **Avg. Steps per Task**
5. **Tool Success Rate**
6. **Dangerous Action Block Rate**

### **任务集规模**

首版建议：

* 8 条 **CI 修复**
* 6 条 **回归修复**
* 4 条 **PR review**
* 2 条 **依赖升级**

总共 **20 条任务** 足够。

### **简历结果写法**

最后简历里不要写“做了个 Agent”，而要写成：

* 构建了 **20 条自建 repo maintenance 任务集**
* 按 **Verification Pass Rate / Localization Accuracy / Tool Success Rate** 评测
* 基于 **trace** 分析迭代上下文工程与工具设计

这种写法最稳。

---

## 9. 目录结构：适合直接开始 vibe coding

我建议直接按下面这个 repo 结构来：

```text
MendCode/
├─ app/
│  ├─ cli/
│  │  └─ main.py
│  ├─ api/
│  │  └─ server.py
│  ├─ orchestrator/
│  │  ├─ runner.py
│  │  ├─ planner.py
│  │  ├─ state.py
│  │  └─ policies.py
│  ├─ context/
│  │  ├─ repo_map.py
│  │  ├─ selector.py
│  │  ├─ log_distill.py
│  │  └─ memory.py
│  ├─ tools/
│  │  ├─ base.py
│  │  ├─ read_file.py
│  │  ├─ search_code.py
│  │  ├─ apply_patch.py
│  │  ├─ run_command.py
│  │  ├─ run_tests.py
│  │  ├─ show_diff.py
│  │  ├─ write_review.py
│  │  └─ write_pr.py
│  ├─ workspace/
│  │  ├─ manager.py
│  │  ├─ worktree.py
│  │  └─ sandbox.py
│  ├─ tracing/
│  │  ├─ schema.py
│  │  ├─ recorder.py
│  │  └─ exporter.py
│  ├─ eval/
│  │  ├─ dataset.py
│  │  ├─ graders.py
│  │  └─ runner.py
│  └─ models/
│     ├─ llm_client.py
│     └─ prompts.py
├─ data/
│  ├─ memories/
│  ├─ tasks/
│  └─ traces/
├─ tests/
│  ├─ unit/
│  └─ e2e/
├─ scripts/
│  ├─ build_repo_map.py
│  ├─ run_eval.py
│  └─ ingest_task.py
└─ README.md
```

这个结构的好处是：
**一层对应一类职责**，非常适合一边对话、一边让模型生成代码。

---

## 10. 开发顺序：最适合 vibe coding 的 4 个阶段

### **Phase 1：先打通最小闭环**

只做：

* CLI
* 单主循环
* 5 个工具
* trace 记录
* worktree 隔离
* 2 条 demo 任务

验收标准：

* 能读 repo
* 能定位错误
* 能改文件
* 能跑测试
* 能输出 trace

### **Phase 2：补上下文工程**

加入：

* **repo map**
* 日志蒸馏
* 记忆加载
* 基本政策闸门

验收标准：

* 同样任务上，步数下降或定位更稳

### **Phase 3：补评测框架**

加入：

* 自建任务集
* 评测 runner
* score 统计
* HTML/JSON trace 导出

验收标准：

* 能跑完整评测并产出结果表

### **Phase 4：补企业化接口**

加入：

* **MCP** 风格外部连接器
* PR 草稿
* review 报告
* Docker sandbox

验收标准：

* 支持一个真实团队维护场景

---

## 11. 你在 vibe coding 时最该坚持的开发纪律

这部分非常重要。

### **每一轮只让模型做一件事**

不要一次让它生成“整个项目”。

正确方式是：

* 先让它写 `state.py`
* 再写 `tools/base.py`
* 再写 `read_file.py`
* 再写 `runner.py`
* 再补单测

### **每个模块先写接口，再写实现**

因为接口稳定之后，后面重写实现成本很低。

### **每加一个能力，就加一个 acceptance test**

这是你避免“项目看起来越来越大，但越来越不稳”的唯一办法。

### **先 trace 后优化**

这和官方建议一致：Agent 优化优先看 **trace**，不要先凭感觉改 prompt。([OpenAI 开发者][10])

---

## 12. 最终版项目定义

最后我把这版方案压缩成一句话：

**MendCode** 是一个面向企业本地代码仓的 **CI / PR 维护闭环 Agent**。
首版采用 **单主循环 + 分层上下文 + 小而准的工具集 + worktree 隔离 + trace/eval 优先** 的路线；不追求花哨多 Agent，而追求**可评测、可调试、可扩展、可通过 vibe coding 稳定落地**。这一判断同时符合当前 **Claude Code Agent Loop / Hooks / Memory** 的公开设计思路、**aider repo map** 的上下文工程经验、**OpenHands** 的 workspace 抽象，以及 **OpenAI** 对 **trace + eval** 的工程化建议。([Claude][3])



[1]: https://code.claude.com/docs/en/overview?utm_source=chatgpt.com "Claude Code overview - Claude Code Docs"
[2]: https://www.anthropic.com/research/building-effective-agents?utm_source=chatgpt.com "Building Effective AI Agents"
[3]: https://code.claude.com/docs/en/agent-sdk/agent-loop?utm_source=chatgpt.com "How the agent loop works - Claude Code Docs"
[4]: https://aider.chat/docs/repomap.html?utm_source=chatgpt.com "Repository map"
[5]: https://code.claude.com/docs/en/hooks-guide?utm_source=chatgpt.com "Automate workflows with hooks - Claude Code Docs"
[6]: https://docs.langchain.com/oss/python/langgraph/overview?utm_source=chatgpt.com "LangGraph overview - Docs by LangChain"
[7]: https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"
[8]: https://www.anthropic.com/engineering/writing-tools-for-agents?utm_source=chatgpt.com "Writing effective tools for AI agents—using ..."
[9]: https://github.com/OpenHands/software-agent-sdk/?utm_source=chatgpt.com "OpenHands/software-agent-sdk"
[10]: https://developers.openai.com/blog/eval-skills?utm_source=chatgpt.com "Testing Agent Skills Systematically with Evals"
