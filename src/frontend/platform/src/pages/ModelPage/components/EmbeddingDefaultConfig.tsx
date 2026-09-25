// F050: Embedding Query Configuration Component
// Settings for query routing strategy and detail display
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "@/components/bs-ui/toast/use-toast"
import { Button } from "@/components/bs-ui/button"
import { captureAndAlertRequestErrorHoc } from "@/controllers/request"
import {
    EmbeddingConfig,
    getEmbeddingConfig,
    updateEmbeddingConfig,
} from "../../../controllers/API/embeddingConfig"

interface EmbeddingDefaultConfigProps {
    onChange?: () => void
}

export default function EmbeddingDefaultConfig({ onChange }: EmbeddingDefaultConfigProps) {
    const [config, setConfig] = useState<EmbeddingConfig>({
        strategy: "dual_rrf",
        show_details: false,
    })
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const { t } = useTranslation("model")

    useEffect(() => {
        captureAndAlertRequestErrorHoc(getEmbeddingConfig()).then((res) => {
            setConfig(res)
            setLoading(false)
        })
    }, [])

    const handleStrategyChange = (strategy: "new_only" | "old_only" | "dual_rrf") => {
        setConfig((prev) => ({ ...prev, strategy }))
    }

    const handleShowDetailsChange = (showDetails: boolean) => {
        setConfig((prev) => ({ ...prev, show_details: showDetails }))
    }

    const handleSave = () => {
        setSaving(true)
        captureAndAlertRequestErrorHoc(updateEmbeddingConfig(config))
            .then(() => {
                toast({ title: "配置已保存" })
                onChange?.()
            })
            .finally(() => setSaving(false))
    }

    if (loading) {
        return <div className="p-4">加载中...</div>
    }

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium mb-4">查询路由策略</h3>
                <div className="space-y-3">
                    <label className="flex items-center gap-3 cursor-pointer">
                        <input
                            type="radio"
                            name="strategy"
                            value="dual_rrf"
                            checked={config.strategy === "dual_rrf"}
                            onChange={() => handleStrategyChange("dual_rrf")}
                            className="w-4 h-4"
                        />
                        <div>
                            <p className="font-medium">双模型 RRF 融合（推荐）</p>
                            <p className="text-sm text-gray-500">
                                迁移期间同时查询新旧模型，结果通过排名融合返回
                            </p>
                        </div>
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer">
                        <input
                            type="radio"
                            name="strategy"
                            value="new_only"
                            checked={config.strategy === "new_only"}
                            onChange={() => handleStrategyChange("new_only")}
                            className="w-4 h-4"
                        />
                        <div>
                            <p className="font-medium">仅使用新模型</p>
                            <p className="text-sm text-gray-500">
                                查询速度更快，但迁移期间未完成部分数据不可见
                            </p>
                        </div>
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer">
                        <input
                            type="radio"
                            name="strategy"
                            value="old_only"
                            checked={config.strategy === "old_only"}
                            onChange={() => handleStrategyChange("old_only")}
                            className="w-4 h-4"
                        />
                        <div>
                            <p className="font-medium">仅使用旧模型</p>
                            <p className="text-sm text-gray-500">
                                保持原有查询行为，不使用新模型
                            </p>
                        </div>
                    </label>
                </div>
            </div>

            <div>
                <h3 className="text-lg font-medium mb-4">技术详情显示</h3>
                <label className="flex items-center gap-3 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={config.show_details}
                        onChange={(e) => handleShowDetailsChange(e.target.checked)}
                        className="w-4 h-4"
                    />
                    <div>
                        <p className="font-medium">在 Chat 界面显示技术详情</p>
                        <p className="text-sm text-gray-500">
                            开启后，终端用户可展开查看来源模型、匹配度等信息
                        </p>
                    </div>
                </label>
            </div>

            <div className="flex justify-end">
                <Button onClick={handleSave} disabled={saving}>
                    {saving ? "保存中..." : "保存配置"}
                </Button>
            </div>
        </div>
    )
}
