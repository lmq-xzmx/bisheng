# Tasks: Embedding 模型平滑迁移架构

**关联规格**: [spec.md](./spec.md)
**版本**: v2.6.0

---

## 状态

| 步骤 | 状态 | 备注 |
|------|------|------|
| spec.md | ✅ 已评审 | 2026-09-25 |
| design.md | ✅ 已评审 | 2026-09-25 |
| tasks.md | ✅ 已拆解 | 2026-09-25 |
| Wave 1-6 实现 | ✅ 完成 | T001-T017 完成 |
| Wave 7 E2E | 🔲 待验证 | 手动验证阶段 |
| 合并 | 🔲 待合并 | PR 待创建 |

---

## Wave 1：数据库与基础设施（无外部依赖，可并行）

### T001: 数据库迁移脚本
**文件**: `src/backend/bisheng/core/database/alembic/versions/xxx_add_embedding_migration_fields.py`
**逻辑**:
- `KnowledgeBase` 表新增字段：`target_model` (VARCHAR null)、`migration_status` (ENUM default 'idle')、`migration_progress` (FLOAT default 0.0)、`locked_at` (DATETIME null)、`locked_by` (VARCHAR null)、`locked_model` (VARCHAR null)
- `TenantSystemConfig` 表新增配置项：`embedding_query_strategy` (ENUM default 'rrf')、`show_embedding_details` (BOOLEAN default false)
**约束**: 仅 DDL，不做数据迁移
**依赖**: 无

### T002: 更新 KnowledgeBase ORM 模型
**文件**: `src/backend/bisheng/knowledge/domain/models/knowledge.py`
**逻辑**:
- 在 `KnowledgeBase` SQLModel 中添加新字段
- 添加 `migration_status` 的 Enum 类 `MigrationStatus`
**依赖**: T001

### T003: RRF 算法实现
**文件**: `src/backend/bisheng/llm/domain/utils/rrf_fusion.py` (新建)
**逻辑**:
```python
def reciprocal_rank_fusion(results_a: List[RetrievedDoc], results_b: List[RetrievedDoc], k: int = 60) -> List[RetrievedDoc]
```
- 实现标准 RRF 算法
- 单元测试覆盖：相同文档排名、互斥文档排名、部分重叠排名
**覆盖 AC**: AC-08
**依赖**: 无

### T004: EmbeddingQueryRouter 实现
**文件**: `src/backend/bisheng/llm/domain/services/embedding_router.py` (新建)
**逻辑**:
- `EmbeddingQueryRouter.query(kb_id, query_text, strategy_override=None)`
- 根据 `kb.migration_status` 和 `tenant_config.embedding_query_strategy` 决定路由策略
- `idle/locked`: 单模型
- `migrating`: 双模型 RRF
- `completed`: 仅新模型
- `old_only` 配置: 忽略迁移状态，仅用 `model` 字段指向的模型
- `new_only` 配置: 忽略迁移状态，仅用 `target_model` 或当前系统默认
**覆盖 AC**: AC-08, AC-09, AC-10, AC-12, AC-13
**依赖**: T003

---

## Wave 2：后端 Domain Service 与配置

### T005: 错误码定义
**文件**: `src/backend/bisheng/common/errcode/knowledge_migration.py` (新建)
**逻辑**: 定义迁移相关错误码
- `EMBEDDING_MIGRATION_NOT_FOUND` (43xxx)
- `EMBEDDING_MIGRATION_ALREADY_LOCKED` (43xxx)
- `EMBEDDING_MIGRATION_TARGET_UNAVAILABLE` (43xxx)
- `EMBEDDING_MIGRATION_LOCKED_KB_CANNOT_MIGRATE` (43xxx)
**依赖**: 无

### T006: KnowledgeMigrationService 实现
**文件**: `src/backend/bisheng/knowledge/domain/services/migration_service.py` (新建)
**逻辑**:
- `get_migration_status(kb_id)` → 返回迁移状态、进度、预估时间
- `list_all_kb_migration_status(tenant_id)` → 返回所有知识库的迁移摘要
- `start_migration(kb_id, strategy)` → 发起迁移
- `pause_migration(kb_id)` → 暂停迁移
- `force_complete_migration(kb_id)` → 强制完成
- `lock_knowledge_base(kb_id)` → 锁定
- `unlock_knowledge_base(kb_id)` → 解锁
- `sync_with_system_default()` → 将系统默认模型同步到新建知识库（仅影响 `model=null` 的知识库）
**覆盖 AC**: AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-07
**依赖**: T002, T005

### T007: 更新 LLMService（移除危险同步逻辑）
**文件**: `src/backend/bisheng/llm/domain/services/llm.py`
**逻辑**: 确认 `update_knowledge_llm` 不再调用自动同步逻辑（已在 revert 中完成）
**验证**: 语法检查通过
**覆盖 AC**: AC-01
**依赖**: 无（已完成）

### T008: Tenant 配置读取/更新 API
**文件**: `src/backend/bisheng/llm/domain/services/llm_config_service.py` (新建或扩展)
**逻辑**:
- `get_embedding_query_strategy(tenant_id)` → 读取 `embedding_query_strategy`
- `set_embedding_query_strategy(tenant_id, strategy)` → 写入
- `get_show_embedding_details(tenant_id)` → 读取
- `set_show_embedding_details(tenant_id, value)` → 写入
**覆盖 AC**: AC-12, AC-13, AC-14
**依赖**: T001

---

## Wave 3：Celery 异步迁移任务

### T009: 迁移任务 Celery Task
**文件**: `src/backend/bisheng/worker/knowledge_embedding_tasks.py` (新建)
**逻辑**:
- `task_migrate_knowledge_base(kb_id)` → 异步执行向量重建
- 分批次处理文档（每批 100 条）
- 每批完成后更新 `migration_progress`
- 捕获异常时标记 `migration_status=failed`，记录错误日志
- 任务中断后重启可从 `migration_progress` 断点续传
**覆盖 AC**: AC-03, AC-15
**依赖**: T006, T004

### T010: 迁移进度更新逻辑
**文件**: 同 T009
**逻辑**:
- 预估重建时间计算：根据已完成的文档数和耗时，推算剩余时间
- 进度持久化：每批次写入数据库
- 状态流转：`pending` → `migrating` → `completed` 或 `failed`
**覆盖 AC**: AC-03
**依赖**: T009

---

## Wave 4：后端 API 层

### T011: 迁移管理 API 端点
**文件**: `src/backend/bisheng/knowledge/api/endpoints/migration.py` (新建)
**逻辑**:
- `GET /api/v1/knowledge/{kb_id}/migration` → 获取单个知识库迁移状态
- `GET /api/v1/knowledge/migration/summary` → 获取所有知识库迁移摘要
- `POST /api/v1/knowledge/{kb_id}/migration/start` → 发起迁移
- `POST /api/v1/knowledge/{kb_id}/migration/pause` → 暂停迁移
- `POST /api/v1/knowledge/{kb_id}/migration/complete` → 强制完成
- `POST /api/v1/knowledge/{kb_id}/migration/lock` → 锁定
- `POST /api/v1/knowledge/{kb_id}/migration/unlock` → 解锁
- 在 `knowledge/api/router.py` 注册路由
**覆盖 AC**: AC-02, AC-03, AC-04, AC-05, AC-06, AC-07
**依赖**: T006, T009

### T012: Tenant Embedding 配置 API
**文件**: `src/backend/bisheng/llm/api/endpoints/embedding_config.py` (新建)
**逻辑**:
- `GET /api/v1/embedding-config` → 获取 embedding 相关配置
- `PUT /api/v1/embedding-config` → 更新配置
- 包括 `embedding_query_strategy` 和 `show_embedding_details`
**覆盖 AC**: AC-12, AC-13, AC-14
**依赖**: T008

---

## Wave 5：前端 Platform（知识库管理页面）

### T013: 迁移影响分析页面
**文件**: `src/frontend/platform/src/pages/ModelManagement/components/MigrationImpact.tsx` (新建)
**逻辑**:
- 调用 `GET /api/v1/knowledge/migration/summary`
- 展示知识库列表：名称、文档数、预估重建时间、当前状态
- 每行操作按钮：「立即迁移」「稍后迁移」「锁定」
- 状态标签：🟡 待迁移 / 🔄 迁移中 / 🟢 已完成 / 🔒 已锁定
**手动验证**:
- 打开 /model/management
- 修改"知识库默认embedding模型"
- 验证影响分析列表正确显示
**覆盖 AC**: AC-01, AC-02
**依赖**: T011

### T014: 知识库详情页迁移状态面板
**文件**: `src/frontend/platform/src/pages/KnowledgeDetail/components/MigrationPanel.tsx` (新建)
**逻辑**:
- 调用 `GET /api/v1/knowledge/{kb_id}/migration`
- 展示进度条、预估完成时间
- 操作按钮：「暂停迁移」「强制完成」「锁定当前模型」
- 锁定状态显示：锁定时间、操作人
- **进度更新方式**：前端轮询（每 5 秒调用一次 GET API 刷新进度）
  - 注：本版本不支持 WebSocket 实时推送（见 design.md §8 后续改进）
**手动验证**:
- 进入知识库详情页
- 发起迁移
- 观察进度条实时更新
- 点击暂停/强制完成，验证状态变化
**覆盖 AC**: AC-03, AC-05, AC-06, AC-07
**依赖**: T011

### T015: Embedding 配置页面更新
**文件**: `src/frontend/platform/src/pages/ModelManagement/components/EmbeddingDefaultConfig.tsx` (扩展)
**逻辑**:
- 新增「查询路由策略」下拉选项：仅新模型 / 仅旧模型 / 双模型 RRF
- 新增「显示技术细节」开关
- 调用 `PUT /api/v1/embedding-config` 保存
**覆盖 AC**: AC-12, AC-13, AC-14
**依赖**: T012

---

## Wave 6：前端 Client（Chat 界面）

### T016: 技术详情折叠面板
**文件**: `src/frontend/client/src/components/RetrievalDetails/RetrievalDetails.tsx` (新建)
**逻辑**:
- 根据 `show_embedding_details` 配置决定是否渲染
- 从 Chat 响应 `extra_data.retrieval_details` 读取数据
- 展示：来源知识库、使用的 embedding 模型、检索文档数、匹配度
- 默认折叠，可展开查看
**手动验证**:
- 管理员开启「显示技术细节」
- 用户在 Client 提问
- 展开技术详情，验证数据正确
**覆盖 AC**: AC-11, AC-14
**依赖**: T012

### T017: Chat 响应数据注入
**文件**: `src/frontend/client/src/hooks/useRAGResponse.ts` (扩展)
**逻辑**:
- 在 RAG 响应中注入 `retrieval_details` 字段
- 调用 `EmbeddingQueryRouter` 时记录本次查询的路由策略和模型来源
- 格式化后塞入 `extra_data` 返回给前端
**覆盖 AC**: AC-11
**依赖**: T004

---

## Wave 7：集成与手动验证

### T018: 手动 E2E 验证
**手动验证步骤**:
1. 修改系统默认 embedding 模型 → 新建知识库使用新模型，已有知识库不受影响
2. 发起知识库迁移 → 观察进度更新，查询结果正常
3. 迁移过程中提问 → 技术详情显示双模型 RRF
4. 锁定知识库 → 修改系统默认 → 锁定知识库不受影响
5. 开启技术详情开关 → Chat 界面显示详情面板
6. 关闭技术详情开关 → Chat 界面不显示详情面板
7. 迁移中断（重启 Worker）→ 重启后从断点续传

**覆盖 AC**: 全部
**依赖**: T001-T017

---

## 实际偏差记录

> **只留一行指针**，论证在 design.md（决策 / 坑），这里不重复。
> 推翻已 ★ 确认的决策时，先停下与用户重新确认，再记录。

- T012 Tenant 配置：使用 `ConfigDao.insert_or_update_config` 复用现有配置表，未新建独立配置表
- 前端组件（MigrationImpact/MigrationPanel/EmbeddingDefaultConfig）：为基础 UI 结构，需集成到现有 ModelPage 页面中

---

## 实施时间线

| 日期 | 完成内容 |
|------|---------|
| 2026-09-25 | Wave 1-6 实现完成（T001-T017） |
| 2026-09-25 | T009 Celery 向量重建逻辑完善 |
| TBD | Wave 7 E2E 手动验证 |
| TBD | PR 合并 |
