// DialogueWork.tsx
import { userContext } from "@/contexts/userContext";
import { ScopeBar } from "@/pages/ModelPage/manage/ScopeBar";
import { useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AppCenter } from "./AppCenter";
import Index from "./index";
import Subscribe from "./Subscribe";
import KnowledgeSpace from "./KnowledgeSpace";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/bs-ui/tabs";
import { Button } from "@/components/bs-ui/button";

export default function DialogueWork() {
  const [defaultValue] = useState("client");
  const [scopeVersion, setScopeVersion] = useState(0);
  const { t, i18n } = useTranslation();
  const { user } = useContext(userContext) as any;
  const navigate = useNavigate();
  useEffect(() => {
    i18n.loadNamespaces('tool');
  }, [i18n]);

  const handleOpenCollaborativeChat = () => {
    window.open('/workspace/collab/sessions', '_blank');
  };

  return (
    <div className="w-full h-full px-2 pt-4 relative">
      <Tabs defaultValue={defaultValue} className="w-full mb-[40px]">
        <div className="mb-4 flex items-center gap-3">
          <ScopeBar
            user={user}
            onScopeChange={() => {
              setScopeVersion((value) => value + 1);
            }}
          />
          {/* F035 (PRD §4.8): the 灵思 tab is merged into 首页 (home) — task-mode
              display name / input placeholder live there now, the entry toggle
              moved to role menus, tools share the home pool, and the SOP
              manual library is replaced by skill management. The app-center
              copy moved out into its own 应用 tab. */}
          <TabsList className="">
            <TabsTrigger value="client">{t('bench.home')}</TabsTrigger>
            <TabsTrigger value="knowledgeSpace">{t('bench.knowledgeSpace')}</TabsTrigger>
            <TabsTrigger value="subscribe">{t('bench.subscribe')}</TabsTrigger>
            <TabsTrigger value="appCenter">{t('bench.appCenter')}</TabsTrigger>
          </TabsList>
          <Button
            variant="outline"
            size="sm"
            onClick={handleOpenCollaborativeChat}
            className="ml-auto flex items-center gap-1.5"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            {t('bench.collaborativeChat') || '协同聊天'}
          </Button>
        </div>
        <TabsContent value="client" key="client-tab">
          <Index scopeVersion={scopeVersion} />
        </TabsContent>
        <TabsContent value="knowledgeSpace">
          <KnowledgeSpace scopeVersion={scopeVersion} />
        </TabsContent>
        <TabsContent value="subscribe">
          <Subscribe scopeVersion={scopeVersion} />
        </TabsContent>
        <TabsContent value="appCenter">
          <AppCenter scopeVersion={scopeVersion} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
