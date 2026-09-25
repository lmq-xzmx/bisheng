# 知识管理文档

本目录包含 Obsidian + BiSheng 知识库整合方案及 Multi-repo 管理方式的相关文档。

## 文档列表

### 1. Obsidian + BiSheng 整合方案

**文件**: [01-obsidian-bisheng-integration.md](./01-obsidian-bisheng-integration.md)

包含内容：
- 整体架构设计
- Git 仓库结构与 SYNC_CONFIG.yaml 配置
- Git post-receive Hook 脚本
- BiSheng 同步服务 (sync.py)
- Obsidian Git 插件配置
- 部署检查清单

### 2. Multi-repo 管理方式

**文件**: [02-multi-repo-management.md](./02-multi-repo-management.md)

包含内容：
- Multi-repo vs Monorepo 对比
- 三种依赖管理方式（发布-订阅、Submodule、Subtree）
- 跨仓库操作工具（Repo、Lerna、自定义脚本）
- CI/CD 跨仓库触发
- 大规模架构建议

## 快速开始

### 部署 Obsidian + BiSheng 同步

1. 创建 Git 仓库并初始化：
```bash
git init knowledge-base
cd knowledge-base
git remote add origin https://github.com/org/knowledge-base.git
```

2. 创建同步配置：
```bash
cp SYNC_CONFIG.yaml.example SYNC_CONFIG.yaml
# 编辑 SYNC_CONFIG.yaml 配置知识库映射
```

3. 配置 Git Hook：
```bash
cp hooks/post-receive /var/www/knowledge-base.git/hooks/
chmod +x /var/www/knowledge-base.git/hooks/post-receive
```

4. 在 Obsidian 中：
- 安装 Obsidian Git 插件
- 克隆仓库到本地
- 配置自动同步

### Multi-repo 管理

使用自定义脚本批量管理：
```bash
python multi_repo_manager.py status --repos-dir ./org
python multi_repo_manager.py pull --repos-dir ./org
python multi_repo_manager.py grep "TODO" --repos-dir ./org
```

## 相关架构文档

- [系统架构总览](../architecture/01-architecture-overview.md)
- [数据模型定义](../architecture/07-data-models.md)
- [多租户架构](../architecture/12-multi-tenant.md)
