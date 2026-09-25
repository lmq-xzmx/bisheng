// F050: Knowledge Base Migration Status Panel
// Shows detailed migration progress for a single knowledge base
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "@/components/bs-ui/toast/use-toast"
import { Button } from "@/components/bs-ui/button"
import { captureAndAlertRequestErrorHoc } from "@/controllers/request"
import {
    forceCompleteMigration,
    getMigrationStatus,
    lockKnowledgeBase,
    MigrationStatus,
    pauseMigration,
    unlockKnowledgeBase,
} from "../../../controllers/API/knowledgeMigration"

interface MigrationPanelProps {
    kbId: number
    onStatusChange?: () => void
}

const statusLabels: Record<string, { label: string; color: string }> = {
    idle: { label: "待迁移", color: "bg-gray-400" },
    pending_delayed: { label: "稍后迁移", color: "bg-yellow-400" },
    pending_immediate: { label: "待迁移", color: "bg-blue-400" },
    migrating: { label: "迁移中", color: "bg-blue-500" },
    completed: { label: "已完成", color: "bg-green-400" },
    locked: { label: "已锁定", color: "bg-gray-500" },
    failed: { label: "失败", color: "bg-red-400" },
}

export default function MigrationPanel({ kbId, onStatusChange }: MigrationPanelProps) {
    const [data, setData] = useState<MigrationStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const { t } = useTranslation("model")

    const loadData = () => {
        setLoading(true)
        captureAndAlertRequestErrorHoc(getMigrationStatus(kbId)).then((res) => {
            setData(res)
            setLoading(false)
        })
    }

    useEffect(() => {
        loadData()
        // Poll every 5 seconds during migration
        const interval = setInterval(() => {
            if (data?.migration_status === "migrating") {
                loadData()
            }
        }, 5000)
        return () => clearInterval(interval)
    }, [kbId, data?.migration_status])

    const handlePause = () => {
        captureAndAlertRequestErrorHoc(pauseMigration(kbId)).then(() => {
            toast({ title: "迁移已暂停" })
            loadData()
            onStatusChange?.()
        })
    }

    const handleForceComplete = () => {
        captureAndAlertRequestErrorHoc(forceCompleteMigration(kbId)).then(() => {
            toast({ title: "迁移已强制完成" })
            loadData()
            onStatusChange?.()
        })
    }

    const handleLock = () => {
        captureAndAlertRequestErrorHoc(lockKnowledgeBase(kbId)).then(() => {
            toast({ title: "知识库已锁定" })
            loadData()
            onStatusChange?.()
        })
    }

    const handleUnlock = () => {
        captureAndAlertRequestErrorHoc(unlockKnowledgeBase(kbId)).then(() => {
            toast({ title: "知识库已解锁" })
            loadData()
            onStatusChange?.()
        })
    }

    const formatProgress = (progress: number) => `${(progress * 100).toFixed(1)}%`

    if (loading || !data) {
        return <div className="p-4">加载中...</div>
    }

    const status = statusLabels[data.migration_status] || statusLabels.idle

    return (
        <div className="space-y-4 p-4 border rounded-lg">
            <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium">向量迁移</h3>
                <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs text-white ${status.color}`}
                >
                    {status.label}
                </span>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <span className="text-gray-500">当前模型：</span>
                    <span>{data.current_model || "-"}</span>
                </div>
                <div>
                    <span className="text-gray-500">目标模型：</span>
                    <span>{data.target_model || "-"}</span>
                </div>
                {data.locked_at && (
                    <>
                        <div>
                            <span className="text-gray-500">锁定时间：</span>
                            <span>{new Date(data.locked_at).toLocaleString()}</span>
                        </div>
                        <div>
                            <span className="text-gray-500">锁定人：</span>
                            <span>{data.locked_by || "-"}</span>
                        </div>
                    </>
                )}
            </div>

            {data.migration_status === "migrating" && (
                <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                        <span>迁移进度</span>
                        <span>{formatProgress(data.migration_progress)}</span>
                    </div>
                    <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-blue-500 transition-all duration-500"
                            style={{ width: formatProgress(data.migration_progress) }}
                        />
                    </div>
                </div>
            )}

            <div className="flex gap-2">
                {data.migration_status === "migrating" && (
                    <>
                        <Button size="sm" variant="outline" onClick={handlePause}>
                            暂停迁移
                        </Button>
                        <Button size="sm" variant="outline" onClick={handleForceComplete}>
                            强制完成
                        </Button>
                    </>
                )}
                {data.migration_status === "idle" && (
                    <Button size="sm" variant="outline" onClick={handleLock}>
                        锁定当前模型
                    </Button>
                )}
                {data.migration_status === "locked" && (
                    <Button size="sm" variant="outline" onClick={handleUnlock}>
                        解锁
                    </Button>
                )}
                <Button size="sm" variant="ghost" onClick={loadData}>
                    刷新
                </Button>
            </div>

            {data.migration_status === "locked" && (
                <div className="text-sm text-gray-500 bg-gray-50 p-3 rounded">
                    <p>此知识库已锁定在模型 {data.locked_model}，不受系统默认模型变更影响。</p>
                </div>
            )}
        </div>
    )
}
