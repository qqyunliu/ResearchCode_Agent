# Bounded Tool Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不引入自治重规划循环的前提下，让混合检索和图关系查询发生超时或异常时有限降级，并向最终响应暴露结构化不确定性。

**Architecture:** 在 `SearchHit` 和 `GraphRetrievalResult` 中携带检索警告，使故障信息沿现有调用链传播。`HybridSearchService` 隔离向量与关键词分支故障；`GraphRagRetriever` 和任务服务在图查询失败时保留直接召回证据。所有策略只尝试一次，不新增 LLM 调用、后台任务或前端改动。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、pytest、Qdrant Client、SQLAlchemy。

---

### Task 1: 混合检索分支隔离

**Files:**
- Modify: `backend/app/retrieval/types.py`
- Modify: `backend/app/retrieval/hybrid_search.py`
- Test: `backend/tests/unit/test_hybrid_search.py`

- [ ] **Step 1: 编写失败测试**

增加以下行为测试：

```python
def test_vector_failure_falls_back_to_keyword_hits() -> None:
    ...
    assert results[0].source == "keyword_fallback"
    assert results[0].uncertainties == (
        "Vector retrieval was unavailable; keyword-only fallback was used.",
    )


def test_keyword_failure_keeps_vector_hits() -> None:
    ...
    assert results[0].source == "vector_fallback"
    assert results[0].uncertainties == (
        "Keyword retrieval was unavailable; vector-only fallback was used.",
    )


def test_missing_vector_index_is_not_hidden_by_fallback() -> None:
    ...
    assert raised.value.code == "VECTOR_INDEX_NOT_FOUND"
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `.\.venv\python.exe -m pytest tests/unit/test_hybrid_search.py -q`

Expected: 新增测试因 `SearchHit.uncertainties` 不存在且检索异常未隔离而失败。

- [ ] **Step 3: 实现最小降级**

为 `SearchHit` 增加默认空元组字段：

```python
uncertainties: tuple[str, ...] = ()
```

在 `HybridSearchService.search` 中：

- 索引明确不存在时继续抛出 `VECTOR_INDEX_NOT_FOUND`；
- 捕获 Embedding/Qdrant 分支异常并继续关键词检索；
- 捕获关键词分支异常，在已有向量结果时继续返回；
- 两个分支均失败时抛出 `RETRIEVAL_UNAVAILABLE`；
- 使用 `dataclasses.replace` 标记 `keyword_fallback` 或 `vector_fallback` 及固定、不泄露内部异常细节的警告；
- 正常融合时合并来源结果携带的警告。

- [ ] **Step 4: 运行测试并确认绿灯**

Run: `.\.venv\python.exe -m pytest tests/unit/test_hybrid_search.py -q`

Expected: 文件内全部测试通过。

### Task 2: 图遍历失败保留直接召回

**Files:**
- Modify: `backend/app/rag/graph_retriever.py`
- Test: `backend/tests/unit/test_graph_retriever.py`

- [ ] **Step 1: 编写失败测试**

```python
def test_graph_failure_keeps_direct_hits_with_uncertainty() -> None:
    ...
    assert [result.entity_id for result in results] == [1]
    assert results[0].uncertainties == (
        "Graph relationship retrieval was unavailable; only direct search evidence was used.",
    )
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `.\.venv\python.exe -m pytest tests/unit/test_graph_retriever.py -q`

Expected: 图异常向外抛出，测试失败。

- [ ] **Step 3: 实现最小降级**

为 `GraphRetrievalResult` 增加默认空警告；直接结果继承 `SearchHit.uncertainties`。每个种子节点的 `graph.traverse` 失败时，保留直接结果并追加固定图检索警告，不进行重试。

- [ ] **Step 4: 运行测试并确认绿灯**

Run: `.\.venv\python.exe -m pytest tests/unit/test_graph_retriever.py -q`

Expected: 文件内全部测试通过。

### Task 3: 任务响应传播降级原因

**Files:**
- Modify: `backend/app/services/code_qa_service.py`
- Modify: `backend/app/services/trace_service.py`
- Modify: `backend/app/services/change_plan_service.py`
- Test: `backend/tests/unit/test_code_qa_service.py`
- Test: `backend/tests/unit/test_trace_service.py`
- Test: `backend/tests/unit/test_change_plan_service.py`

- [ ] **Step 1: 编写失败测试**

分别验证：

```python
assert "Vector retrieval was unavailable" in response.uncertainties
assert "Graph relationship retrieval was unavailable" in response.uncertainties
```

Trace 与 Change Plan 还需模拟最终 `expand_entities` 抛出 `TimeoutError`，确认服务继续构建直接证据上下文、调用一次回答 LLM，并返回空图及图扩展警告。

- [ ] **Step 2: 运行聚焦测试并确认红灯**

Run:

```powershell
.\.venv\python.exe -m pytest tests/unit/test_code_qa_service.py tests/unit/test_trace_service.py tests/unit/test_change_plan_service.py -q
```

Expected: 降级警告尚未进入响应，或图扩展异常仍向外抛出。

- [ ] **Step 3: 实现响应传播**

- Code QA 从命中项汇总、去重 `uncertainties`；
- Trace 与 Change Plan 从 `GraphRetrievalResult` 汇总警告；
- `expand_entities` 失败时使用空 `GraphResult`，追加“图扩展不可用”警告；
- 所有正常、修复成功和验证失败响应均保留这些警告；
- 不把图工具故障描述为静态索引中没有对应关系类型。

- [ ] **Step 4: 运行聚焦测试并确认绿灯**

运行 Step 2 命令，预期全部通过。

### Task 4: 回归验证与最小审查

**Files:**
- Review all files modified in Tasks 1-3

- [ ] **Step 1: 运行相关测试**

```powershell
.\.venv\python.exe -m pytest tests/unit/test_hybrid_search.py tests/unit/test_graph_retriever.py tests/unit/test_code_qa_service.py tests/unit/test_trace_service.py tests/unit/test_change_plan_service.py tests/unit/test_agent_executor.py tests/unit/test_agent_chat_service.py -q
```

- [ ] **Step 2: 运行后端全量测试和编译检查**

```powershell
.\.venv\python.exe -m pytest -q
.\.venv\python.exe -m compileall -q app tests
```

- [ ] **Step 3: 审查变更**

```powershell
git diff --check
git diff -- backend/app backend/tests
```

检查：没有无限重试、没有新增 LLM 调用、没有吞掉 `VECTOR_INDEX_NOT_FOUND`、没有在响应中泄露底层异常文本、没有前端改动。

本次不提交、不推送，等待用户审核工作区变更。
