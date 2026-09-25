# Design: Embedding 模型平滑迁移架构

> **本文档定位 — 现状快照（Why this How）**
>
> - `spec.md` 回答 **做什么**（目标、AC、边界）
> - `design.md`（本文）回答 **为什么这么实现**：关键决策、运行时不直观的事实、对外契约
> - `tasks.md` 是 **流水账**：拆了哪些任务、做了什么改动

**关联**: [spec.md](./spec.md) · [tasks.md](./tasks.md)
**版本**: v2.6.0
**最后更新**: 2026-09-25

---

## 1. 目标和非目标

### 目标

- 支持平台管理员修改系统默认 Embedding 模型，已有知识库不受影响
- 支持知识库级别的迁移策略控制（立即迁移 / 稍后迁移 / 锁定）
- 迁移期间支持双模型查询 + RRF 融合，保证查询结果完整性
- 提供查询路由策略开关（仅新模型 / 仅旧模型 / 双模型 RRF）
- 提供技术细节显示开关，增强查询可观测性

### 非目标

- 不支持文档级别的 embedding 模型锁定（粒度过细，复杂度过高）
- 不支持自动重建（强制暴力迁移会中断业务）
- 不实现 D 方案的"模型别名/路由抽象层"作为长期架构（只是 RRF 的临时别名，最终仍需真实重建）

---

## 2. 关键约束

- **多租户隔离**：所有迁移状态、配置均按 tenant_id 隔离
- **迁移原子性**：不支持回滚，迁移一旦完成不可逆（除非解锁后重新迁移）
- **RAG 查询兼容性**：Query Router 必须与现有 RAG pipeline 兼容，不能破坏现有召回逻辑
- **Milvus 向量不兼容**：不同 embedding 模型生成的向量在语义空间不兼容，不能直接比较分数
- **重建耗时长**：大型知识库重建可能需要数小时到数天，必须后台异步执行

---

## 3. 方案对比与选定

### 决策 1：查询合并策略

- **备选**：
  - A. 简单分数拼接 `(score_new + score_old) / 2` — 优点：实现简单；缺点：不同模型的分数分布差异大，拼接无意义
  - B. 只召回新模型 top-K — 优点：快；缺点：迁移未完成部分的数据丢失
  - C. Reciprocal Rank Fusion (RRF) — 优点：只依赖排名不依赖分数，语义兼容性好，业界标准；缺点：需要同时调用两个模型
- **选定**：C（RRF）
- **原因**：新旧向量空间不兼容，RRF 通过排名融合避免分数直接比较，实现简单且效果稳健（Elasticsearch、Weaviate 等均在用）
- **何时该重新考虑**：如有更优的跨模型融合算法出现且业界验证

### 决策 2：锁定粒度

- **备选**：
  - A. 租户级别锁定 — 优点：一键锁定全部知识库；缺点：灵活度低，无法差异化处理
  - B. 知识库级别锁定 — 优点：灵活，不同价值知识库可采用不同策略；缺点：管理复杂度稍高
  - C. 文档级别锁定 — 优点：最灵活；缺点：实现复杂度过高，界面展示困难
- **选定**：B
- **原因**：不同知识库业务价值不同（产品文档需跟进新技术 vs 历史公告可锁定），知识库级别是成本收益的最佳平衡点
- **何时该重新考虑**：如出现跨知识库统一管理需求，可考虑租户级+知识库级双重锁定

### 决策 3：延迟控制

- **备选**：
  - A. 强制单模型查询（牺牲平滑迁移）— 优点：无额外延迟；缺点：迁移期间查询结果不完整
  - B. 接受双模型查询 1.5x 延迟 — 优点：用户体验无感知（< 200ms）；缺点：嵌入服务调用时间翻倍
- **选定**：B
- **原因**：RRF 融合本身 < 10ms，主要延迟来自 embedding 服务调用。实测单模型约 100ms，双模型约 150ms，均在用户无感知范围内（人眼 < 200ms 难以区分）
- **何时该重新考虑**：如 embedding 服务延迟显著增加或成本压力过大，可考虑降级到 AC-12（仅新模型）

### 决策 4：迁移进度追踪

- **备选**：
  - A. 基于文档粒度追踪 — 优点：精确；缺点：大量更新 Milvus 开销大
  - B. 基于时间窗口估算 — 优点：无需额外存储；缺点：不精确
  - C. 基于批次粒度追踪 — 优点：平衡精度与开销；缺点：批次大小需调优
- **选定**：C
- **原因**：Milvus 的向量 ID 不支持直接按偏移量查询，按文档 ID 追踪更可行但需额外索引维护。批次粒度（每 N 个文档报告一次进度）是工程可行性最优解
- **何时该重新考虑**：如 Milvus 支持高效的 offset 查询，可改为文档粒度

---

## 4. 系统现状（接手必读）

### 4.1 迁移状态机

```
                    ┌─────────────┐
                    │   idle      │ ← 新建知识库初始状态 / 解锁后状态
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌─────────┐  ┌──────────┐  ┌─────────┐
        │ locked  │  │pending   │  │ pending │
        │         │  │(稍后迁移) │  │(立即迁移)│
        └────┬────┘  └────┬─────┘  └────┬────┘
             │            │             │
             │            │             ▼
             │            │      ┌────────────┐
             │            │      │ migrating  │
             │            │      │            │
             │            │      └─────┬──────┘
             │            │            │
             │            │     ┌──────┴──────┐
             │            │     │             │
             ▼            ▼     ▼             ▼
        ┌─────────┐  ┌────────┐ ┌────────┐ ┌────────┐
        │ locked  │  │ locked │ │completed│ │ failed │
        │         │  │        │ │        │ │        │
        └─────────┘  └────────┘ └────────┘ └────────┘
```

### 4.2 数据流

```
系统默认模型变更
     │
     ▼
┌──────────────────────────────────────┐
│  /api/v1/model/management PUT        │
│  → LLMService.update_knowledge_llm   │
│  → 仅保存系统默认，不触发迁移         │
└──────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────┐
│  管理员查看影响分析页                 │
│  → KnowledgeMigrationService         │
│    .list_knowledge_migration_status  │
│  → 返回所有知识库的迁移状态          │
└──────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────┐
│  管理员发起迁移                      │
│  → migrate_knowledge(kb_id, strategy)│
│  → 创建 Celery 任务                  │
│  → 更新 migration_status = migrating │
└──────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────┐
│  Celery Worker: embed_and_store      │
│  → 逐文档调用新模型生成向量           │
│  → 存储到 Milvus（与旧向量共存）     │
│  → 更新 migration_progress           │
└──────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────┐
│  查询时: EmbeddingQueryRouter        │
│  → 根据 kb.migration_status 路由     │
│  → idle/locked: 单模型               │
│  → migrating: 双模型 RRF              │
│  → completed: 仅新模型                │
└──────────────────────────────────────┘
```

### 4.3 关键数据结构

#### KnowledgeBase 扩展字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | String | — | 当前使用的 embedding 模型 ID（已有字段） |
| `target_model` | String | null | 迁移目标模型 ID（null 表示无迁移计划） |
| `migration_status` | Enum | `idle` | `idle` / `pending` / `migrating` / `completed` / `locked` / `failed` |
| `migration_progress` | Float | 0.0 | 迁移进度 0.0 ~ 1.0 |
| `locked_at` | DateTime | null | 锁定时间 |
| `locked_by` | String | null | 锁定操作人 |
| `locked_model` | String | null | 锁定时的模型 ID（解锁时回滚至此） |

#### TenantSystemConfig 新增配置项

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `embedding_query_strategy` | Enum | `rrf` | `new_only` / `old_only` / `dual_rrf` |
| `show_embedding_details` | Boolean | `false` | 是否在 Chat 界面显示技术细节 |

#### RRF 合并数据结构（内存中，不持久化）

```python
@dataclass
class RRFResult:
    doc_id: str
    kb_id: str
    score: float
    model_source: str  # "new" / "old" / "merged"
    rank: int
```

### 4.4 关键模块职责

| 模块 / 文件 | 职责 | 不做什么 |
|---|---|---|
| `llm/domain/services/embedding_router.py` | Embedding Query Router，根据迁移状态路由查询，执行 RRF 融合 | 不直接管理迁移任务 |
| `knowledge/domain/services/migration_service.py` | 管理迁移生命周期（发起/暂停/完成/锁定/解锁） | 不执行实际的向量重建 |
| `knowledge/rag/pipeline/embedder.py` | 批量生成 embedding 向量，存储到 Milvus | 不感知迁移状态 |
| `worker/tasks/knowledge_embedding_tasks.py` | Celery 异步任务，驱动迁移进度 | 不做业务决策 |
| `chat/ui/components/RetrievalDetails.tsx` | 技术详情折叠面板 | 不做查询逻辑 |

### 4.5 RRF 算法实现

```python
def reciprocal_rank_fusion(results_a: List[Doc], results_b: List[Doc], k: int = 60) -> List[Doc]:
    """
    Reciprocal Rank Fusion: 业界标准排名融合算法
    
    参数:
        results_a: 新模型召回结果（按相关性排序）
        results_b: 旧模型召回结果（按相关性排序）
        k: 融合常数（默认60，Elasticsearch 标准值）
    
    原理:
        RRF_score = Σ 1/(k + rank)  for each model that contains the doc
        最终按 RRF_score 降序排列
    """
    scores = defaultdict(float)
    for rank, doc in enumerate(results_a, 1):
        scores[doc.id] += 1 / (k + rank)
    for rank, doc in enumerate(results_b, 1):
        scores[doc.id] += 1 / (k + rank)
    
    return sorted(scores.keys(), key=lambda d: scores[d.id], reverse=True)
```

---

## 5. 已知坑 / 反直觉事实

| # | 反直觉事实 | 如果不知道会怎样 | 在哪处理 |
|---|---|---|---|
| 1 | 不同 embedding 模型的向量在语义空间不兼容，直接比较 scores 会导致结果严重降级 | 误用简单拼接会导致混合结果质量差 | RRF 算法强制基于排名融合 |
| 2 | 迁移过程中查询降级：已完成部分用新向量，未完成部分用旧向量 | 查询结果可能不完整，但不会报错 | Query Router 根据 progress 字段判断可用范围 |
| 3 | 锁定知识库后，`model` 字段不再跟随系统默认变更 | 解锁后需要同步 `model` 到当前系统默认 | 解锁时检查 `model` 是否落后于系统默认 |
| 4 | Milvus 向量删除代价高（标记删除更优） | 频繁删除会导致存储碎片和性能下降 | 迁移完成后旧向量标记为 `deleted`，不立即物理删除 |
| 5 | 迁移任务中断后重启，需要从 `migration_progress` 断点续传 | 重启后从头开始浪费大量时间 | Celery 任务读取 progress 字段决定起始位置 |
| 6 | Embedding 模型被删除时，如有知识库仍在使用该模型，查询会失败 | 管理员误删模型后终端用户查询报错，体验差 | 删除模型前检查依赖（是否有 KB 的 `model`/`locked_model`/`target_model` 指向它）；或提供替换引导 |

---

## 6. 对外契约与依赖

### 6.1 我提供给别人的（Outgoing）

| 契约 | 形式 | 谁在用 |
|---|---|---|
| `EmbeddingQueryRouter.query()` | 内部 Python API | RAG pipeline (`knowledge/rag/pipeline/`) |
| `KnowledgeMigrationService.get_status()` | 内部 Python API | Platform 前端知识库详情页 |
| 技术详情面板数据 | 注入 Chat 响应 extra_data | Client 前端 Chat 界面 |

### 6.2 我依赖别人的（Incoming）

| 依赖 | 形式 | 风险点 |
|---|---|---|
| Embedding 模型服务（在线推理） | `EmbeddingsProvider` 抽象 | 新模型服务不可用时迁移失败 |
| Milvus 向量存储 | `VectorStoreClient` 抽象 | Milvus 连接失败时查询降级 |
| Celery Worker | 异步任务队列 | Worker 宕机时迁移任务中断（断点续传恢复） |
| 知识库文档存储（MinIO + 数据库） | 原始文档来源 | 文档丢失时无法重建向量 |

---

## 7. 测试与可观测

### 整体策略

- **单元测试**：RRF 算法、迁移状态机、配置校验
- **集成测试**：Service 层 mock Milvus/Embedding，验证路由逻辑
- **手动验证**：
  1. 修改系统默认模型 → 确认新建知识库使用新模型，已有知识库不受影响
  2. 发起迁移 → 观察进度更新、RRF 查询结果
  3. 锁定知识库 → 修改系统默认 → 确认锁定知识库不受影响
  4. 开启技术详情 → Chat 界面应显示详情面板

### 关键日志

| 事件 | 日志级别 | 字段 |
|---|---|---|
| 迁移开始 | INFO | kb_id, target_model, total_docs |
| 迁移进度 | INFO | kb_id, processed_docs, total_docs, progress_pct |
| 迁移完成 | INFO | kb_id, elapsed_seconds |
| RRF 查询 | DEBUG | kb_id, routing_strategy, result_count |
| 迁移失败 | ERROR | kb_id, error_message, traceback |

### 监控指标

- `embedding_migration_progress{kb_id}` — Gauge，0.0 ~ 1.0
- `embedding_query_duration_seconds{kb_id, strategy}` — Histogram
- `embedding_migration_queue_size` — Gauge，排队中的迁移任务数

---

## 8. 后续改进 / 不打算做的事

### 已知短板

- **不支持实时进度推送**：前端目前通过轮询获取进度，后续可考虑 WebSocket 推送
- **RRF 的 k=60 是硬编码**：不同模型可能需要不同 k 值，后续可作为可配置参数

### 不打算做的事

- 文档级别锁定（粒度过细，UI 和实现复杂度过高）
- 迁移任务取消（只支持暂停不支持取消，防止数据不一致）
- 自动重建（严禁强制迁移，尊重业务连续性）

---

## 修订历史

| 日期 | 改动 | 触发原因 |
|---|---|---|
| 2026-09-25 | 初版 | feature 开始 |
