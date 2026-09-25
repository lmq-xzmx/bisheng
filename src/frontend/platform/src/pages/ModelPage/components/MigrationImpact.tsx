// F050: Migration Impact Analysis Component
// Displays all knowledge bases and their migration status when embedding model changes
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "@/components/bs-ui/toast/use-toast"
import { Button } from "@/components/bs-ui/button"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/bs-ui/table"
import { captureAndAlertRequestErrorHoc } from "@/controllers/request"
import {
    getMigrationSummary,
    lockKnowledgeBase,
    MigrationStatus,
    startMigration,
    unlockKnowledgeBase,
} from "../../../controllers/API/knowledgeMigration"

interface MigrationImpactProps {
    onStatusChange?: () => void
}

const statusLabels: Record<string, { label: string; color: string }> = {
    idle: { label: "待迁移", color: "bg-gray-400" },
    pending_delayed: { label: "稍后迁移", color: "bg-yellow-400" },
    pending_immediate: { label: "待迁移", color: "bg-blue-400" },
    migrating: { label: "迁移中", color: "bg-blue-500 animate-pulse" },
    completed: { label: "已完成", color: "bg-green-400" },
    locked: { label: "已锁定", color: "bg-gray-500" },
    failed: { label: "失败", color: "bg-red-400" },
}

export default function MigrationImpact({ onStatusChange }: MigrationImpactProps) {
    const [data, setData] = useState<MigrationStatus[]>([])
    const [loading, setLoading] = useState(true)
    const { t } = useTranslation("model")

    const loadData = () => {
        setLoading(true)
        captureAndAlertRequestErrorHoc(getMigrationSummary()).then((res) => {
            setData(res)
            setLoading(false)
        })
    }

    useEffect(() => {
        loadData()
    }, [])

    const handleStartMigration = (kbId: number, targetModel: string) => {
        captureAndAlertRequestErrorHoc(
            startMigration(kbId, { target_model: targetModel, strategy: "immediate" })
        ).then(() => {
            toast({ title: "迁移已开始" })
            loadData()
            onStatusChange?.()
        })
    }

    const handleLock = (kbId: number) => {
        captureAndAlertRequestErrorHoc(lockKnowledgeBase(kbId)).then(() => {
            toast({ title: "知识库已锁定" })
            loadData()
            onStatusChange?.()
        })
    }

    const handleUnlock = (kbId: number) => {
        captureAndAlertRequestErrorHoc(unlockKnowledgeBase(kbId)).then(() => {
            toast({ title: "知识库已解锁" })
            loadData()
            onStatusChange?.()
        })
    }

    const formatProgress = (progress: number) => {
        return `${(progress * 100).toFixed(1)}%`
    }

    if (loading) {
        return <div className="p-4">加载中...</div>
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium">知识库迁移状态</h3>
                <Button variant="outline" size="sm" onClick={loadData}>
                    刷新
                </Button>
            </div>

            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>知识库名称</TableHead>
                        <TableHead>当前模型</TableHead>
                        <TableHead>目标模型</TableHead>
                        <TableHead>状态</TableHead>
                        <TableHead>进度</TableHead>
                        <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {data.map((item) => {
                        const status = statusLabels[item.migration_status] || statusLabels.idle
                        return (
                            <TableRow key={item.kb_id}>
                                <TableCell className="font-medium">{item.kb_name}</TableCell>
                                <TableCell>{item.current_model || "-"}</TableCell>
                                <TableCell>{item.target_model || "-"}</TableCell>
                                <TableCell>
                                    <span
                                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs text-white ${status.color}`}
                                    >
                                        {status.label}
                                    </span>
                                </TableCell>
                                <TableCell>
                                    {item.migration_status === "migrating" && (
                                        <div className="flex items-center gap-2">
                                            <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-blue-500 transition-all"
                                                    style={{ width: formatProgress(item.migration_progress) }}
                                                />
                                            </div>
                                            <span className="text-xs">
                                                {formatProgress(item.migration_progress)}
                                            </span>
                                        </div>
                                    )}
                                    {item.migration_status !== "migrating" && (
                                        <span className="text-gray-400">-</span>
                                    )}
                                </TableCell>
                                <TableCell className="text-right">
                                    {item.migration_status === "idle" && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() =>
                                                handleStartMigration(item.kb_id, item.target_model || "")
                                            }
                                        >
                                            立即迁移
                                        </Button>
                                    )}
                                    {item.migration_status === "idle" && (
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            className="ml-2"
                                            onClick={() => handleLock(item.kb_id)}
                                        >
                                            稍后迁移
                                        </Button>
                                    )}
                                    {item.migration_status === "locked" && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => handleUnlock(item.kb_id)}
                                        >
                                            解锁
                                        </Button>
                                    )}
                                </TableCell>
                            </TableRow>
                        )
                    })}
                </TableBody>
            </Table>

            {data.length === 0 && (
                <div className="text-center py-8 text-gray-400">
                    暂无可迁移的知识库
                </div>
            )}
        </div>
    )
}
