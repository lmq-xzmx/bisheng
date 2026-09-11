import { LoadingIcon } from '@/components/bs-icons/loading';
import { Button } from '@/components/bs-ui/button';
import { DialogClose, DialogFooter } from "@/components/bs-ui/dialog";
import { Label } from '@/components/bs-ui/label';
import { toast } from '@/components/bs-ui/toast/use-toast';
import { getToolsApi, updateToolApi } from '@/controllers/API/tools';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from "react-i18next";
import { InputField, SelectField } from "./InputField";

const defaultToolParams = {
    bing: {
        api_key: '',
        base_url: 'https://api.bing.microsoft.com/v7.0/search'
    },
    bocha: {
        api_key: '',
        base_url: ''
    },
    jina: {
        api_key: '',
        base_url: ''
    },
    serp: {
        api_key: '',
        engine: 'baidu',
        base_url: ''
    },
    tavily: {
        api_key: '',
        base_url: ''
    },
    cloudsway: {
        api_key: '',
        endpoint: '',
        base_url: ''
    },
    searXNG: {
        server_url: ''
    },
};

interface WebSearchFormProps {
    formData?: any;
    onSubmit?: (config: any) => void;
    isApi?: boolean;
}

const WebSearchForm = ({ formData, onSubmit, isApi = false }: WebSearchFormProps) => {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(true);
    const toolIdRef = useRef('');
    const [enabled, setEnabled] = useState(true);
    const [prompt, setPrompt] = useState('');
    const closeRef = useRef<HTMLButtonElement | null>(null);

    const [allToolsConfig, setAllToolsConfig] = useState<Record<string, any>>({
        ...defaultToolParams,
    });

    const [selectedTool, setSelectedTool] = useState<string>('bing');
    const [formErrors, setFormErrors] = useState({});

    // Initialization: If isApi is true, fetch data via the interface; otherwise, use the parent-level formData.
    useEffect(() => {
        const initFromApi = async () => {
            try {
                const res = await getToolsApi('default');
                const webSearchTool = res.find((item: any) => item.name === '联网搜索');
                if (webSearchTool) {
                    toolIdRef.current = webSearchTool.id;
                    if (webSearchTool.extra) {
                        try {
                            const extraData = JSON.parse(webSearchTool.extra);
                            setSelectedTool(extraData.type || 'bing');
                            setEnabled(extraData.enabled ?? true);
                            setPrompt(extraData.prompt ?? '');
                            setAllToolsConfig({
                                ...defaultToolParams,
                                ...(extraData.config || {}),
                            });
                        } catch (e) { }
                    }
                }
            } catch (error: any) {
                toast({
                    title: t('failed'),
                    description: error?.message || '',
                    variant: 'error',
                });
            } finally {
                setLoading(false);
            }
        };

        const initFromProps = () => {
            const mergedConfig = {
                ...defaultToolParams,
                ...(formData?.config || {}),
            } as Record<string, any>;
            setAllToolsConfig(mergedConfig);
            setSelectedTool(formData?.type || 'bing');
            setEnabled(formData?.enabled ?? true);
            setPrompt(formData?.prompt ?? '');
            setLoading(false);
        };

        if (isApi) {
            initFromApi();
        } else {
            initFromProps();
        }
    }, [isApi, formData]);

    const validationRules = {
        bing: {
            base_url: (value) => !value && 'Bing Search URL ' + t('chatConfig.errors.required')
        },
        bocha: {
            api_key: (value) => !value && 'API Key ' + t('chatConfig.errors.required')
        },
        jina: {
            api_key: (value) => !value && 'API Key ' + t('chatConfig.errors.required')
        },
        serp: {
            api_key: (value) => !value && 'API Key ' + t('chatConfig.errors.required'),
            engine: (value) => !value && 'engine ' + t('chatConfig.errors.required')
        },
        tavily: {
            api_key: (value) => !value && 'API Key ' + t('chatConfig.errors.required')
        },
        cloudsway: {
            api_key: (value) => !value && 'API Key ' + t('chatConfig.errors.required'),
            endpoint: (value) => !value && 'endpoint ' + t('chatConfig.errors.required')
        },
        searXNG: {
            server_url: (value) => !value && 'The server address cannot be empty'
        }
    };

    const handleToolChange = (tool) => {
        setSelectedTool(tool);
        setFormErrors({});
    };

    const handleParamChange = (e) => {
        const { name, value } = e.target;
        setAllToolsConfig(prev => ({
            ...prev,
            [selectedTool]: {
                ...prev[selectedTool],
                [name]: value
            }
        }));

        setFormErrors(prev => ({
            ...prev,
            [name]: undefined
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        const errors = {} as Record<string, string>;
        const currentToolRules = (validationRules as any)[selectedTool] || {};

        Object.keys(currentToolRules).forEach(key => {
            const error = currentToolRules[key]((allToolsConfig as any)[selectedTool]?.[key]);
            if (error) {
                errors[key] = error;
            }
        });

        if (Object.keys(errors).length > 0) {
            setFormErrors(errors);
            return;
        }

        const typedConfig = {
            bing: (allToolsConfig as any).bing || defaultToolParams.bing,
            bocha: (allToolsConfig as any).bocha || defaultToolParams.bocha,
            jina: (allToolsConfig as any).jina || defaultToolParams.jina,
            serp: (allToolsConfig as any).serp || defaultToolParams.serp,
            tavily: (allToolsConfig as any).tavily || defaultToolParams.tavily,
            cloudsway: (allToolsConfig as any).cloudsway || defaultToolParams.cloudsway,
            searXNG: (allToolsConfig as any).searXNG || defaultToolParams.searXNG,
        };

        const newConfig = {
            enabled,
            type: selectedTool,
            config: typedConfig,
            prompt,
        };
        try {
            if (isApi) {
                if (toolIdRef.current) {
                    await updateToolApi(toolIdRef.current, newConfig);
                }
                toast({
                    title: t('skills.saveSuccessful'),
                    description: '',
                    variant: 'success',
                });
                // Close the pop-up window after successful submission.
                closeRef.current?.click();
            } else {
                onSubmit?.(newConfig);
            }
        } catch (error: any) {
            toast({
                title: t('failed'),
                description: error?.message || '',
                variant: 'error',
            });
        }
    };

    const renderParams = () => {

        const currentTool: any = ((allToolsConfig as any)[selectedTool] as any) || ({} as any);
        const currentToolMap: Record<string, any> = currentTool as Record<string, any>;

        if (!currentTool) return null;

        const baseUrlField = (
            <InputField
                label="Base URL"
                name="base_url"
                value={currentToolMap['base_url'] || ''}
                onChange={handleParamChange}
                error={(formErrors as any).base_url}
                id={`${selectedTool}-base-url`}
            />
        );

        switch (selectedTool) {
            case 'bing':
                return (
                    <>
                        <InputField
                            required
                            label="Bing Subscription Key"
                            type="password"
                            name="api_key"
                            value={currentToolMap['api_key'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).api_key}
                            id="bing-api-key"
                        />
                        <InputField
                            required
                            label="Bing Search URL"
                            name="base_url"
                            value={currentToolMap['base_url'] || defaultToolParams.bing.base_url}
                            onChange={handleParamChange}
                            error={(formErrors as any).base_url}
                            id="bing-base-url"
                        />
                    </>
                );
            case 'bocha':
                return (
                    <>
                        <InputField
                            required
                            label="API Key"
                            type="password"
                            name="api_key"
                            value={currentToolMap['api_key'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).api_key}
                            id="bocha-api-key"
                        />
                        {baseUrlField}
                    </>
                );
            case 'jina':
                return (
                    <>
                        <InputField
                            required
                            label="API Key"
                            type="password"
                            name="api_key"
                            value={currentToolMap['api_key'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).api_key}
                            id="jina-api-key"
                        />
                        {baseUrlField}
                    </>
                );
            case 'serp':
                return (
                    <>
                        <InputField
                            required
                            label="API Key"
                            type="password"
                            name="api_key"
                            value={currentToolMap['api_key'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).api_key}
                            id="serp-api-key"
                        />
                        <InputField
                            required
                            label="engine"
                            name="engine"
                            value={currentToolMap['engine'] || 'baidu'}
                            onChange={handleParamChange}
                            error={(formErrors as any).engine}
                            id="serp-engine"
                        />
                        {baseUrlField}
                    </>
                );
            case 'tavily':
                return (
                    <>
                        <InputField
                            required
                            label="API Key"
                            type="password"
                            name="api_key"
                            value={currentToolMap['api_key'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).api_key}
                            id="tavily-api-key"
                        />
                        {baseUrlField}
                    </>
                );
            case 'cloudsway':
                return (
                    <>
                        <InputField
                            required
                            label="API Key"
                            type="password"
                            name="api_key"
                            value={currentToolMap['api_key'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).api_key}
                            id="cloudsway-api-key"
                        />
                        <InputField
                            required
                            label="endpoint"
                            name="endpoint"
                            value={currentToolMap['endpoint'] || ''}
                            onChange={handleParamChange}
                            error={(formErrors as any).endpoint}
                            id="cloudsway-endpoint"
                        />
                        {baseUrlField}
                    </>
                );
            case 'searXNG':
                return (
                    <InputField
                        required
                        label={t('chatConfig.webSearch.serverUrl')}
                        name="server_url"
                        value={currentToolMap['server_url'] || ''}
                        onChange={handleParamChange}
                        error={(formErrors as any).server_url}
                        id="searxng-server-url"
                        placeholder={t('chatConfig.webSearch.serverUrlPlaceholder')}
                    />
                );
            default:
                return null;
        }
    };

    if (isApi && loading) {
        return (
            <div className="flex h-40 items-center justify-center">
                <LoadingIcon />
            </div>
        );
    }

    return (
        <>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                {/* Hide the close button for programmatic closing of the pop-up window after successful submission. */}
                <DialogClose asChild>
                    <button ref={closeRef} className="hidden" />
                </DialogClose>
                <SelectField
                    label={t('chatConfig.webSearch.engine')}
                    value={selectedTool}
                    onChange={handleToolChange}
                    options={[
                        { value: 'bing', label: t('chatConfig.webSearch.bing') },
                        { value: 'bocha', label: t('chatConfig.webSearch.bocha') },
                        { value: 'jina', label: t('chatConfig.webSearch.jina') },
                        { value: 'serp', label: t('chatConfig.webSearch.serp') },
                        { value: 'tavily', label: t('chatConfig.webSearch.tavily') },
                        { value: 'searXNG', label: t('chatConfig.webSearch.searXNG') },
                        { value: 'cloudsway', label: t('chatConfig.webSearch.cloudsway') },
                    ]}
                    id="search-tool-selector"
                    name="search_tool"
                />

                <div className="space-y-4">
                    <Label className="bisheng-label">{t('chatConfig.webSearch.config')}</Label>
                    {renderParams()}
                </div>

                {/* 诊断与缓存面板 */}
                <SearchDiagnosticsPanel
                    searchApiBase={currentToolMap['server_url'] || ''}
                />

                <DialogFooter>
                    <DialogClose>
                        <Button variant="outline" className="px-11" type="button">
                            {t('build.cancel')}
                        </Button>
                    </DialogClose>
                    <Button className="px-11" type="submit" disabled={isApi && loading}>
                        {t('build.confirm')}
                    </Button>
                </DialogFooter>
            </form>
        </>

    );
};

export default WebSearchForm;

// ============================================================================
// 搜索诊断面板：显示各源状态、清缓存、抓 RSS
// ============================================================================

import { useCallback, useState } from 'react';
import { toast } from '@/components/bs-ui/toast/use-toast';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/bs-ui/card';
import { Button } from '@/components/bs-ui/button';
import { Badge } from '@/components/bs-ui/badge';
import { Progress } from '@/components/bs-ui/progress';

interface SourceStatus {
    status: 'OK' | 'ERROR' | 'checking' | 'idle';
    count?: number;
    size_bytes?: number;
    error?: string;
    response?: Record<string, any>;
}

interface DiagnosticsData {
    timestamp: string;
    sources: Record<string, SourceStatus>;
}

const StatusBadge = ({ s }: { s: SourceStatus }) => {
    if (s.status === 'checking') return <Badge variant="outline">检查中…</Badge>;
    if (s.status === 'idle') return <Badge variant="outline">未检测</Badge>;
    if (s.status === 'ERROR') return <Badge variant="destructive">异常</Badge>;
    return <Badge variant="secondary">正常</Badge>;
};

const SourceItem = ({
    label,
    source,
    s,
    detail,
}: {
    label: string;
    source: string;
    s: SourceStatus;
    detail?: string;
}) => (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
        <div className="flex flex-col gap-1 min-w-0">
            <span className="font-medium text-sm truncate">{label}</span>
            {s.error && (
                <span className="text-xs text-destructive truncate">{s.error}</span>
            )}
            {s.count !== undefined && (
                <span className="text-xs text-muted-foreground">
                    返回 {s.count} 条结果
                </span>
            )}
            {s.size_bytes !== undefined && (
                <span className="text-xs text-muted-foreground">
                    {s.size_bytes} bytes
                </span>
            )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-4">
            <StatusBadge s={s} />
            {detail && <span className="text-xs text-muted-foreground">{detail}</span>}
        </div>
    </div>
);

const SearchDiagnosticsPanel = ({ searchApiBase }: { searchApiBase: string }) => {
    const [data, setData] = useState<DiagnosticsData | null>(null);
    const [loading, setLoading] = useState(false);
    const [meiliStats, setMeiliStats] = useState<Record<string, any> | null>(null);
    const [rssLoading, setRssLoading] = useState(false);

    const base = searchApiBase?.replace(/\/$/, '');

    const doCheck = useCallback(async () => {
        if (!base) {
            toast({ title: '请先保存 SearXNG 服务器地址', variant: 'destructive' });
            return;
        }
        setLoading(true);
        try {
            const res = await fetch(`${base}/debug/sources`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            setData(json);
            toast({ title: '检测完成', variant: 'success' });
        } catch (err: any) {
            toast({ title: '检测失败', description: err.message, variant: 'destructive' });
        } finally {
            setLoading(false);
        }
    }, [base]);

    const doMeiliStats = useCallback(async () => {
        if (!base) return;
        try {
            const res = await fetch(`${base}/debug/meilisearch/stats`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            setMeiliStats(json.data || json);
        } catch {}
    }, [base]);

    const doClear = useCallback(async () => {
        if (!base) return;
        try {
            const res = await fetch(`${base}/debug/meilisearch/clear`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            toast({ title: '缓存已清空', variant: 'success' });
            doMeiliStats();
        } catch (err: any) {
            toast({ title: '清空失败', description: err.message, variant: 'destructive' });
        }
    }, [base, doMeiliStats]);

    const doFinanceRss = useCallback(async () => {
        if (!base) return;
        setRssLoading(true);
        try {
            const res = await fetch(`${base}/debug/finance/rss`, { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            toast({
                title: '财经 RSS 抓取完成',
                description: `导入了 ${json.imported || 0} 条`,
                variant: 'success',
            });
        } catch (err: any) {
            toast({ title: '抓取失败', description: err.message, variant: 'destructive' });
        } finally {
            setRssLoading(false);
        }
    }, [base]);

    const meiliDocCount = meiliStats?.data?.numberOfDocuments || 0;

    return (
        <div className="rounded-md border p-4 space-y-4">
            <div className="flex items-center justify-between">
                <span className="text-sm font-medium">诊断与缓存</span>
                <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={doCheck} disabled={loading || !base}>
                        {loading ? '检测中…' : '检测连接'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={doMeiliStats} disabled={!base}>
                        缓存状态
                    </Button>
                    <Button size="sm" variant="outline" onClick={doClear} disabled={!base}>
                        清空缓存
                    </Button>
                    <Button size="sm" variant="outline" onClick={doFinanceRss} disabled={rssLoading || !base}>
                        {rssLoading ? '抓取中…' : '抓取财经 RSS'}
                    </Button>
                </div>
            </div>

            {data && (
                <div className="space-y-1">
                    <div className="text-xs text-muted-foreground mb-2">
                        检测时间：{new Date(data.timestamp).toLocaleString()}
                    </div>
                    {Object.entries(data.sources).map(([key, s]) => {
                        const labelMap: Record<string, string> = {
                            searxng: '网络搜索（SearXNG）',
                            weibo_hot: '微博热搜',
                            meilisearch: 'Meilisearch 健康',
                            finance_rss: '财经 RSS（东方财富）',
                        };
                        return (
                            <SourceItem
                                key={key}
                                label={labelMap[key] || key}
                                source={key}
                                s={s as SourceStatus}
                            />
                        );
                    })}
                </div>
            )}

            {meiliStats && (
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>Meilisearch 文档数：{meiliDocCount}</span>
                    {meiliStats.status === 'ok' && (
                        <span>响应：{JSON.stringify(meiliStats.data || meiliStats).slice(0, 60)}</span>
                    )}
                </div>
            )}
        </div>
    );
};
