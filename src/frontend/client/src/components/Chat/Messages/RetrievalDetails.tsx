// F050: Retrieval Details Collapse Panel
// Shows embedding model info, match score, etc. for RAG results
import { memo, useState } from "react"
import { ChevronDownIcon, ChevronUpIcon } from "lucide-react"
import { useLocalize } from "~/hooks"
import { cn } from "~/utils"

export interface RetrievalDetailsData {
    /** Source knowledge base name */
    knowledge_base?: string
    /** Number of retrieved documents */
    doc_count?: number
    /** Embedding model used */
    embedding_model?: string
    /** Match score (0-1) */
    match_score?: number
    /** Query routing strategy used */
    routing_strategy?: "new_only" | "old_only" | "dual_rrf"
}

interface RetrievalDetailsProps {
    details: RetrievalDetailsData
    className?: string
}

const strategyLabels: Record<string, string> = {
    new_only: "新模型",
    old_only: "旧模型",
    dual_rrf: "双模型 RRF 融合",
}

export const RetrievalDetails = memo(function RetrievalDetails({
    details,
    className,
}: RetrievalDetailsProps) {
    const [expanded, setExpanded] = useState(false)
    const localize = useLocalize()

    if (!details || Object.keys(details).length === 0) {
        return null
    }

    return (
        <div className={cn("text-xs text-gray-500", className)}>
            <button
                type="button"
                onClick={() => setExpanded((e) => !e)}
                className="flex items-center gap-1 hover:text-gray-700 transition-colors"
            >
                {expanded ? (
                    <ChevronUpIcon className="w-3 h-3" />
                ) : (
                    <ChevronDownIcon className="w-3 h-3" />
                )}
                {localize("retrieval_details") || "技术详情"}
            </button>

            {expanded && (
                <div className="mt-2 p-2 bg-gray-50 rounded border space-y-1">
                    {details.knowledge_base && (
                        <div className="flex justify-between">
                            <span className="text-gray-400">
                                {localize("source_kb") || "来源知识库"}：
                            </span>
                            <span>{details.knowledge_base}</span>
                        </div>
                    )}
                    {details.doc_count !== undefined && (
                        <div className="flex justify-between">
                            <span className="text-gray-400">
                                {localize("retrieved_docs") || "检索文档数"}：
                            </span>
                            <span>{details.doc_count}</span>
                        </div>
                    )}
                    {details.embedding_model && (
                        <div className="flex justify-between">
                            <span className="text-gray-400">
                                {localize("embedding_model") || "向量模型"}：
                            </span>
                            <span>{details.embedding_model}</span>
                        </div>
                    )}
                    {details.match_score !== undefined && (
                        <div className="flex justify-between">
                            <span className="text-gray-400">
                                {localize("match_score") || "匹配度"}：
                            </span>
                            <span>{(details.match_score * 100).toFixed(0)}%</span>
                        </div>
                    )}
                    {details.routing_strategy && (
                        <div className="flex justify-between">
                            <span className="text-gray-400">
                                {localize("routing_strategy") || "查询策略"}：
                            </span>
                            <span>{strategyLabels[details.routing_strategy] || details.routing_strategy}</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
})
