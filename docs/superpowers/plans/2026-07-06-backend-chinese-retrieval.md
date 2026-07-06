# 后端中文检索与同语言回答实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 使用智谱 `embedding-3` 提升中英跨语言代码检索能力，通过 LLM 将中文问题改写为英文代码检索词，并保证 Agent 使用原始问题的语言回答。

**方案：** 将智谱 `embedding-3`（1024 维）设为默认 Embedding 配置，扩展现有 OpenAI 兼容 Provider 以传递向量维度。新增独立查询改写服务，只对包含中文的查询调用一次现有 LLM；改写结果只进入混合检索，原始问题继续用于 Agent 路由、最终回答与会话保存。

**技术栈：** Python 3.11、FastAPI、Pydantic v2、OpenAI Python SDK、智谱 `embedding-3`、Qdrant、pytest

---

## 范围与约束

实现：

- 智谱 `embedding-3` 默认 API 配置与 1024 维请求。
- 中文检测与 LLM 英文检索词改写。
- 改写失败后回退原始查询。
- 混合检索同时对向量检索和关键词检索使用改写结果。
- Agent 路由、最终回答和会话保存继续使用原始问题。
- Code QA、Trace、Change Plan 使用与问题相同的语言回答。
- 中文路由、查询改写、检索和原问题保留测试。
- 一个显式运行、只发送少量固定文本的智谱 Embedding 验证脚本。
- README、后端 README 和 `.env.example` 配置说明。

不实现：

- 本地 Embedding 模型与自动回退。
- 双 Qdrant 索引。
- 前端修改。
- 查询改写缓存、批处理任务或后台队列。
- 自动翻译代码内容。
- 自动执行多次真实 LLM 或 Embedding 调用。

## 配置约定

```dotenv
RCA_EMBEDDING_PROVIDER=api
RCA_EMBEDDING_MODEL=embedding-3
RCA_EMBEDDING_API_KEY=
RCA_EMBEDDING_BASE_URL=https://open.bigmodel.cn/api/paas/v4
RCA_EMBEDDING_DIMENSIONS=1024
```

Embedding Key 与 `RCA_LLM_API_KEY` 分开管理。真实测试只能从环境或
`backend/.env` 读取 Key，不得在命令、日志、测试快照或提交内容中输出。

更换模型或维度后，已有项目必须重新构建向量索引。

---

### 任务 1：支持智谱 Embedding 配置与自定义维度

**文件：**

- 修改：`backend/app/core/config.py`
- 修改：`backend/app/core/dependencies.py`
- 修改：`backend/app/retrieval/embedding_service.py`
- 修改：`backend/.env.example`
- 测试：`backend/tests/unit/test_embedding_service.py`
- 创建：`backend/tests/unit/test_dependencies.py`

- [ ] **步骤 1：为 API Embedding 维度编写失败测试**

在 `test_embedding_service.py` 中验证：

```python
provider = OpenAICompatibleEmbeddingProvider(
    model_name="embedding-3",
    api_key="test-key",
    base_url="https://open.bigmodel.cn/api/paas/v4",
    dimensions=1024,
    client=fake_client,
)

provider.embed_documents(["中文告警", "alert API"])
provider.embed_query("告警接口在哪里")
```

期望 Fake Client 收到：

```python
{
    "model": "embedding-3",
    "input": ["中文告警", "alert API"],
    "dimensions": 1024,
}
```

以及：

```python
{
    "model": "embedding-3",
    "input": ["告警接口在哪里"],
    "dimensions": 1024,
}
```

- [ ] **步骤 2：运行单元测试并确认失败**

运行：

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\backend
.\.venv\python.exe -m pytest tests\unit\test_embedding_service.py -v
```

预期：因 Provider 尚不接受 `dimensions` 而失败。

- [ ] **步骤 3：实现可选 `dimensions` 参数**

修改 `OpenAICompatibleEmbeddingProvider`：

- 构造器接收 `dimensions: int | None`；
- 维度必须大于零；
- 仅当维度不为空时向 `client.embeddings.create` 传递
  `dimensions`；
- 文档和查询使用完全相同的模型与维度。

- [ ] **步骤 4：将智谱设为默认配置**

在 `Settings` 和 `.env.example` 中设置：

```python
embedding_provider = "api"
embedding_model = "embedding-3"
embedding_base_url = "https://open.bigmodel.cn/api/paas/v4"
embedding_dimensions = 1024
```

`get_embedding_service()` 将 `embedding_dimensions` 传给 API Provider。
保留 `local` Provider 代码兼容性，但它不再是默认模式，也不参与自动回退。

- [ ] **步骤 5：运行配置与 Embedding 单元测试**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_embedding_service.py tests\unit\test_dependencies.py -v
```

预期：全部通过，且不访问网络。

---

### 任务 2：实现中文查询改写服务

**文件：**

- 创建：`backend/app/retrieval/query_rewriter.py`
- 修改：`backend/app/core/dependencies.py`
- 测试：`backend/tests/unit/test_query_rewriter.py`

- [ ] **步骤 1：编写中文检测与改写失败测试**

测试以下行为：

```python
assert contains_cjk("告警 API 在哪里") is True
assert contains_cjk("Where is AlertController?") is False
```

中文问题调用 Fake LLM，并返回精简英文检索词：

```python
result = rewriter.rewrite(
    "告警列表 API 在哪里实现？",
)
assert result == "alert list API implementation controller service"
```

系统提示词必须要求：

- 只返回一行英文检索词；
- 保留 `risk_score`、`AlertController`、`/api/alerts` 等代码标识；
- 不回答问题；
- 不添加 Markdown 或解释。

- [ ] **步骤 2：编写英文旁路和失败回退测试**

验证：

- 英文查询原样返回且不调用 LLM；
- 空白改写结果回退原问题；
- LLM 抛出异常时回退原问题；
- 多行响应被规范化为单行；
- 首尾空白被删除。

- [ ] **步骤 3：运行测试并确认失败**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_query_rewriter.py -v
```

预期：模块不存在或接口尚未实现。

- [ ] **步骤 4：实现 `LlmQueryRewriter`**

公开接口：

```python
class QueryRewriter(Protocol):
    def rewrite(self, query: str) -> str: ...


class LlmQueryRewriter:
    def __init__(self, llm: LlmClient) -> None: ...
    def rewrite(self, query: str) -> str: ...
```

实现只负责中文检测、调用、规范化与安全回退，不记录问题内容或 Key。

- [ ] **步骤 5：注册依赖并运行测试**

在 `dependencies.py` 中增加缓存的 `get_query_rewriter()`，复用
`get_llm_client()`。运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_query_rewriter.py tests\unit\test_dependencies.py -v
```

预期：全部通过。

---

### 任务 3：将改写查询接入混合检索

**文件：**

- 修改：`backend/app/retrieval/hybrid_search.py`
- 修改：`backend/app/api/search_api.py`
- 修改：`backend/app/api/graph_api.py`
- 修改：`backend/app/api/agent_api.py`
- 测试：`backend/tests/unit/test_hybrid_search.py`
- 测试：`backend/tests/integration/test_hybrid_search_api.py`

- [ ] **步骤 1：编写改写查询流向失败测试**

构造 Fake Rewriter：

```python
class FakeRewriter:
    def rewrite(self, query: str) -> str:
        assert query == "告警列表接口在哪里"
        return "alert list API controller"
```

验证：

- `embed_query()` 收到英文改写结果；
- `keyword_search.search()` 收到英文改写结果；
- Rewriter 仍收到原始中文；
- 返回值融合逻辑和 0.7/0.3 权重不变。

- [ ] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_hybrid_search.py -v
```

预期：`HybridSearchService` 尚不接受 Rewriter。

- [ ] **步骤 3：为混合检索增加可注入 Rewriter**

`HybridSearchService`：

- 接受 `rewriter: QueryRewriter | None`；
- 没有 Rewriter 时保持现有行为，避免破坏纯单元测试；
- 有 Rewriter 时只改写一次；
- 改写结果同时进入向量与关键词分支；
- 项目 ID、limit、融合权重和响应结构不变。

- [ ] **步骤 4：在所有真实混合检索入口注入 Rewriter**

更新：

- `/api/search/hybrid`
- `/api/graph/search-chain`
- `/api/agent/code-qa`
- `/api/agent/trace`
- `/api/agent/chat`

关键词专用接口 `/api/search/keyword` 保持不变，不引入 LLM 调用。

- [ ] **步骤 5：运行单元与集成测试**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_hybrid_search.py tests\integration\test_hybrid_search_api.py tests\integration\test_keyword_search.py -v
```

预期：全部通过，关键词专用接口仍不需要 LLM。

---

### 任务 4：保证最终回答使用原问题及同一种语言

**文件：**

- 修改：`backend/app/services/code_qa_service.py`
- 修改：`backend/app/services/trace_service.py`
- 修改：`backend/app/services/change_plan_service.py`
- 测试：`backend/tests/unit/test_code_qa_service.py`
- 测试：`backend/tests/unit/test_trace_service.py`
- 测试：`backend/tests/unit/test_change_plan_service.py`
- 测试：`backend/tests/unit/test_agent_chat_service.py`

- [ ] **步骤 1：编写同语言提示词失败测试**

中文问题场景验证三个系统提示词均包含等价约束：

```text
Respond in the same language as the user's original question.
```

Change Plan 的 JSON 字段名保持英文，但 `summary`、`reason`、
`suggested_changes`、`risks`、`uncertainties` 的文本内容使用原问题语言。

- [ ] **步骤 2：编写原始问题保留测试**

使用中文原问题和返回英文检索词的 Fake Rewriter，验证：

- 检索服务收到的有效查询为英文；
- Code QA、Trace、Change Plan 的最终 LLM user prompt 仍含完整中文原问题；
- `AgentChatService` 保存的用户消息仍是中文原文；
- Planner 仍根据中文原文选择任务类型；
- 不把英文改写词保存成用户消息。

- [ ] **步骤 3：运行测试并确认失败**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_code_qa_service.py tests\unit\test_trace_service.py tests\unit\test_change_plan_service.py tests\unit\test_agent_chat_service.py -v
```

预期：同语言系统提示词断言失败。

- [ ] **步骤 4：更新三类 Agent 系统提示词**

只添加语言约束，不降低以下现有保障：

- 只能依据索引证据；
- 引用必须直接支持结论；
- 不得编造文件、符号、API 或关系；
- 缺失证据必须明确表达；
- Change Plan 必须返回结构化 JSON。

- [ ] **步骤 5：运行服务层测试**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_code_qa_service.py tests\unit\test_trace_service.py tests\unit\test_change_plan_service.py tests\unit\test_agent_chat_service.py -v
```

预期：全部通过。

---

### 任务 5：补齐中文路由与端到端检索测试

**文件：**

- 修改：`backend/tests/unit/test_agent_planner.py`
- 修改：`backend/tests/integration/test_code_qa_api.py`
- 修改：`backend/tests/integration/test_trace_api.py`
- 修改：`backend/tests/integration/test_agent_chat_api.py`
- 修改：`backend/tests/integration/test_week4_acceptance.py`

- [ ] **步骤 1：扩展中文 Planner 用例**

至少覆盖：

| 中文问题 | 预期任务 |
| --- | --- |
| `告警列表 API 在哪里实现？` | `CODE_QA` |
| `告警趋势数据的调用链是什么？` | `TRACE_CHAIN` |
| `增加 risk_score 字段需要修改哪些文件？` | `CHANGE_PLAN` |
| `修改前后端调用链会影响哪些文件？` | `CHANGE_PLAN` 优先 |

- [ ] **步骤 2：增加中文 API 检索链测试**

通过 Fake Rewriter、Fake Embedding 和 Fake LLM 验证：

```text
中文请求
  -> Planner 使用中文原文
  -> Rewriter 产生英文检索词
  -> Hybrid Search 使用英文检索词
  -> 最终提示词包含中文原文
  -> 响应与会话保存中文问题
```

测试不得访问真实网络或读取开发者 `.env`。

- [ ] **步骤 3：分组运行中文相关测试**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_agent_planner.py tests\unit\test_query_rewriter.py tests\unit\test_hybrid_search.py -v
.\.venv\python.exe -m pytest tests\integration\test_code_qa_api.py tests\integration\test_trace_api.py tests\integration\test_agent_chat_api.py -v
.\.venv\python.exe -m pytest tests\integration\test_week4_acceptance.py -v
```

预期：三组全部通过。

---

### 任务 6：增加受控的真实智谱 Embedding 验证

**文件：**

- 创建：`backend/scripts/check_embedding_api.py`
- 创建：`backend/tests/unit/test_check_embedding_api.py`

- [ ] **步骤 1：先为验证逻辑编写离线测试**

将相似度与响应检查写成可注入 Provider 的函数。Fake Provider 返回固定
1024 维向量，测试验证：

- 三个输入得到三个非空向量；
- 每个向量均为 1024 维；
- 中文“告警列表接口”和英文“alert list API”相似度高于无关文本；
- 输出只包含模型名、维度和相似度，不包含 Key。

- [ ] **步骤 2：运行离线脚本测试**

运行：

```powershell
.\.venv\python.exe -m pytest tests\unit\test_check_embedding_api.py -v
```

预期：全部通过，不访问网络。

- [ ] **步骤 3：实现显式验证脚本**

运行方式：

```powershell
.\.venv\python.exe -m scripts.check_embedding_api
```

脚本从 `Settings` 获取智谱配置，单次批量发送以下固定文本：

```text
告警列表接口
alert list API
database migration rollback
```

如果 Provider、模型、维度或 Key 不符合要求，脚本应在发请求前明确失败。

- [ ] **步骤 4：执行一次真实智谱测试**

这是本计划唯一授权的真实 Embedding 调用。运行前确认：

- `backend/.env` 已配置真实 `RCA_EMBEDDING_API_KEY`；
- 不打印 `.env`；
- 不在命令行传 Key；
- 不重复执行；
- 只记录模型、向量数量、维度和相似度。

预期：返回 3 个 1024 维向量，语义相关中英文文本的余弦相似度高于无关
文本。如果余额、网络或服务商错误导致失败，保留错误证据并停止，不循环
重试。

---

### 任务 7：更新文档并完成回归验证

**文件：**

- 修改：`README.md`
- 修改：`backend/README.md`
- 修改：`backend/.env.example`

- [ ] **步骤 1：更新配置与行为说明**

文档明确说明：

- 默认使用智谱 `embedding-3` 与 1024 维；
- 智谱接口需要独立 Embedding Key；
- 中文查询会增加一次 LLM 改写调用；
- 原始中文用于最终回答和会话保存；
- 英文查询不调用 Rewriter；
- 无本地 Embedding 回退；
- 服务不可用时关键词专用接口仍可使用；
- 改模型或维度必须重建索引；
- 真实 API 调用会产生费用。

- [ ] **步骤 2：运行完整后端测试**

运行：

```powershell
.\.venv\python.exe -m pytest
```

预期：全部测试通过；除已有预期跳过项外无失败。

- [ ] **步骤 3：运行覆盖率与编译检查**

运行：

```powershell
.\.venv\python.exe -m pytest --cov=app --cov-report=term-missing
.\.venv\python.exe -m compileall -q app scripts tests
```

预期：覆盖率不低于 80%，编译检查成功。

- [ ] **步骤 4：确认前端未被本任务修改**

记录任务开始前已有的前端未提交文件，并运行：

```powershell
git diff --name-only
git diff --check
```

预期：本任务新增差异只涉及 `backend/`、README 和本计划文件；不会覆盖或
撤销之前的前端中文化改动。

- [ ] **步骤 5：交付用户手动测试**

汇总：

- 配置变更；
- 中文改写与原问题保留机制；
- 自动测试、覆盖率和编译结果；
- 唯一一次真实智谱测试结果；
- 必须重建向量索引的提醒；
- 已知的费用、网络和隐私风险。

按用户要求保持未提交状态，等待手动测试。未经单独确认，不提交、不推送。
