# Multi-repo 管理方式

本文档描述多仓库（Multi-repo）架构的管理方式、工具链和最佳实践。

---

## 1. Multi-repo vs Monorepo

| 维度 | Mono-repo | Multi-repo |
|------|-----------|------------|
| **仓库数量** | 1 | N |
| **依赖管理** | 简单 (内部引用) | 复杂 (需要包管理器) |
| **权限隔离** | 粗粒度 | 细粒度 |
| **构建速度** | 慢 (全量) | 快 (按需) |
| **跨库检索** | 简单 | 需要工具支持 |
| **适用规模** | <50 项目 | >50 项目 |

---

## 2. Multi-repo 典型使用场景

### 场景一：独立项目群

适用于团队管理多个相互独立的项目：

```
org/
├── project-alpha/      # 项目 A 独立仓库
├── project-beta/       # 项目 B 独立仓库
├── project-gamma/     # 项目 C 独立仓库
└── shared-libs/        # 共享库独立仓库
```

### 场景二：发布物管理

每个发布物对应一个独立仓库：

```
org/
├── ui-components/      # UI 组件库
├── utils/              # 工具库
├── api-client/         # API 客户端
└── shared-config/      # 共享配置
```

### 场景三：权限隔离

敏感项目独立仓库，严格控制访问：

```
org/
├── public-docs/        # 公开文档
├── internal-docs/      # 内部文档 (受限)
└── core-algorithm/     # 核心算法 (极受限)
```

---

## 3. 依赖管理方式

### 方式一：发布-订阅模式 (推荐)

```
项目 B (发布者)
    │
    │ 1. 开发 & 测试
    │ 2. 版本发布 (v1.2.3)
    ▼
私有包管理器 (npm / Maven / PyPI)
    │
    │ 3. 包可用
    ▼
项目 A (订阅者)
    │
    │ 4. 在 package.json 声明依赖
    │    "project-b": "^1.2.3"
    ▼
    5. npm install 自动下载
```

**优点**：版本明确、依赖清晰、易于回滚
**缺点**：需要维护包管理器、发布流程有开销

### 方式二：Git Submodule

```bash
# 在项目 A 中添加项目 B 作为子模块
cd project-a
git submodule add https://github.com/org/project-b.git libs/project-b

# 更新到最新版本
cd libs/project-b
git checkout main
git pull

# 提交子模块更新
cd ../..
git add libs/project-b
git commit -m "Update project-b to latest"
```

**优点**：直接引用源码、可跟踪变更
**缺点**：管理复杂、容易出现"孤儿提交"

### 方式三：Git Subtree

```bash
# 添加项目 B 作为 subtree
git subtree add --prefix=libs/project-b https://github.com/org/project-b.git main

# 更新到最新版本
git subtree pull --prefix=libs/project-b https://github.com/org/project-b.git main

# 从子目录提取出独立的仓库
git subtree split --prefix=libs/project-b -b split-branch
```

**优点**：历史可见、管理比 submodule 简单
**缺点**：会污染主项目历史

---

## 4. 跨仓库操作工具

### 4.1 Repo (Android 模式)

Google 开发的 Android 项目管理工具，通过 manifest 定义多仓库关系。

```bash
# 安装
curl https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo
chmod a+x ~/bin/repo

# 初始化 (需要 manifest 文件)
repo init -u https://github.com/org/manifest.git -b main

# 同步所有仓库
repo sync

# 在所有仓库执行命令
repo forall -c "git status"

# 上传修改
repo upload
```

### 4.2 Lerna (JavaScript)

管理多个 npm 包的工具，适合 JS/TS 项目。

```bash
# 初始化
npx lerna init

# 发布所有包
npx lerna publish

# 在所有包执行命令
npx lerna run build
npx lerna run test

# 添加依赖
npx lerna add lodash
```

### 4.3 自定义脚本

```python
#!/usr/bin/env python3
"""
multi_repo_manager.py
跨仓库批量操作管理工具
"""

import os
import subprocess
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


class MultiRepoManager:
    def __init__(self, repos_dir: str):
        self.repos_dir = Path(repos_dir)
        self.repos = self._discover_repos()
    
    def _discover_repos(self) -> list:
        """发现所有 Git 仓库"""
        repos = []
        for item in self.repos_dir.iterdir():
            if item.is_dir() and (item / ".git").exists():
                repos.append(item)
        return repos
    
    def _run_git(self, repo_path: Path, *args) -> tuple:
        """在指定仓库执行 git 命令"""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            return repo_path.name, result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return repo_path.name, -1, "", "Timeout"
    
    def status(self) -> dict:
        """查看所有仓库状态"""
        results = {}
        for repo in self.repos:
            _, code, stdout, _ = self._run_git(repo, "status", "--porcelain")
            results[repo.name] = {
                "clean": code == 0 and not stdout.strip(),
                "changes": stdout.strip() if stdout else ""
            }
        return results
    
    def pull_all(self, parallel: int = 4) -> dict:
        """并行拉取所有仓库"""
        results = {}
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(self._run_git, repo, "pull"): repo
                for repo in self.repos
            }
            for future in as_completed(futures):
                repo = futures[future]
                name, code, stdout, stderr = future.result()
                results[name] = {"success": code == 0, "message": stdout or stderr}
        return results
    
    def push_all(self) -> dict:
        """推送所有仓库"""
        results = {}
        for repo in self.repos:
            name, code, stdout, stderr = self._run_git(repo, "push")
            results[name] = {"success": code == 0, "message": stdout or stderr}
        return results
    
    def grep_all(self, pattern: str, file_type: str = "*.py") -> dict:
        """在所有仓库中搜索"""
        results = {}
        for repo in self.repos:
            _, code, stdout, _ = self._run_git(
                repo, "grep", "-n", "--full-name", pattern, "--", file_type
            )
            if stdout.strip():
                results[repo.name] = stdout.strip().split("\n")
        return results
    
    def backup_all(self, backup_dir: Path) -> dict:
        """备份所有仓库"""
        backup_dir.mkdir(parents=True, exist_ok=True)
        results = {}
        for repo in self.repos:
            backup_path = backup_dir / f"{repo.name}.git"
            _, code, _, _ = self._run_git(repo, "push", "--mirror", str(backup_path))
            results[repo.name] = {"success": code == 0}
        return results


def main():
    parser = argparse.ArgumentParser(description="Multi-repo Manager")
    parser.add_argument("command", choices=["status", "pull", "push", "grep", "backup"])
    parser.add_argument("--repos-dir", default="./org", help="Repositories directory")
    parser.add_argument("--pattern", help="Search pattern (for grep)")
    parser.add_argument("--backup-dir", help="Backup directory (for backup)")
    
    args = parser.parse_args()
    manager = MultiRepoManager(args.repos_dir)
    
    if args.command == "status":
        results = manager.status()
        for repo, status in results.items():
            print(f"{repo}: {'✅' if status['clean'] else '❌'}")
            if status['changes']:
                print(status['changes'])
    
    elif args.command == "pull":
        results = manager.pull_all()
        for repo, result in results.items():
            print(f"{repo}: {'✅' if result['success'] else '❌'}")
    
    elif args.command == "push":
        results = manager.push_all()
        for repo, result in results.items():
            print(f"{repo}: {'✅' if result['success'] else '❌'}")
    
    elif args.command == "grep":
        if not args.pattern:
            print("Error: --pattern required for grep")
            return
        results = manager.grep_all(args.pattern)
        for repo, matches in results.items():
            print(f"\n=== {repo} ===")
            for match in matches:
                print(match)
    
    elif args.command == "backup":
        if not args.backup_dir:
            print("Error: --backup-dir required for backup")
            return
        results = manager.backup_all(Path(args.backup_dir))
        for repo, result in results.items():
            print(f"{repo}: {'✅' if result['success'] else '❌'}")


if __name__ == "__main__":
    main()
```

**使用示例**：

```bash
# 查看所有仓库状态
python multi_repo_manager.py status --repos-dir ./org

# 拉取所有仓库最新代码
python multi_repo_manager.py pull --repos-dir ./org

# 在所有仓库搜索关键词
python multi_repo_manager.py grep "TODO" --repos-dir ./org

# 备份所有仓库
python multi_repo_manager.py backup --repos-dir ./org --backup-dir ./backups
```

---

## 5. CI/CD 跨仓库触发

### GitHub Actions 事件驱动

```yaml
# project-b/.github/workflows/on-release.yml
name: Notify Dependents

on:
  release:
    types: [published]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger project-a rebuild
        run: |
          curl -X POST \
            -H "Authorization: token ${{ secrets.PAT }}" \
            -H "Accept: application/vnd.github.v3+json" \
            https://api.github.com/repos/org/project-a/dispatches \
            -d '{"event_type":"dependency-update","client_payload":{"repo":"project-b","tag":"${{ github.ref_name }}"}}'

---
# project-a/.github/workflows/on-dependency-update.yml
name: Handle Dependency Update

on:
  repository_dispatch:
    types: [dependency-update]

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Update dependency
        run: |
          npm install project-b@${{ github.event.client_payload.tag }}
      
      - name: Create PR
        run: |
          git checkout -b chore/update-project-b
          git add package.json package-lock.json
          git commit -m "chore: update project-b to ${{ github.event.client_payload.tag }}"
          git push origin chore/update-project-b
          gh pr create --title "chore: update project-b" --body "Auto PR from project-b release"
```

---

## 6. 大规模 Multi-repo 架构建议

### 仓库数量 < 10

直接管理，每个仓库独立运作，共享代码通过 npm/Maven 包。

### 仓库数量 10-50

引入 Repo 或 Lerna 工具，manifest 文件集中管理。

```
org/
├── manifest/           # Repo manifest
│   └── default.xml
├── project-a/
├── project-b/
└── shared-libs/
```

### 仓库数量 > 50

考虑分组建模，按业务域划分仓库组：

```
org/
├── platform/           # 平台团队
│   ├── frontend/
│   ├── backend/
│   └── shared/
├── products/          # 产品团队
│   ├── product-x/
│   └── product-y/
└── infrastructure/    # 基础设施团队
    ├── ci-templates/
    └── deployment/
```

---

## 7. 工具对比

| 工具 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **Git Submodule** | 少量固定依赖 | 原生支持、简单 | 操作复杂、容易出错 |
| **Git Subtree** | 需要保留历史 | 历史可见 | 命令复杂 |
| **Repo** | 50+ 仓库 (Android 模式) | Google 背书、大规模支持 | 配置复杂 |
| **Lerna** | JS/TS 多包项目 | npm 生态集成 | 仅限 JS |
| **自定义脚本** | 通用场景 | 灵活控制 | 需要维护 |

---

## 相关文档

- [Obsidian + BiSheng 整合方案](./01-obsidian-bisheng-integration.md)
- [系统架构总览](../architecture/01-architecture-overview.md)
