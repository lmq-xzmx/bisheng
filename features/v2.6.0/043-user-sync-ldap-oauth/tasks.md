# Tasks: LDAP + OAuth 统一用户同步

**关联规格**: [spec.md](./spec.md)
**版本**: v2.6.0

---

## 状态

| 步骤 | 状态 | 备注 |
|------|------|------|
| spec.md | ✅ 已评审 | 用户于 2026-09-06 确认 |
| design.md | ✅ 已确认 | 架构设计已确认 |
| tasks.md | ✅ 已拆解 | Wave 1-4 已完成 |
| 实现 | 🔲 进行中 | 后端 Wave 1-4 完成，前端待开始 |

---

## 开发模式

**按 Wave 组织任务**：按依赖分组——无依赖的归 Wave 1（可并行），依赖前序的归后续 Wave。

**后端 Test-First（务实版）**：
- 核心 Service 写单元测试（mock DAO 层）
- API 层用 TestClient 集成测试
- 中间件/DM8/e2e 测试在 CI 跑

**前端手动验证**：每个任务附验证步骤。

---

## Tasks

### Wave 1 - 基础设施（无依赖）

- [ ] **T001**: 数据库配置表 ORM 模型
  **文件**: `src/backend/bisheng/user_sync/domain/models/oauth_config.py`,
           `src/backend/bisheng/user_sync/domain/models/ldap_config.py`,
           `src/backend/bisheng/user_sync/domain/models/user_sync_config.py`
  **逻辑**: 定义 SQLModel 表（含 tenant_id/create_time/update_time）
  **依赖**: 无

- [ ] **T002**: 错误码定义
  **文件**: `src/backend/bisheng/common/errcode/user_sync.py`
  **逻辑**: 定义 191xx (LDAP) / 192xx (OAuth) 错误码类
  **依赖**: 无

- [ ] **T003**: 枚举和常量定义
  **文件**: `src/backend/bisheng/user_sync/domain/constants.py`
  **逻辑**: SOURCE 常量、SyncStrategy 枚举、SyncOptions
  **依赖**: 无

### Wave 2 - 抽象层

- [ ] **T004**: UserSyncProvider ABC 定义
  **文件**: `src/backend/bisheng/user_sync/domain/providers/base.py`
  **逻辑**: 抽象基类定义 authenticate/get_user_attrs/sync_user 方法
  **测试**: `src/backend/test/user_sync/test_user_sync_provider_base.py`
  **依赖**: T001, T003

- [ ] **T005**: 用户同步公共逻辑 Service
  **文件**: `src/backend/bisheng/user_sync/domain/services/user_upsert_service.py`,
           `src/backend/bisheng/user_sync/domain/services/department_sync_service.py`
  **逻辑**: 从 sso_sync 抽取的公共用户 upsert 和部门同步逻辑
  **测试**: `src/backend/test/user_sync/test_user_upsert_service.py`
  **依赖**: T001, T004

### Wave 3 - LDAP Provider 实现

- [ ] **T006**: LDAP Provider 实现
  **文件**: `src/backend/bisheng/user_sync/domain/providers/ldap_provider.py`
  **逻辑**: 实现 UserSyncProvider，支持 ldap3 连接池、Bind 认证
  **测试**: `src/backend/test/user_sync/test_ldap_provider.py`
  **依赖**: T004, T005

- [ ] **T007**: LDAP API 端点
  **文件**: `src/backend/bisheng/user_sync/api/ldap.py`,
           `src/backend/bisheng/user_sync/api/router.py`
  **逻辑**: POST /api/v1/user/ldap/login
  **测试**: `src/backend/test/user_sync/test_ldap_api.py`
  **依赖**: T006

### Wave 4 - OAuth Provider 实现

- [ ] **T008**: OAuth State 管理 Service
  **文件**: `src/backend/bisheng/user_sync/domain/services/oauth_state_service.py`
  **逻辑**: Redis 存储 state、5分钟过期、HMAC 签名验证
  **测试**: `src/backend/test/user_sync/test_oauth_state_service.py`
  **依赖**: T003

- [ ] **T009**: OAuth Provider 基类
  **文件**: `src/backend/bisheng/user_sync/domain/providers/oauth_provider.py`
  **逻辑**: OAuth 通用流程：authorize URL 生成、token 交换、用户信息获取
  **依赖**: T004, T008

- [ ] **T010**: Google OAuth Provider 实现
  **文件**: `src/backend/bisheng/user_sync/domain/providers/google_provider.py`
  **逻辑**: 实现 Google OAuth2 流程
  **测试**: `src/backend/test/user_sync/test_google_provider.py`
  **依赖**: T009

- [ ] **T011**: OAuth API 端点
  **文件**: `src/backend/bisheng/user_sync/api/oauth.py`,
           `src/backend/bisheng/user_sync/api/providers.py`
  **逻辑**:
  - GET /api/v1/oauth/{provider}/authorize
  - GET /api/v1/oauth/{provider}/callback
  - GET /api/v1/oauth/providers
  **测试**: `src/backend/test/user_sync/test_oauth_api.py`
  **依赖**: T010

### Wave 5 - 管理员配置 API

- [ ] **T012**: OAuth Provider 管理 API
  **文件**: `src/backend/bisheng/user_sync/api/admin_oauth.py`
  **逻辑**: CRUD /admin/oauth-providers
  **依赖**: T001

- [ ] **T013**: LDAP Config 管理 API
  **文件**: `src/backend/bisheng/user_sync/api/admin_ldap.py`
  **逻辑**: GET/PUT /admin/ldap-config
  **依赖**: T001

### Wave 6 - 前端集成

- [ ] **T014**: 前端 OAuth Provider 动态渲染
  **文件**: `src/frontend/client/src/components/Auth/SocialLoginRender.tsx`
  **逻辑**: 调用 GET /api/v1/oauth/providers 动态渲染登录按钮
  **手动验证**:
  - 打开 http://localhost:4001/workspace/login
  - 确认显示的社交登录按钮与配置一致
  **依赖**: T011

- [ ] **T015**: 前端 LDAP 登录集成
  **文件**: `src/frontend/platform/src/pages/LoginPage/login.tsx`,
           `src/frontend/platform/src/controllers/API/userSync.ts`
  **逻辑**: 调用新的 /api/v1/user/ldap/login 端点
  **手动验证**:
  - 打开 http://localhost:3001/login
  - 使用 LDAP 账号登录成功
  **依赖**: T007

- [ ] **T016**: 前端配置管理页面（可选，Phase 2）
  **文件**: `src/frontend/platform/src/pages/Admin/UserSyncConfig/`
  **逻辑**: OAuth Provider 和 LDAP 配置的管理界面
  **依赖**: T012, T013

---

## 实际偏差记录

> 待 design.md 评审后补充

---

## 附录：关键文件清单

### 新增文件

```
src/backend/bisheng/user_sync/
├── __init__.py
├── api/
│   ├── __init__.py
│   ├── router.py
│   ├── ldap.py
│   ├── oauth.py
│   ├── providers.py
│   ├── admin_oauth.py
│   └── admin_ldap.py
└── domain/
    ├── __init__.py
    ├── constants.py
    ├── models/
    │   ├── __init__.py
    │   ├── oauth_config.py
    │   ├── ldap_config.py
    │   └── user_sync_config.py
    ├── providers/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── ldap_provider.py
    │   ├── oauth_provider.py
    │   └── google_provider.py
    └── services/
        ├── __init__.py
        ├── user_upsert_service.py
        ├── department_sync_service.py
        └── oauth_state_service.py

src/backend/bisheng/common/errcode/user_sync.py

src/backend/test/user_sync/
├── conftest.py
├── test_user_sync_provider_base.py
├── test_user_upsert_service.py
├── test_ldap_provider.py
├── test_ldap_api.py
├── test_oauth_state_service.py
├── test_google_provider.py
└── test_oauth_api.py
```

### 修改文件

```
src/frontend/client/src/components/Auth/SocialLoginRender.tsx
src/frontend/platform/src/pages/LoginPage/login.tsx
src/frontend/platform/src/controllers/API/userSync.ts
```
