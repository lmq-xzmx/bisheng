# Obsidian + BiSheng 知识库整合方案

本文档描述如何将 Obsidian 作为个人/团队知识编辑工具，与 BiSheng 企业知识库系统整合，实现大规模知识管理。

---

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           大规模知识管理架构                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Git 知识仓库 (Monorepo)                              │   │
│  │                                                                              │   │
│  │   knowledge-base/                                                              │   │
│  │   ├── _templates/          ← 知识模板库                                        │   │
│  │   ├── _shared/              ← 团队共享知识                                       │   │
│  │   ├── projects/             ← 项目知识 (按项目隔离)                              │   │
│  │   └── personal/             ← 个人笔记 (不同步)                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                          │
│                               Git Post-Receive Hook                               │
│                                         │                                          │
│                                         ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         BiSheng 知识同步服务                                  │   │
│  │                                                                              │   │
│  │   Git Path              →  BiSheng Knowledge Base                              │   │
│  │   ─────────────────────────────────────────────────────                     │   │
│  │   _shared/规范流程/     →  team:standards                                  │   │
│  │   _shared/技术文档/     →  team:technical                                  │   │
│  │   projects/alpha/       →  project:alpha                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Git 仓库结构设计

### 目录规范

```
knowledge-base/
├── README.md                    # 仓库说明
├── SYNC_CONFIG.yaml            # 同步配置 (关键!)
├── _templates/                 # 知识模板
│   ├── meeting-template.md
│   ├── project-template.md
│   └── spec-template.md
├── _shared/                   # 团队共享知识 (自动同步)
│   ├── _index.yaml           # 定义知识库映射
│   ├── 规范流程/
│   ├── 技术文档/
│   └── 培训资料/
└── projects/                   # 项目知识 (按项目同步)
    ├── alpha/
    ├── beta/
    └── gamma/
```

### SYNC_CONFIG.yaml 同步配置

```yaml
# 同步配置 - BiSheng 使用此配置决定如何处理每个文件
version: "1.0"

# 全局同步规则
sync:
  # 包含路径 (只同步这些路径下的文件)
  include_paths:
    - "_shared/**"
    - "projects/**"
  
  # 排除路径 (不同步)
  exclude_paths:
    - "_templates/**"
    - "personal/**"
    - "**/.obsidian/**"
    - "**/*.draft.md"
  
  # 文件类型
  file_types:
    - "*.md"
    - "*.markdown"
  
  # 附件处理
  attachments:
    enabled: true
    max_size: "50MB"
    types:
      - "*.pdf"
      - "*.png"
      - "*.jpg"
      - "*.gif"
      - "*.drawio"

# 知识库映射
knowledge_mappings:
  mappings:
    "_shared/规范流程":
      knowledge_base: "team:standards"
      collection: "shared_standards"
      tags: ["规范", "流程", "team"]
    
    "_shared/技术文档":
      knowledge_base: "team:technical"
      collection: "shared_technical"
      tags: ["技术", "文档", "team"]
    
    "_shared/培训资料":
      knowledge_base: "team:training"
      collection: "shared_training"
      tags: ["培训", "新人", "team"]
    
    "projects/alpha":
      knowledge_base: "project:alpha"
      collection: "project_alpha"
      tags: ["project", "alpha"]
    
    "projects/beta":
      knowledge_base: "project:beta"
      collection: "project_beta"
      tags: ["project", "beta"]

# 处理规则
processing:
  frontmatter:
    required_fields:
      - "title"
    optional_fields:
      - "tags"
      - "authors"
      - "date"
      - "status"
  
  auto_tags:
    from_path: true
    from_filename: true
  
  summary:
    enabled: true
    method: "first_paragraph"
```

### Frontmatter 规范

```markdown
---
title: Code Review 规范
authors:
  - zhangsan
  - lisi
date: 2024-01-15
status: active
tags: [规范, CodeReview, 工程实践]
sync:
  enabled: true
  knowledge_base: team:standards
  visibility: team
related_projects:
  - alpha
---

# Code Review 规范

本文档定义了团队代码审查的标准流程...
```

---

## 3. Git post-receive Hook 脚本

### 服务器端 Hook

**路径**: `/var/www/knowledge-base.git/hooks/post-receive`

```bash
#!/bin/bash
#====================================================
# BiSheng Knowledge Sync - Git Post-Receive Hook
#====================================================

GIT_DIR="/var/www/knowledge-base.git"
WORK_TREE="/var/www/knowledge-base-checkout"
SYNC_SCRIPT="/opt/bisheng-sync/sync.py"
LOCK_FILE="/var/run/bisheng-sync.lock"
LOG_FILE="/var/log/bisheng-sync.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        log "${YELLOW}Sync already running, skipping...${NC}"
        exit 0
    fi
    echo $$ > "$LOCK_FILE"
}

cleanup() {
    release_lock
    cd "$GIT_DIR" && rm -rf "$WORK_TREE"
}

release_lock() { rm -f "$LOCK_FILE"; }
trap cleanup EXIT
acquire_lock

log "${GREEN}=== Starting BiSheng Knowledge Sync ===${NC}"

while read oldrev newrev refname; do
    branch=$(echo $refname | sed 's/refs\/heads\///')
    
    if [ "$branch" != "main" ] && [ "$branch" != "master" ]; then
        log "Skipping branch: $branch"
        continue
    fi
    
    log "Processing $branch: $oldrev -> $newrev"
    
    cd "$GIT_DIR"
    rm -rf "$WORK_TREE"
    GIT_WORK_TREE="$WORK_TREE" git checkout -f main
    
    CHANGED_FILES=$(git diff --name-only $oldrev $newrev -- "*.md" "*.markdown" | grep -v "^_templates/" | grep -v "^personal/")
    DELETED_FILES=$(git diff --name-only --diff-filter=D $oldrev $newrev -- "*.md" "*.markdown" | grep -v "^_templates/" | grep -v "^personal/")
    NEW_FILES=$(git diff --name-only --diff-filter=A $oldrev $newrev -- "*.md" "*.markdown" | grep -v "^_templates/" | grep -v "^personal/")
    
    if [ -z "$CHANGED_FILES" ] && [ -z "$DELETED_FILES" ] && [ -z "$NEW_FILES" ]; then
        log "No knowledge files to sync"
        continue
    fi
    
    python3 "$SYNC_SCRIPT" \
        --work-tree "$WORK_TREE" \
        --changed "$CHANGED_FILES" \
        --deleted "$DELETED_FILES" \
        --new "$NEW_FILES" \
        --commit-range "$oldrev..$newrev" \
        2>&1 | tee -a "$LOG_FILE"
    
done

log "${GREEN}=== Sync Finished ===${NC}"
```

---

## 4. BiSheng 同步服务

### 同步处理器

**路径**: `/opt/bisheng-sync/sync.py`

```python
#!/usr/bin/env python3
"""
BiSheng Knowledge Sync Service
从 Git 仓库同步知识到 BiSheng
"""

import os
import sys
import json
import yaml
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set

import requests
from pydantic import BaseModel

BISHENG_API = os.getenv("BISHENG_API", "http://localhost:7861")
API_KEY = os.getenv("BISHENG_API_KEY", "")


class SyncConfig(BaseModel):
    version: str
    sync: Dict
    knowledge_mappings: Dict
    processing: Dict


class KnowledgeFile(BaseModel):
    path: str
    relative_path: str
    content: str
    frontmatter: Dict
    tags: List[str]
    knowledge_base: str
    collection: str
    action: str


class BiShengSyncService:
    def __init__(self, work_tree: str, config_path: str = "SYNC_CONFIG.yaml"):
        self.work_tree = Path(work_tree)
        self.config = self._load_config(config_path)
        self.session = requests.Session()
        if API_KEY:
            self.session.headers.update({"Authorization": f"Bearer {API_KEY}"})
    
    def _load_config(self, config_path: str) -> SyncConfig:
        config_file = self.work_tree / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Config not found: {config_file}")
        with open(config_file) as f:
            raw_config = yaml.safe_load(f)
        return SyncConfig(**raw_config)
    
    def _should_sync(self, path: str) -> bool:
        path = Path(path)
        for pattern in self.config.sync.get("exclude_paths", []):
            if path.match(pattern):
                return False
        for pattern in self.config.sync.get("include_paths", []):
            if str(path).startswith(pattern.replace("*", "")):
                return True
        return False
    
    def _get_knowledge_mapping(self, path: str) -> Optional[Dict]:
        for prefix, mapping in self.config.knowledge_mappings.get("mappings", {}).items():
            if path.startswith(prefix):
                return mapping
        return None
    
    def _parse_frontmatter(self, content: str) -> tuple[Dict, str]:
        if not content.startswith("---"):
            return {}, content
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content
        fm_lines, rest = parts[1], parts[2]
        fm = {}
        for line in fm_lines.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                fm[key.strip()] = value.strip().strip('"').strip("'")
        return fm, rest
    
    def _extract_title(self, content: str, frontmatter: Dict) -> str:
        if "title" in frontmatter:
            return frontmatter["title"]
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return "Untitled"
    
    def _get_auto_tags(self, path: str, frontmatter: Dict) -> Set[str]:
        tags = set(frontmatter.get("tags", []))
        if self.config.processing.get("auto_tags", {}).get("from_path"):
            parts = Path(path).parts
            tags.update(parts[:-1])
        if self.config.processing.get("auto_tags", {}).get("from_filename"):
            name = Path(path).stem
            tags.update(name.replace("-", " ").replace("_", " ").split())
        return tags
    
    def _process_file(self, file_path: str, action: str = "upsert") -> Optional[KnowledgeFile]:
        full_path = self.work_tree / file_path
        if not self._should_sync(file_path):
            return None
        
        mapping = self._get_knowledge_mapping(file_path)
        if not mapping:
            return None
        
        if action == "delete":
            return KnowledgeFile(
                path=file_path, relative_path=file_path, content="",
                frontmatter={}, tags=[],
                knowledge_base=mapping.get("knowledge_base", ""),
                collection=mapping.get("collection", ""), action="delete"
            )
        
        if not full_path.exists():
            return None
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        frontmatter, body = self._parse_frontmatter(content)
        tags = list(self._get_auto_tags(file_path, frontmatter))
        
        if frontmatter.get("sync", {}).get("enabled", True) is False:
            return None
        
        return KnowledgeFile(
            path=file_path, relative_path=file_path, content=body.strip(),
            frontmatter=frontmatter, tags=tags,
            knowledge_base=mapping.get("knowledge_base", ""),
            collection=mapping.get("collection", ""), action="upsert"
        )
    
    def _upsert_document(self, file: KnowledgeFile) -> None:
        payload = {
            "title": self._extract_title(file.content, file.frontmatter),
            "content": file.content,
            "knowledge_base": file.knowledge_base,
            "collection": file.collection,
            "tags": file.tags,
            "metadata": {
                "source": "git",
                "path": file.path,
                "authors": file.frontmatter.get("authors", []),
                "date": file.frontmatter.get("date"),
                "status": file.frontmatter.get("status", "active"),
            }
        }
        doc_id = hashlib.md5(file.path.encode()).hexdigest()
        response = self.session.post(
            f"{BISHENG_API}/api/v1/knowledge/document",
            json={"id": doc_id, **payload}
        )
        if response.status_code not in (200, 201):
            raise Exception(f"API error: {response.status_code} {response.text}")
    
    def _delete_document(self, file: KnowledgeFile) -> None:
        doc_id = hashlib.md5(file.path.encode()).hexdigest()
        response = self.session.delete(
            f"{BISHENG_API}/api/v1/knowledge/document/{doc_id}"
        )
        if response.status_code not in (200, 204, 404):
            raise Exception(f"Delete error: {response.status_code}")
    
    def sync_to_bisheng(self, files: List[KnowledgeFile]) -> Dict:
        results = {"success": 0, "failed": 0, "errors": []}
        for file in files:
            try:
                if file.action == "delete":
                    self._delete_document(file)
                else:
                    self._upsert_document(file)
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{file.path}: {str(e)}")
        return results


def main():
    parser = argparse.ArgumentParser(description="BiSheng Knowledge Sync")
    parser.add_argument("--work-tree", required=True)
    parser.add_argument("--changed")
    parser.add_argument("--deleted")
    parser.add_argument("--new")
    parser.add_argument("--commit-range")
    args = parser.parse_args()
    
    service = BiShengSyncService(args.work_tree)
    files_to_sync = []
    
    for line in (args.changed or "").split("\n"):
        line = line.strip()
        if line:
            result = service._process_file(line, "upsert")
            if result:
                files_to_sync.append(result)
    
    for line in (args.new or "").split("\n"):
        line = line.strip()
        if line:
            result = service._process_file(line, "create")
            if result:
                files_to_sync.append(result)
    
    for line in (args.deleted or "").split("\n"):
        line = line.strip()
        if line:
            result = service._process_file(line, "delete")
            if result:
                files_to_sync.append(result)
    
    if files_to_sync:
        results = service.sync_to_bisheng(files_to_sync)
        print(json.dumps(results, indent=2))
    else:
        print(json.dumps({"success": 0, "failed": 0, "message": "No files to sync"}))


if __name__ == "__main__":
    main()
```

---

## 5. Obsidian Git 插件配置

### .gitignore

```gitignore
# Obsidian 系统文件
.obsidian/
workspace.json
*.md.bak

# 个人笔记 (不提交到团队仓库)
personal/**
personal/**/**/

# 草稿文件
*.draft.md
**/*.draft.md
**/drafts/**

# 本地附件
attachments/
.cache/
```

### Obsidian Git 插件配置

```json
{
  "autoCommitInterval": 15,
  "autoPush": true,
  "autoPull": true,
  "commitMessage": "vault backup: {{date}}",
  "include": [
    "_shared/**",
    "projects/**",
    "!**/*.draft.md",
    "!**/personal/**"
  ],
  "exclude": [
    ".obsidian/**",
    "*.md.bak",
    "**/drafts/**",
    "personal/**"
  ],
  "pullUpdates": true,
  "mergeConflicts": "ignore",
  "showStatusBar": true,
  "sideBarDisplay": "collapsed"
}
```

### 快捷命令配置

```json
{
  "hotkeys": [
    {
      "id": "sync-team-knowledge",
      "name": "Sync Team Knowledge",
      "keys": ["Ctrl+Shift+S"],
      "action": "obsidian-git:Commit and push changes"
    }
  ]
}
```

---

## 6. 部署检查清单

- [ ] 创建 Git 仓库
- [ ] 配置 post-receive hook
- [ ] 设置工作目录权限
- [ ] 安装 Python 依赖 (requests, pydantic, pyyaml)
- [ ] 配置环境变量 (BISHENG_API, BISHENG_API_KEY)
- [ ] 创建 BiSheng 知识库 (team:standards, team:technical, etc.)
- [ ] 配置 API 访问
- [ ] 克隆 Git 仓库到 Obsidian
- [ ] 配置 .gitignore
- [ ] 安装并配置 Obsidian Git 插件
- [ ] 测试自动同步

---

## 相关文档

- [Multi-repo 管理方式](../knowledge-sync/02-multi-repo-management.md)
- [系统架构总览](../architecture/01-architecture-overview.md)
- [数据模型定义](../architecture/07-data-models.md)
