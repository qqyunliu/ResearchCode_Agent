---

# ResearchCode-Agent 4周开发计划

## 一、一个月版本目标

项目定位为：

> 面向高校实验室数十万行科研代码库的轻量级代码理解与辅助开发 Agent。

核心链路：

```text
代码库扫描
  ↓
代码解析与实体入库
  ↓
向量检索 + 轻量 GraphRAG
  ↓
Agent 问答
  ↓
前后端接口链路追踪
  ↓
简单修改规划
```

---

# 二、本版本保留与砍掉的功能

## 2.1 必做功能

| 功能        | 说明                                             |
| --------- | ---------------------------------------------- |
| 项目扫描      | 输入本地项目路径，扫描前端、后端、算法模块代码                        |
| 文件统计      | 统计文件数、代码行数、语言分布                                |
| Java 解析   | 抽取 Spring Boot Controller、Service、方法、API       |
| Vue 解析    | 抽取前端页面、axios/request API 调用                    |
| Python 解析 | 抽取算法模块中的类、函数、入口方法                              |
| 实体入库      | 保存文件、类、方法、API、前端请求等实体                          |
| 关系入库      | 保存前端请求 API、后端 API 定义、Controller 调用 Service 等关系 |
| 向量检索      | 对代码实体生成 embedding，支持语义检索                       |
| 关键词检索     | 支持文件名、函数名、字段名、API 路径检索                         |
| 混合检索      | 融合向量检索与关键词检索                                   |
| Agent 问答  | 基于 RAG 回答代码库相关问题                               |
| 接口链路追踪    | 展示前端页面 → API → Controller → Service 的链路        |
| 简单修改规划    | 根据需求输出可能涉及的文件、修改点和风险点                          |

---

## 2.2 明确不做的功能

| 不做功能            | 理由                                          |
| --------------- | ------------------------------------------- |
| 用户登录 / 权限系统     | 面试展示版不需要多用户管理                               |
| 完整 Memory 机制    | 一个月内优先跑通核心链路，不做长期记忆                         |
| Skill 自动沉淀      | 需要真实任务数据积累，当前不适合做                           |
| 多模型调度           | 当前单模型即可完成问答、规划和总结                           |
| Celery 异步队列     | 数十万行代码可以先用同步任务或 FastAPI BackgroundTasks     |
| Redis           | 当前会话和任务状态可直接放内存或数据库                         |
| Elasticsearch   | 关键词检索先用 SQLite LIKE / FTS5 实现               |
| Neo4j 强依赖       | 本版本先用 code_entities + code_relations 表模拟图查询 |
| 自动修改代码          | 只输出修改建议，不直接写入代码                             |
| 自动生成 Git commit | 风险高，且不是核心展示点                                |
| 完整代码 Review     | 本版本只做简单修改规划和风险提示                            |
| 自动运行测试          | 不同实验室项目适配成本高，暂不做                            |
| 复杂图谱可视化         | 只展示核心调用链，不做完整知识图谱浏览器                        |

---

# 三、简化技术栈

## 3.1 推荐技术栈

| 层级        | 技术选型                                                    | 作用                                       |
| --------- | ------------------------------------------------------- | ---------------------------------------- |
| 前端        | Vue3 + TypeScript + Element Plus                        | 管理项目、展示问答、展示链路                           |
| 后端        | FastAPI                                                 | 提供扫描、解析、检索、Agent API                     |
| 数据库       | SQLite                                                  | 存储项目、文件、实体、关系、对话记录                       |
| 向量库       | Qdrant                                                  | 存储代码实体 embedding                         |
| 图结构       | SQLite 表模拟                                              | 用 code_entities + code_relations 实现轻量图查询 |
| 代码解析      | Python ast + 正则 + 可选 tree-sitter                        | 抽取 Java/Vue/Python 代码实体                  |
| Embedding | sentence-transformers 或 OpenAI-compatible embedding API | 生成代码块向量                                  |
| LLM       | OpenAI-compatible API                                   | Agent 问答、修改规划                            |
| 前端代码展示    | highlight.js / Monaco Editor                            | 展示引用代码片段                                 |
| 链路图展示     | Cytoscape.js                                            | 展示前后端接口调用链                               |

---

## 3.2 最小后端依赖

```txt
fastapi
uvicorn
sqlalchemy
pydantic
python-dotenv
qdrant-client
sentence-transformers
openai
loguru
```

如果使用 SQLite FTS5，可不引入 Elasticsearch。

---

## 3.3 最小前端依赖

```txt
vue
vue-router
pinia
axios
element-plus
highlight.js
cytoscape
```

---

# 四、核心数据表设计

## 4.1 projects

```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    status TEXT DEFAULT 'created',
    created_at TEXT,
    updated_at TEXT
);
```

---

## 4.2 code_files

```sql
CREATE TABLE code_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT,
    line_count INTEGER,
    file_hash TEXT,
    created_at TEXT
);
```

---

## 4.3 code_entities

```sql
CREATE TABLE code_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_id INTEGER,
    entity_type TEXT NOT NULL,
    name TEXT,
    qualified_name TEXT,
    file_path TEXT,
    start_line INTEGER,
    end_line INTEGER,
    content TEXT,
    metadata TEXT
);
```

---

## 4.4 code_relations

```sql
CREATE TABLE code_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    source_id INTEGER,
    target_id INTEGER,
    source_name TEXT,
    target_name TEXT,
    relation_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    metadata TEXT
);
```

---

## 4.5 conversations

```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

---

## 4.6 messages

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    role TEXT,
    content TEXT,
    references_json TEXT,
    created_at TEXT
);
```

---

# 五、后端目录结构

```text
backend/
 ├── app/
 │   ├── main.py
 │   ├── api/
 │   │   ├── project_api.py
 │   │   ├── search_api.py
 │   │   ├── graph_api.py
 │   │   └── agent_api.py
 │   ├── core/
 │   │   ├── config.py
 │   │   └── database.py
 │   ├── models/
 │   │   ├── project.py
 │   │   ├── code_file.py
 │   │   ├── code_entity.py
 │   │   ├── code_relation.py
 │   │   └── conversation.py
 │   ├── services/
 │   │   ├── scanner.py
 │   │   ├── index_service.py
 │   │   └── change_plan_service.py
 │   ├── parsers/
 │   │   ├── java_parser.py
 │   │   ├── vue_parser.py
 │   │   ├── python_parser.py
 │   │   └── relation_builder.py
 │   ├── rag/
 │   │   ├── chunk_builder.py
 │   │   ├── embedding_service.py
 │   │   ├── vector_store.py
 │   │   ├── keyword_search.py
 │   │   ├── hybrid_search.py
 │   │   └── context_builder.py
 │   ├── graph/
 │   │   ├── graph_query_service.py
 │   │   └── graph_rag_retriever.py
 │   ├── agent/
 │   │   ├── planner.py
 │   │   ├── tool_registry.py
 │   │   ├── executor.py
 │   │   └── prompts.py
 │   └── utils/
 │       ├── hash_utils.py
 │       ├── path_utils.py
 │       └── api_normalizer.py
 ├── requirements.txt
 └── README.md
```

---

# 六、前端目录结构

```text
frontend/
 ├── src/
 │   ├── api/
 │   │   ├── project.ts
 │   │   ├── search.ts
 │   │   ├── graph.ts
 │   │   └── agent.ts
 │   ├── views/
 │   │   ├── ProjectView.vue
 │   │   ├── SearchView.vue
 │   │   ├── GraphView.vue
 │   │   └── AgentChat.vue
 │   ├── components/
 │   │   ├── ProjectStats.vue
 │   │   ├── CodeReference.vue
 │   │   ├── GraphPanel.vue
 │   │   └── ChatMessage.vue
 │   ├── router/
 │   ├── stores/
 │   └── utils/
 └── package.json
```

---

# 七、4周开发排期总览

| 周次    | 核心目标                      | 最终交付                            |
| ----- | ------------------------- | ------------------------------- |
| 第 1 周 | 项目初始化 + 代码扫描 + 实体抽取       | 能扫描真实项目并抽取 Java/Vue/Python 代码实体 |
| 第 2 周 | 向量索引 + 关键词检索 + 基础 RAG     | 能通过自然语言检索代码并回答基础问题              |
| 第 3 周 | 轻量 GraphRAG + 接口链路追踪      | 能展示前端页面到后端接口的调用链                |
| 第 4 周 | Agent 整合 + 修改规划 + 前端 Demo | 能完整演示问答、链路追踪、修改规划               |

---

# 八、第 1 周：项目初始化与代码解析入库

## 目标

实现：

```text
项目路径输入
  ↓
扫描源码文件
  ↓
识别语言
  ↓
抽取代码实体
  ↓
写入数据库
```

---

## 第 1 周交付物

| 交付物          | 验收标准                             |
| ------------ | -------------------------------- |
| FastAPI 后端骨架 | `/health` 正常返回                   |
| SQLite 数据库   | 自动创建核心表                          |
| 项目创建接口       | 能保存项目名称和 root_path               |
| 项目扫描接口       | 能扫描指定路径下源码文件                     |
| Java 解析器     | 能抽取 Controller、Service、方法、后端 API |
| Vue 解析器      | 能抽取前端 API 请求                     |
| Python 解析器   | 能抽取类和函数                          |
| 关系构建器        | 能建立 REQUESTS_API、DEFINES_API 等关系 |
| 项目统计接口       | 能返回文件数、代码行数、API 数量等              |

---

## 第 1 周每日任务

### Day 1：后端基础工程

| 任务            | Codex 可执行描述                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| 创建 FastAPI 项目 | 创建 FastAPI 后端项目，包含 app/main.py、app/api、app/core、app/models、app/services、app/parsers、app/rag、app/agent 目录 |
| 配置数据库         | 使用 SQLAlchemy + SQLite，提供数据库连接、Session 管理和初始化方法                                                          |
| 实现健康检查        | 实现 GET /health 接口，返回 `{ "status": "ok" }`                                                                |
| 建立基础模型        | 创建 Project、CodeFile、CodeEntity、CodeRelation、Conversation、Message ORM 模型                                  |

---

### Day 2：项目扫描器

| 任务                | Codex 可执行描述                                                                      |
| ----------------- | -------------------------------------------------------------------------------- |
| 编写 ProjectScanner | 输入项目 root_path，递归扫描源码文件                                                          |
| 添加忽略规则            | 忽略 `.git`、`node_modules`、`dist`、`build`、`target`、`__pycache__`、`.idea`、`.vscode` |
| 识别语言              | 根据后缀识别 `.java`、`.py`、`.vue`、`.js`、`.ts`、`.sql`、`.xml`、`.yml`、`.json`             |
| 统计文件信息            | 统计 file_path、language、line_count、file_hash                                       |
| 实现扫描接口            | 实现 POST `/api/projects/{project_id}/scan`，扫描结果写入 code_files 表                    |

---

### Day 3：Java 后端解析器

| 任务            | Codex 可执行描述                                                                                                      |
| ------------- | ---------------------------------------------------------------------------------------------------------------- |
| 编写 JavaParser | 解析 Java 文件中的 class、method                                                                                        |
| 抽取 Spring API | 识别 `@RestController`、`@Controller`、`@RequestMapping`、`@GetMapping`、`@PostMapping`、`@PutMapping`、`@DeleteMapping` |
| 拼接完整 API      | 将 class 级 `@RequestMapping` 和 method 级 Mapping 合并为完整路径                                                           |
| 生成实体          | 将 Java class、method、backend_api 写入 code_entities                                                                 |
| 保存 metadata   | backend_api 的 metadata 中保存 method、path、controller_class、handler_method                                           |

---

### Day 4：Vue 前端请求解析器

| 任务            | Codex 可执行描述                                                |
| ------------- | ---------------------------------------------------------- |
| 编写 VueParser  | 解析 `.vue`、`.js`、`.ts` 文件                                   |
| 识别 axios 请求   | 支持 `axios.get`、`axios.post`、`axios.put`、`axios.delete`     |
| 识别 request 封装 | 支持 `request.get`、`request.post`、`request({ url, method })` |
| 抽取 API 信息     | 获取 method、url、file_path、line_number                        |
| 生成实体          | 写入 `frontend_api_call` 类型实体                                |

---

### Day 5：Python 算法模块解析器

| 任务              | Codex 可执行描述                                            |
| --------------- | ------------------------------------------------------ |
| 编写 PythonParser | 使用 Python ast 模块解析 `.py` 文件                            |
| 抽取类             | 抽取 class name、start_line、end_line、content              |
| 抽取函数            | 抽取 function name、arguments、start_line、end_line、content |
| 抽取 import       | 可选抽取 import 关系                                         |
| 写入实体            | 写入 `python_class`、`python_function` 类型实体               |

---

### Day 6：关系构建器

| 任务           | Codex 可执行描述                                                 |
| ------------ | ----------------------------------------------------------- |
| 编写 API 归一化工具 | 将 `/api/user/{id}`、`/api/user/:id`、`/api/user/123` 统一为可比较形式 |
| 建立前后端 API 关系 | 匹配 frontend_api_call 和 backend_api，建立 `REQUESTS_API` 关系     |
| 建立 API 定义关系  | backend_api 关联对应 java_method，建立 `DEFINES_API` 关系            |
| 建立文件包含关系     | file 关联 class/method/api，建立 `CONTAINS` 关系                   |

---

### Day 7：统计与验收

| 任务     | Codex 可执行描述                                              |
| ------ | -------------------------------------------------------- |
| 实现统计接口 | GET `/api/projects/{project_id}/stats`                   |
| 返回统计信息 | 文件总数、代码总行数、Java/Vue/Python 文件数、后端 API 数、前端 API 调用数、匹配关系数 |
| 修复解析问题 | 用真实实验室项目跑一遍，修复明显解析失败情况                                   |
| 准备样例项目 | 准备一个小型 demo 代码库，用于稳定测试                                   |

---

# 九、第 2 周：向量检索、关键词检索与基础 RAG

## 目标

实现：

```text
代码实体
  ↓
生成代码块
  ↓
生成 embedding
  ↓
写入 Qdrant
  ↓
混合检索
  ↓
RAG 问答
```

---

## 第 2 周交付物

| 交付物                  | 验收标准                          |
| -------------------- | ----------------------------- |
| CodeChunkBuilder     | 能从 code_entities 生成可向量化 chunk |
| EmbeddingService     | 能生成文本向量                       |
| QdrantVectorStore    | 能创建 collection、写入、检索          |
| KeywordSearchService | 能按关键词检索代码实体                   |
| HybridSearchService  | 能融合向量检索和关键词检索                 |
| RAG Context Builder  | 能构造带文件路径和行号的上下文               |
| 基础代码问答接口             | 能回答“某个接口在哪里实现”                |

---

## 第 2 周每日任务

### Day 8：代码 Chunk 构建

| 任务                  | Codex 可执行描述                                                                           |
| ------------------- | ------------------------------------------------------------------------------------- |
| 编写 CodeChunkBuilder | 从 code_entities 读取 class、method、backend_api、frontend_api_call、python_function         |
| 构造 chunk            | 每个 chunk 包含 entity_id、name、entity_type、file_path、start_line、end_line、content、metadata |
| 构造 searchable_text  | 拼接实体名称、类型、文件路径、注释、代码内容                                                                |
| 限制 chunk 长度         | 过长 content 截断到固定字符数，避免 embedding 输入过大                                                 |

---

### Day 9：Embedding 服务

| 任务                  | Codex 可执行描述                           |
| ------------------- | ------------------------------------- |
| 编写 EmbeddingService | 支持 sentence-transformers 本地 embedding |
| 支持 API 模式           | 支持 OpenAI-compatible embedding API    |
| 配置切换                | 通过 `.env` 控制 embedding provider       |
| 批量生成                | 支持批量文本输入，返回向量列表                       |

---

### Day 10：Qdrant 向量库

| 任务                   | Codex 可执行描述                                                 |
| -------------------- | ----------------------------------------------------------- |
| 编写 QdrantVectorStore | 实现 create_collection、upsert_chunks、search                   |
| collection 命名        | 使用 `project_{project_id}_code_chunks`                       |
| payload 设计           | 保存 entity_id、file_path、entity_type、name、start_line、end_line |
| 建立索引接口               | POST `/api/projects/{project_id}/build-vector-index`        |

---

### Day 11：关键词检索

| 任务                      | Codex 可执行描述                           |
| ----------------------- | ------------------------------------- |
| 编写 KeywordSearchService | 基于 SQLite 查询 code_entities            |
| 支持字段                    | name、qualified_name、file_path、content |
| 支持 API 搜索               | 对 `/api/xxx` 路径做优先匹配                  |
| 实现接口                    | POST `/api/search/keyword`            |

---

### Day 12：混合检索

| 任务                     | Codex 可执行描述                            |
| ---------------------- | -------------------------------------- |
| 编写 HybridSearchService | 同时调用向量检索和关键词检索                         |
| 结果去重                   | 根据 entity_id 去重                        |
| 分数融合                   | vector_score 占 0.7，keyword_score 占 0.3 |
| 实现接口                   | POST `/api/search/hybrid`              |

---

### Day 13：RAG 上下文构造

| 任务                   | Codex 可执行描述                                       |
| -------------------- | ------------------------------------------------- |
| 编写 RagContextBuilder | 将检索结果转换成 LLM 上下文                                  |
| 添加引用信息               | 每段上下文包含 file_path、start_line、end_line、entity_type |
| 限制上下文长度              | 根据字符数限制截断低分片段                                     |
| 编写 Prompt            | 要求模型必须基于上下文回答，不能编造文件                              |

---

### Day 14：基础代码问答

| 任务            | Codex 可执行描述                          |
| ------------- | ------------------------------------ |
| 实现 LLMClient  | 封装 OpenAI-compatible chat completion |
| 实现 code_qa 服务 | 检索 → 构造上下文 → 调用 LLM → 返回答案           |
| 实现接口          | POST `/api/agent/code-qa`            |
| 返回 references | 返回引用文件、行号、实体类型、相关原因                  |

---

# 十、第 3 周：轻量 GraphRAG 与前后端接口链路追踪

## 目标

实现：

```text
前端页面 / API / 用户问题
  ↓
定位前端请求
  ↓
匹配后端 API
  ↓
定位 Controller 方法
  ↓
推断 Service 调用
  ↓
返回链路图和自然语言解释
```

---

## 第 3 周交付物

| 交付物                     | 验收标准                              |
| ----------------------- | --------------------------------- |
| API 定义关系                | backend_api 能关联 java_method       |
| 前后端请求关系                 | frontend_api_call 能关联 backend_api |
| Controller-Service 调用关系 | 能抽取简单 service.method 调用           |
| GraphQueryService       | 能基于实体关系做 BFS 查询                   |
| GraphRAG Retriever      | 能结合检索结果扩展一到两跳关系                   |
| 链路查询接口                  | 能返回 nodes 和 edges                 |
| 前端链路图页面                 | 能展示 API 调用链                       |

---

## 第 3 周每日任务

### Day 15：完善 API 定义关系

| 任务             | Codex 可执行描述                                              |
| -------------- | -------------------------------------------------------- |
| 增强 JavaParser  | backend_api metadata 中保存 controller_class、handler_method |
| 建立 DEFINES_API | backend_api 指向 java_method                               |
| 建立 CONTAINS    | java_class 指向 java_method                                |
| 修复重复实体         | 避免同一 API 或 method 重复入库                                   |

---

### Day 16：Controller 到 Service 调用关系

| 任务              | Codex 可执行描述                            |
| --------------- | -------------------------------------- |
| 抽取注入字段          | 识别 `@Autowired`、`@Resource`、构造函数注入     |
| 提取 service 调用   | 从 Java 方法体中识别 `xxxService.method(...)` |
| 建立 CALLS_METHOD | Controller method 指向 Service method    |
| 添加置信度           | 精确匹配 0.8，名称推断 0.6                      |

---

### Day 17：图查询服务

| 任务                   | Codex 可执行描述                                                   |
| -------------------- | ------------------------------------------------------------- |
| 编写 GraphQueryService | 基于 code_entities 和 code_relations 查询图                         |
| 实现 BFS               | 输入 entity_id、max_depth、relation_types，返回节点和边                  |
| 实现 API chain 查询      | 输入 method + api_path，返回 frontend → api → controller → service |
| 结果格式统一               | 返回 nodes、edges、references                                     |

---

### Day 18：链路查询接口

| 任务                 | Codex 可执行描述                                                          |
| ------------------ | -------------------------------------------------------------------- |
| 实现 api-chain 接口    | GET `/api/graph/api-chain?project_id=&method=&api_path=`             |
| 实现 search-chain 接口 | POST `/api/graph/search-chain`，支持自然语言 query                          |
| query 解析           | 对 query 先做 hybrid_search，再根据命中实体扩展图关系                                |
| 返回图数据              | nodes 包含 label、type、file_path、line；edges 包含 relation_type、confidence |

---

### Day 19：GraphRAG Retriever

| 任务                   | Codex 可执行描述                               |
| -------------------- | ----------------------------------------- |
| 编写 GraphRagRetriever | 先 HybridSearch，再 GraphQueryService 扩展邻居节点 |
| 一跳二跳扩展               | 直接命中实体优先，一跳关系其次，二跳关系最后                    |
| 去重                   | 按 entity_id 去重                            |
| 添加 relation_reason   | 说明实体为什么被加入上下文                             |

---

### Day 20：前端链路展示

| 任务              | Codex 可执行描述                  |
| --------------- | ---------------------------- |
| 创建 GraphView 页面 | 提供搜索框，输入 API 或功能关键词          |
| 接入接口            | 调用 `/api/graph/search-chain` |
| 使用 Cytoscape.js | 展示 nodes 和 edges             |
| 节点详情            | 点击节点展示文件路径、行号、代码片段           |

---

### Day 21：链路问答接口

| 任务          | Codex 可执行描述                    |
| ----------- | ------------------------------ |
| 实现 trace 服务 | GraphRAG 检索 → 构造链路上下文 → LLM 总结 |
| 实现接口        | POST `/api/agent/trace`        |
| 回答格式        | 必须包含链路、涉及文件、无法确定项              |
| 返回图数据       | 同时返回 graph_nodes、graph_edges   |

---

# 十一、第 4 周：Agent 整合、修改规划与前端 Demo

## 目标

整合成统一 Agent：

```text
用户输入问题
  ↓
Planner 判断任务类型
  ↓
调用对应工具链
  ↓
生成答案
  ↓
前端展示回答、引用、链路图
```

---

## 第 4 周交付物

| 交付物                | 验收标准                                            |
| ------------------ | ----------------------------------------------- |
| SimpleAgentPlanner | 能区分 CODE_QA、TRACE_CHAIN、CHANGE_PLAN             |
| ToolRegistry       | 统一注册 hybrid_search、graph_search、read_entity 等工具 |
| AgentExecutor      | 根据任务类型执行不同工具链                                   |
| ChangePlanService  | 能输出新增字段/接口的修改规划                                 |
| 统一 Agent Chat 接口   | 一个接口支持问答、链路追踪、修改规划                              |
| AgentChat 前端页面     | 能展示回答、引用和链路图                                    |
| README             | 包含启动方式、功能说明、Demo 问题                             |
| Demo 样例问题          | 至少准备 5 个稳定演示问题                                  |

---

## 第 4 周每日任务

### Day 22：Agent Planner

| 任务                    | Codex 可执行描述                         |
| --------------------- | ----------------------------------- |
| 编写 SimpleAgentPlanner | 输入 question，输出 task_type            |
| 规则分类                  | “在哪里/哪个文件/怎么实现” → CODE_QA           |
| 规则分类                  | “数据从哪里来/链路/调用关系/前后端” → TRACE_CHAIN  |
| 规则分类                  | “新增/修改/字段/接口/需要改哪些文件” → CHANGE_PLAN |
| 兜底分类                  | 无法判断时归为 CODE_QA                     |

---

### Day 23：Tool Registry 与 Executor

| 任务               | Codex 可执行描述                                                    |
| ---------------- | -------------------------------------------------------------- |
| 编写 ToolRegistry  | 注册 hybrid_search、graph_search、read_entity、get_related_entities |
| 编写 AgentExecutor | 根据 task_type 选择工具链                                             |
| CODE_QA 工具链      | hybrid_search → rag_context → llm                              |
| TRACE_CHAIN 工具链  | graph_rag_retriever → llm                                      |
| CHANGE_PLAN 工具链  | hybrid_search → related_entities → change_plan_prompt → llm    |

---

### Day 24：修改规划服务

| 任务                   | Codex 可执行描述                                   |
| -------------------- | --------------------------------------------- |
| 编写 ChangePlanService | 输入需求，提取字段名、功能名、接口名等关键词                        |
| 检索相关文件               | 检索 Entity、DTO、Mapper、Controller、Vue 页面、API 文件 |
| 生成修改清单               | 输出可能涉及文件、修改建议、不确定点                            |
| 编写 Prompt            | 禁止编造未检索到的文件；不确定内容必须标注“需要确认”                   |

---

### Day 25：统一 Agent Chat 接口

| 任务     | Codex 可执行描述                                         |
| ------ | --------------------------------------------------- |
| 实现统一接口 | POST `/api/agent/chat`                              |
| 请求参数   | project_id、question、conversation_id 可选              |
| 响应字段   | answer、task_type、references、graph_nodes、graph_edges |
| 保存对话   | 将用户问题和助手回答写入 messages 表                             |

---

### Day 26：前端 Agent Chat 页面

| 任务               | Codex 可执行描述                                   |
| ---------------- | --------------------------------------------- |
| 创建 AgentChat.vue | 实现对话输入框和回答展示区域                                |
| 接入 chat 接口       | 调用 `/api/agent/chat`                          |
| 展示 references    | 文件路径、行号、实体类型、相关原因                             |
| 展示链路图            | 如果返回 graph_nodes 和 graph_edges，则展示 GraphPanel |
| 代码片段弹窗           | 点击引用后展示对应代码内容                                 |

---

### Day 27：前端项目管理与检索页面

| 任务             | Codex 可执行描述                            |
| -------------- | -------------------------------------- |
| 创建 ProjectView | 添加项目路径、触发扫描、展示统计信息                     |
| 创建 SearchView  | 输入关键词或自然语言，展示 hybrid_search 结果         |
| 添加示例问题         | 在 AgentChat 左侧放置 5 个可点击示例问题            |
| 打通路由           | `/projects`、`/search`、`/graph`、`/chat` |

---

### Day 28：测试、修复与文档

| 任务         | Codex 可执行描述                  |
| ---------- | ---------------------------- |
| 编写 README  | 包含项目背景、技术栈、启动方式、接口说明、Demo 步骤 |
| 准备 demo 问题 | 至少 5 个稳定问题                   |
| 修复前后端 bug  | 确保扫描、索引、问答、链路追踪可完整跑通         |
| 记录限制       | 写清楚当前版本限制和后续扩展点              |
| 准备截图       | 保存项目统计、问答、链路图、修改规划结果截图       |

---

# 十二、核心 API 清单

## 12.1 项目相关

```http
POST /api/projects
POST /api/projects/{project_id}/scan
GET  /api/projects/{project_id}/stats
```

---

## 12.2 索引相关

```http
POST /api/projects/{project_id}/build-vector-index
GET  /api/projects/{project_id}/index-status
```

---

## 12.3 检索相关

```http
POST /api/search/keyword
POST /api/search/vector
POST /api/search/hybrid
```

---

## 12.4 图查询相关

```http
GET  /api/graph/api-chain
POST /api/graph/search-chain
```

---

## 12.5 Agent 相关

```http
POST /api/agent/code-qa
POST /api/agent/trace
POST /api/agent/chat
```

---

# 十三、最终 Demo 必须跑通的 5 个问题

| 类型     | 示例问题                           | 期望能力                                |
| ------ | ------------------------------ | ----------------------------------- |
| 代码定位   | 告警列表接口在哪里实现？                   | 返回 Controller、Service、相关文件          |
| 链路追踪   | 告警趋势图的数据从哪里来？                  | 返回前端页面 → API → Controller → Service |
| 前端接口分析 | 设备状态页面调用了哪些后端接口？               | 返回前端文件和 API 列表                      |
| 算法模块定位 | 异常检测算法入口函数在哪里？                 | 返回 Python 函数和文件                     |
| 修改规划   | 新增 risk_score 风险评分字段，需要修改哪些文件？ | 返回可能涉及文件、修改建议、不确定点                  |

---

# 十四、开发优先级

## 必须优先完成

```text
1. 项目扫描
2. Java/Vue/Python 解析
3. 实体与关系入库
4. 向量索引
5. 混合检索
6. 基础 Agent 问答
7. 前后端接口链路追踪
```

---

## 时间不够时可以降级

| 功能                    | 降级方式                        |
| --------------------- | --------------------------- |
| 前端图谱展示                | 先用列表展示链路，不画图                |
| Python 解析             | 只抽取函数，不抽取 import 关系         |
| Controller-Service 调用 | 只做一跳 service.method 识别      |
| 修改规划                  | 只输出涉及文件和修改建议，不生成代码          |
| 对话历史                  | 不做 conversation，仅单轮问答       |
| Qdrant                | 如果部署麻烦，先用本地 FAISS 或内存向量索引替代 |

---

# 十五、最终验收标准

一个月结束时，系统应至少满足：

| 能力      | 验收方式                              |
| ------- | --------------------------------- |
| 能接入真实项目 | 输入 root_path 后成功扫描                |
| 能统计代码库  | 返回文件数、代码行数、API 数量                 |
| 能抽取 API | 后端 Spring API 和前端 request 均可识别    |
| 能做代码检索  | 输入自然语言返回相关代码片段                    |
| 能做代码问答  | Agent 回答中包含文件路径和行号                |
| 能做链路追踪  | 返回前端 → API → Controller → Service |
| 能做修改规划  | 新增字段/接口时返回涉及文件和修改建议               |
| 能前端演示   | 页面可操作，不只停留在接口层                    |
