# 前端全面中文化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在不修改后端、不改变现有布局与交互逻辑的前提下，将前端所有面向用户的英文文案改为简体中文。

**方案：** 直接替换现有 Vue 组件中的静态文案，不引入 i18n 依赖。API 路径、文件名、代码内容、实体类型及 `CODE_QA`、`TRACE_CHAIN`、`CHANGE_PLAN` 等后端技术标识保持原样；同步更新前端测试的文本断言。

**技术栈：** Vue 3、TypeScript、Vue Router、Vitest、Vue Test Utils

---

## 范围

修改：

- `frontend/src/components/AppNav.vue`
- `frontend/src/components/GraphPanel.vue`
- `frontend/src/components/ReferenceDialog.vue`
- `frontend/src/views/ProjectView.vue`
- `frontend/src/views/SearchView.vue`
- `frontend/src/views/GraphView.vue`
- `frontend/src/views/AgentChat.vue`
- 上述组件对应的 `frontend/src/**/__tests__/*.spec.ts`

不修改：

- `backend/` 下的任何文件
- 前后端 API、TypeScript 类型和路由路径
- 页面布局、配色、组件结构和交互流程
- LLM 提示词、Embedding 模型和中文检索逻辑
- 代码实体类型、任务类型、路径、文件名及源码展示内容

## 文案规则

- 使用自然、简洁的简体中文，不逐字硬译。
- `Project ID` 显示为“项目 ID”。
- `Agent`、`GraphRAG`、`API`、`HTTP` 等通用技术词保留英文。
- `CODE_QA`、`TRACE_CHAIN`、`CHANGE_PLAN` 等后端返回值原样展示。
- 加载状态统一使用“……”，例如“正在搜索……”。
- 错误信息说明用户可以检查的条件，不暴露内部异常。
- 示例问题改为中文，但只负责界面示例，不承诺中文检索效果。

---

### 任务 1：建立中文文案测试基线

**文件：**

- 修改：`frontend/src/__tests__/router.spec.ts`
- 修改：`frontend/src/components/__tests__/GraphPanel.spec.ts`
- 修改：`frontend/src/components/__tests__/ReferenceDialog.spec.ts`
- 修改：`frontend/src/views/__tests__/ProjectView.spec.ts`
- 修改：`frontend/src/views/__tests__/SearchView.spec.ts`
- 修改：`frontend/src/views/__tests__/GraphView.spec.ts`
- 修改：`frontend/src/views/__tests__/AgentChat.spec.ts`

- [ ] **步骤 1：安装锁文件中已声明的前端依赖**

运行：

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\frontend
npm.cmd install
```

预期：`vue-router` 出现在本地依赖树中，`package.json` 和
`package-lock.json` 不产生非预期修改。

- [ ] **步骤 2：把现有英文界面断言改为目标中文文案**

测试应覆盖导航、页面标题、主要按钮、加载状态、空状态、错误提示、
聊天欢迎语、示例问题、引用弹窗和图谱占位提示。

- [ ] **步骤 3：运行测试并确认测试先失败**

运行：

```powershell
npm.cmd test -- --run
```

预期：测试因组件仍显示英文而失败；不应出现模块缺失、TypeScript
解析失败或后端相关错误。

---

### 任务 2：中文化公共组件

**文件：**

- 修改：`frontend/src/components/AppNav.vue`
- 修改：`frontend/src/components/GraphPanel.vue`
- 修改：`frontend/src/components/ReferenceDialog.vue`

- [ ] **步骤 1：中文化导航与公共操作文案**

将项目、搜索、图谱、Agent 对话等导航文字，以及关闭、加载、空图谱、
引用详情、文件与行号等公共文案替换为中文。

- [ ] **步骤 2：保留技术数据原值**

不得翻译实体类型、关系类型、文件路径、限定名、源码和 API 返回值。

- [ ] **步骤 3：运行公共组件测试**

运行：

```powershell
npm.cmd test -- --run src/components src/__tests__/router.spec.ts
```

预期：公共组件与路由相关测试通过。

---

### 任务 3：中文化项目与搜索页面

**文件：**

- 修改：`frontend/src/views/ProjectView.vue`
- 修改：`frontend/src/views/SearchView.vue`

- [ ] **步骤 1：中文化项目管理页面**

覆盖标题、介绍、项目名称、项目路径、项目 ID、注册、扫描、构建向量
索引、统计信息、加载状态、成功提示、空状态和错误提示。

- [ ] **步骤 2：中文化代码搜索页面**

覆盖标题、说明、查询输入、搜索按钮、加载状态、无结果提示和错误提示；
搜索结果中的实体类型、来源、路径与代码保持原样。

- [ ] **步骤 3：运行项目与搜索页面测试**

运行：

```powershell
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts src/views/__tests__/SearchView.spec.ts
```

预期：两个页面的测试全部通过。

---

### 任务 4：中文化图谱与 Agent 页面

**文件：**

- 修改：`frontend/src/views/GraphView.vue`
- 修改：`frontend/src/views/AgentChat.vue`

- [ ] **步骤 1：中文化图谱页面**

覆盖标题、说明、查询条件、搜索按钮、图例、节点与边计数、节点详情、
加载状态、空状态及错误提示。

- [ ] **步骤 2：中文化 Agent 对话页面**

覆盖标题、说明、恢复会话、发送按钮、欢迎语、证据为空提示、不确定性
标题、错误提示和示例问题。用户与 Agent 的真实回答内容保持原样。

- [ ] **步骤 3：运行图谱与 Agent 页面测试**

运行：

```powershell
npm.cmd test -- --run src/views/__tests__/GraphView.spec.ts src/views/__tests__/AgentChat.spec.ts
```

预期：两个页面的测试全部通过。

---

### 任务 5：完整验证与变更边界检查

**文件：**

- 验证：`frontend/src/`
- 验证：`frontend/package.json`
- 验证：`frontend/package-lock.json`

- [ ] **步骤 1：扫描残留的用户可见英文**

运行：

```powershell
rg -n "Project|Search|Graph|Restore|Send|Loading|Unable|No indexed|Select|File|Lines" frontend/src --glob "*.vue"
```

预期：结果仅包含明确需要保留的技术词，其他面向用户的英文均已中文化。

- [ ] **步骤 2：运行完整前端测试**

运行：

```powershell
npm.cmd test -- --run
```

预期：全部前端测试通过。

- [ ] **步骤 3：运行生产构建**

运行：

```powershell
npm.cmd run build
```

预期：TypeScript 检查和 Vite 构建成功；允许保留 Cytoscape 大分块警告。

- [ ] **步骤 4：确认没有修改后端**

运行：

```powershell
git diff --name-only
git diff --check
```

预期：本次中文化只涉及 `frontend/` 文件和本计划文件；不存在
`backend/` 修改，也不存在空白错误。

- [ ] **步骤 5：交付审阅**

汇总中文化范围、测试结果、构建结果和仍保留的英文技术标识。未经用户
单独确认，不提交、不推送，也不执行浏览器视觉检查。
