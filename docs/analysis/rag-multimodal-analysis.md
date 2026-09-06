# BiSheng RAG 与多模态检索成熟度分析

> 分析日期：2026-08-27
> 基于版本：v2.6.0

---

## 一、现有 RAG 架构

### 1.1 完整流水线

```
Ingestion:
文档 → Loader → Transformer → Milvus(向量) + ES(全文)

Retrieval:
Query → Embed → Milvus ANN × k=100 ─┐
           └→ ES BM25 × k=100 ───→ RRF Fusion (c=60)
                                       ↓
               CustomReranker (BGE-reranker-large, 存在但未全局启用)
                                       ↓
               按 source+chunk_index 排序 → max_content=15000 截断
                                       ↓
               create_stuff_documents_chain(LLM) → 答案
```

### 1.2 核心组件

| 组件 | 实现 | 路径 |
|---|---|---|
| 多格式解析 | PDF/Word/Excel/PPT/HTML/OFD/图片/音视频 | `bisheng/knowledge/rag/pipeline/loader/` |
| 文本分割 | ElemCharacterTextSplitter + 边界框保留 | `bisheng_langchain/text_splitter.py` |
| 向量存储 | Milvus HNSW（稠密）+ ES BM25（稀疏）| `bisheng_langchain/vectorstores/` |
| 双路召回 | RRF 融合，c=60，权重 0.5/0.5 | `bisheng/core/ai/rerank/rrf_rerank.py` |
| Retriever | Baseline / Keyword / Mix / SmallerChunks | `bisheng_langchain/rag/init_retrievers.py` |
| Reranker | BGE-reranker-large，threshold=0 | `bisheng_langchain/rag/rerank/rerank.py` |
| 意图检测 | ❌ 无 | — |

---

## 二、RAG 成熟度评分

| 维度 | 实现情况 | 成熟度 |
|---|---|---|
| **文档解析** | PDF/Word/Excel/PPT/HTML/OFD/图片/音视频 | ✅ 完整 |
| **Chunk 策略** | 递归字符分割 + 层级分块 + overlap | ✅ 完整 |
| **Embedding** | 多模型（OpenAI/Wenxin/HuggingFace/gte） | ✅ 完整 |
| **向量检索** | Milvus ANN HNSW，多 retriever 并行 | ✅ 完整 |
| **关键词检索** | Elasticsearch BM25，match_phrase | ✅ 完整 |
| **双路召回** | ES + Milvus 混合，RRF 3 种合并策略 | ✅ 完整 |
| **重排序（Rerank）** | BGE-reranker-large 已实现，但**未全局启用** | ⚠️ 不一致 |
| **Query 改写/扩展** | ❌ 无（无 HyDE、query decomposition） | ❌ 缺失 |
| **语义分块** | ❌ 仅有递归字符分割 | ❌ 缺失 |
| **多模态检索** | ❌ **完全不存在**（查询仅支持纯文本） | ❌ 缺失 |
| **索引富化** | 仅 title 提取，无摘要/实体/关系 | ⚠️ 薄弱 |
| **Context 长度控制** | max_content=15000（**按字符非 token**） | ⚠️ 有误差 |
| **MMR 多样性召回** | Milvus wrapper 有实现，但默认路径未用 | ⚠️ 未启用 |
| **评估框架** | 仅 answer_correctness，无 recall@K/MRR/NDCG | ⚠️ 缺失 |

---

## 三、多模态混合查询（Mixed Query）需求分析

### 3.1 需求定义

用户查询为"文本 + 图片"混合形式，例如：
- 文字描述"帮我看看这份合同有没有风险" + 附一张合同截图
- 文字描述"这个零件加工工艺有没有问题" + 附一张工程图纸照片
- 文字描述"对比表格数据" + 附一张表格截图

### 3.2 业界实现路径

**核心原理**：图文分别编码到统一向量空间，支持 cross-modal retrieval

| 实现方式 | 说明 |
|---|---|
| **双路编码 + 融合** | 文本走文本编码器，图片走视觉编码器，输出在投影空间对齐 |
| **多模态 embedding** | CLIP / Qwen-VL /InternLM-VL 类模型将图文联合编码 |
| **图像 → 文本 → 检索** | OCR + 视觉模型提取图中实体，转化为文本后走现有 RAG |
| **统一向量空间** | 图片和文本向量存入同一 Collection，支持以图搜文、以文搜图 |

### 3.3 系统要求

```
用户查询（文字 + 图片）
    ↓
┌─────────────────────────────────────────────┐
│  文本部分 → 文本 Embedding（已有）          │
│  图片部分 → 视觉 Encoder → 图片向量         │
│              ↓                               │
│         OCR 提取图中文字 + 视觉 embedding   │
└─────────────────────────────────────────────┘
    ↓
  复合检索请求 → Milvus（图+文同一 Collection）
    ↓
  召回结果排序 → LLM 生成
```

---

## 四、对 BiSheng 的影响评估

### 4.1 当前能力边界

| 场景 | 当前支持 | 说明 |
|---|---|---|
| 纯文本 Query | ✅ 支持 | 现有 Milvus + ES 双路召回 |
| 纯图片 Query（以图搜图） | ❌ 不支持 | 无视觉编码 pipeline |
| 图+文混合 Query | ❌ 不支持 | 需新增多模态 encoder |
| 文档内嵌图片（图片 chunk） | ⚠️ 有限 | `chunk_bboxes` metadata 存在，但图片未做 embedding |

### 4.2 改动范围评估

| 层级 | 改动内容 | 工作量 |
|---|---|---|
| **Embedding 层** | 新增多模态 embedding 模型（CLIP/Qwen-VL） | 中 |
| **向量存储** | Milvus 新增图片向量，与文本向量存同一 Collection 或新建 partition | 中 |
| **检索层** | 修改 `BishengRAGTool` 支持图文混合检索请求 | 中 |
| **文档解析** | Ingestion 时对文档内嵌图片也做 embedding | 大 |
| **OCR** | 新增 NaviDC-OCR 或等价方案，提取图片中的文字信息 | 大 |
| **并发/队列** | 图片 encoding 耗 GPU，需队列限流（T4 可扛，需评估并发） | 中 |

### 4.3 关键风险

1. **GPU 瓶颈**：图片 encoding 是 GPU 密集操作，晚高峰 100 用户并发带图查询，T4 显存在 4G-16G，需评估队列长度
2. **向量空间统一**：图片向量与文本向量必须投影到同一空间，否则无法做跨模态检索
3. **存储膨胀**：图片向量维度（CLIP 768维 / 1024维）比文本 embedding 大，Milvus 存储成本显著上升
4. **延迟增加**：图片处理（OCR + vision encoder）增加 500ms-2s/张，需前端有加载提示

---

## 五、优化路线图建议

### 第一阶段：基础设施补齐（Reranker + token 截断）

| 任务 | 产出 |
|---|---|
| Reranker 在主路径全局启用 | `KnowledgeRetrieverTool` 默认开启 rerank |
| max_content 改为 token 计数 | 引入 tiktoken，按 token 数截断 |

### 第二阶段：召回质量提升

| 任务 | 产出 |
|---|---|
| 添加 HyDE | 用户问题先生成假设答案，再检索 |
| 启用 MMR | 多样性召回，减少结果重复 |
| 混合分数归一化 | RRF 前对 BM25 和向量距离做 min-max 归一化 |
| Query 改写 | 同义词扩展 + 口语化纠错 |

### 第三阶段：多模态能力（需独立需求确认）

| 任务 | 说明 |
|---|---|
| 多模态 embedding 选型 | 推荐 Qwen-VL2 或 CLIP，优先选与现有 LLM 同家族的模型 |
| OCR pipeline | NaviDC-OCR 或 PaddleOCR 提取图片文字 |
| 图文联合检索 | Milvus 新建 `image_embedding` 向量场，与文本向量同 Collection |
| 文档图片预索引 | Ingestion 时对 PDF/Word 内嵌图片做 vision embedding |

---

## 六、关键文件索引

| 组件 | 文件路径 |
|---|---|
| RAG Tool 核心 | `bisheng_langchain/rag/bisheng_rag_tool.py` |
| Knowledge 检索工具 | `bisheng/tool/domain/langchain/knowledge.py` |
| RRF 融合 | `bisheng/core/ai/rerank/rrf_rerank.py` |
| Reranker | `bisheng_langchain/rag/rerank/rerank.py` |
| Milvus 向量存储 | `bisheng_langchain/vectorstores/milvus.py` |
| ES 关键词搜索 | `bisheng_langchain/vectorstores/elastic_keywords_search.py` |
| 文本分割器 | `bisheng_langchain/text_splitter.py` |
| RAG 配置 | `bisheng_langchain/rag/config/baseline_v2.yaml` |
| Ingestion pipeline | `bisheng/knowledge/rag/pipeline/` |
| 文档解析 loader | `bisheng/knowledge/rag/pipeline/loader/` |
| RAG 评估 | `bisheng_langchain/rag/scoring/llama_index_score.py` |

---

## 七、一句话总结

> BiSheng RAG 的**基础设施完整**（多格式解析、双路召回、RRF 融合、多租户），但**检索后处理不彻底**（Reranker 未全局启用、无 Query 侧优化）。**多模态混合查询是完全空白的能力**，如业务确认有"图文混合查询"需求，需在 embedding 层和向量存储层做系统性改造，建议在纯文本 RAG 质量稳定后再推进。
