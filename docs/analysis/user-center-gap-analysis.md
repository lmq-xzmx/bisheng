# BiSheng 用户中心差距分析报告

> 分析日期：2026-07-25
> 基于版本：v2.6.0

---

## 一、当前账号与权限体系全貌

### 1.1 登录方式

| 方式 | 状态 | 说明 |
|---|---|---|
| 用户名 + 密码（MD5） | ✅ 已实现 | 前端 RSA 加密传输，后端 MD5 存储，`/api/v1/user/login` |
| 自注册 | ✅ 已实现 | 有验证码保护，首个注册用户自动成为 super_admin |
| HMAC-SSO 回调 | ✅ 已实现 | `/api/v1/internal/sso/login-sync`，商业版 Java Gateway 调用 |
| 部门/用户批量同步 | ✅ 已实现 | `/api/v1/departments/sync` + `/api/v1/internal/sso/gateway-wecom-org-sync` |
| 企业微信/飞书/钉钉组织同步 | ✅ 已实现（拉取模式） | Celery 定时任务，不是交互式登录 |
| LDAP 登录 | ⚠️ 存在路由但未实现 | `/api/v1/user/ldap` 在中间件白名单中，但后端无 handler，需经 Java Gateway 代理 |
| OAuth2 / OIDC / SAML | ❌ 后端未实现 | 全部由商业版 Java Gateway 处理，后端只接收 HMAC 回调 |
| MFA / 2FA | ❌ 未实现 | 代码中无 `pyotp`/`webauthn` 等依赖 |
| 无密码登录（Magic Link） | ❌ 未实现 | `phone_number`/`email` 字段存在但未用于认证 |

### 1.2 JWT 与会话管理

- **算法**：HS256（对称），密钥默认硬编码在代码中
- **Payload**：`{user_id, user_name, tenant_id, token_version}`
- **有效期**：默认 24 小时（可配置）
- **Token 失效**：通过 `token_version` 递增实现，存储在 MySQL + Redis 两级
- **会话追踪**：`USER_CURRENT_SESSION` Redis key，但管理端无 UI
- **多设备登录**：`allow_multi_login` 控制，但不彻底
- **WebSocket 认证**：通过 URL query param `?t=...` 或 Cookie

### 1.3 权限模型：RBAC + ReBAC 双轨制

**ReBAC（OpenFGA）— 目标架构**
- 16 种对象类型，权限金字塔 `owner > manager > editor > viewer`
- 支持跨租户资源共享（F013）
- L1~L6 权限检查链

**Legacy RBAC（仍活跃）**
- `userrole` / `role` / `roleaccess` / `usergroup` 等 MySQL 表
- `LegacyRBACSyncService` 负责两者同步

### 1.4 租户隔离

- **44 张表**通过 `tenant_id` 逻辑隔离
- 5 种存储引擎（MySQL / MinIO / Milvus / ES / Redis）全部按租户前缀划分
- **ContextVar** 注入 `current_tenant_id`，SQLAlchemy 事件自动追加 WHERE 条件
- 支持**租户树**（Root + Child tenants），FGA `tenant#admin` 授权

---

## 二、作为多套系统用户中心的差距

| 维度 | BiSheng 当前 | 多系统用户中心需求 | 差距 |
|---|---|---|---|
| **统一用户池** | 每套 BiSheng 独立 `user` 表 | 跨系统共享同一用户库 | ❌ 无中央用户库，各部署独立 |
| **SSO 跨实例** | 本部署内 HMAC callback | 一次登录访问所有子系统 | ❌ 无法跨 BiSheng 实例 |
| **身份提供商** | 自身是 IdP，也接受外部 SSO | 应同时支持作为 IdP 和 SP | ❌ 没有 OIDC/SAML Provider 能力 |
| **用户 Provisioning** | 仅 OrgSync 拉取 | 需要 SCIM 推送接收 | ❌ 无 SCIM 端点 |
| **Token 互认** | 自身 JWT | 外部系统应能验证 BiSheng Token | ❌ 无 token introspection / JWKS |
| **统一会话管理** | 内部 Redis 追踪 | 跨系统单点会话 | ❌ 无 |
| **LDAP 直接绑定** | `/api/v1/user/ldap` 是空路由 | 很多企业要求 LDAP 直登 | ❌ 必须绕道 Java Gateway |
| **用户数据导出** | 无 | GDPR 等合规需要 | ❌ 无 |
| **批量用户管理** | 只能管理员逐个创建 | 需要 CSV 导入 / API 批量操作 | ❌ 无 |

---

## 三、SSO 支持情况

### 3.1 当前 SSO 路径

```
外部 IdP（如企业微信、飞书、钉钉、定制 OAuth）
        ↓
   商业版 Java Gateway（bisheng-gateway）
   JustAuth 1.16.6 处理 OAuth2 流程
        ↓ HMAC-SHA256 签名回调
   /api/v1/internal/sso/login-sync （后端唯一入口）
        ↓
   返回 JWT，登录完成
```

### 3.2 局限

1. **只支持 Gateway 认识的 Provider** — 通用 OAuth2/OIDC 需要在 Java Gateway 侧扩展
2. **没有 SAML 支持** — 企业常用 ADFS/Okta/OneLogin 等 SAML IdP 无法直连
3. **没有 OIDC 协议层** — 无 JWKS、无 ID Token 验证、无 OIDC Discovery
4. **后端不管理 OAuth 流程** — 所有上游 OAuth 由 Java Gateway 处理

### 3.3 同租户跨系统 SSO 可行路径

**路径 1：轻量改造 — 暴露 Token 验证接口（最小改动）**
```
外部系统 ──POST /api/v1/auth/introspect──→ BiSheng
           { token: "xxx" }
                                          ↓
                              验证 JWT 签名 + token_version
                              返回 { active: true, user_id, tenant_id }
```

**路径 2：OIDC 化 — BiSheng 作为轻量 OIDC Provider**
- 新增 `/oidc/.well-known/openid-configuration`
- 新增 `/oidc/authorize`、`/oidc/token`、`/oidc/userinfo`、`/oidc/jwks`

**路径 3：Cookie 共享（SSO 单点会话）**
- 同一顶级域名下，通过 Cookie 共享实现免登

---

## 四、OIDC / SAML IdP 能力

### 4.1 OIDC（OpenID Connect）

OIDC 是建立在 OAuth 2.0 之上的**身份层协议**，本质是一个"带身份信息的 OAuth2"。

**OIDC 的核心价值：标准化的用户信息 + 协议互操作性**

OIDC 工作流：
```
1. RP 向 OP 发起认证请求（带 client_id, redirect_uri, scope=openid）
2. OP 显示登录页面，用户输入凭证
3. OP 回调 RP 的 redirect_uri，带上 ?code=xxx
4. RP 用 code 换 ID Token（JWT）+ Access Token
5. RP 验证 ID Token（签名、issuer、audience、exp）
6. 提取 sub/email/name 等 Claims 完成登录
```

**关键能力：**
- **Discovery** — 协议元数据自动发现，RP 只需知道 IdP 的 Issuer URL
- **JWKS** — 公钥自动获取，ID Token 签名自动验证
- **ID Token** — 标准 JWT，含 `sub`/`email`/`name` 等标准 Claims
- **Token Introspection** — 资源方可以验证 Token 有效性

### 4.2 SAML 2.0

SAML 是比 OIDC 更老的 XML-based SSO 协议，主要用于**企业内网**。

| | SAML | OIDC |
|---|---|---|
| 协议载体 | XML | JSON (JWT) |
| 复杂度 | 高 | 低 |
| 主要场景 | 企业内网（ADFS、Okta） | 云 SaaS + 企业内网 |
| Token 大小 | 大 | 小 |
| 主要 IdP 支持 | 几乎全部支持 | 几乎全部支持 |

### 4.3 当前 BiSheng 的 IdP 能力

**BiSheng 不具备 IdP 能力**：
- 不发行 OIDC ID Token（只消费）
- 不暴露 JWKS 端点
- 没有 SAML Metadata

---

## 五、用户数据模型差距

### 5.1 User 字段现状

`user/domain/models/user.py:21-101`：

```
user_id, user_name, email, phone_number, dept_id(字符串), remark, avatar,
source, external_id, delete, disable_source, password, password_update_time,
token_version, create_time, update_time
```

### 5.2 缺失字段

| 缺失项 | 影响 |
|---|---|
| **无自定义字段** | 无法存储工号、职位、地点、成本中心、经理等企业属性 |
| **无姓名分拆** | 只有 `user_name`，无 `first_name`/`last_name`/`display_name` |
| **无最后登录时间/IP** | 无法做登录历史、异常检测、新设备告警 |
| **无邮箱/手机认证标记** | `email_verified`、`phone_verified` 不存在 |
| **无 MFA 相关字段** | 无 `mfa_enabled`、`mfa_secret`、`backup_codes` |
| **`dept_id` 是自由字符串** | 不是外键，与 `UserDepartment` 表并存，造成双数据源 |
| **`user_link` 表被挪用** | 本应是"第三方账号绑定表"，实际用来存"收藏流程" |

---

## 六、用户生命周期管理差距

### 6.1 批量操作

| 功能 | 现状 |
|---|---|
| **CSV/Excel 批量导入** | ❌ 完全不存在 |
| **批量启用/禁用/删除** | ❌ 不存在。前端无复选框，无批量操作 |
| **用户合并/去重** | ❌ 不存在 |
| **用户数据导出（GDPR）** | ❌ 不存在 |
| **资源所有权转移** | ❌ 禁用用户后，其拥有的资源无人继承 |

### 6.2 生命周期状态

```
当前状态机：
  active (delete=0)
      ↓ 管理员禁用
  disabled (delete=1)
```

缺失：激活待定 → 已激活 → 暂停 → 注销 等完整生命周期。

---

## 七、密码策略差距

### 7.1 已实现

- 正则强度检查：`^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,128}$`
- 密码有效期检查（仅在登录时触发）
- 错误次数锁定（Redis 计数器）

### 7.2 深度缺失

| 功能 | 现状 |
|---|---|
| **密码历史（防重复使用）** | ❌ 无 `password_history` 表 |
| **密码策略可配置** | ❌ 正则硬编码，无 admin UI 修改 |
| **常见密码黑名单** | ❌ 无 |
| **强制首次登录改密** | ❌ 无 |
| **即将过期主动通知** | ❌ 无 |
| **最小长度可配置** | ❌ 永远是 8 位 |

---

## 八、账户安全差距

### 8.1 登录保护现状

`user/domain/services/user.py:215-245` — 仅针对 `user_id` 的计数器，不针对 IP：

```python
Redis: USER_PASSWORD_ERROR:{user_id} → INCR + EXPIRE
超限 → delete=1（禁用账户）
```

### 8.2 深度缺失

| 缺失 | 说明 |
|---|---|
| **IP 级别限速** | 对 `/api/v1/user/login` 无中间件限速 |
| **IP 白名单/黑名单** | 完全不存在 |
| **登录异常检测** | 无新设备 / 新位置 / 异地登录检测 |
| **会话列表** | `USER_CURRENT_SESSION` 只存最新一个 JWT，无列表接口 |
| **强制下线** | 无 "踢出此会话" 接口 |
| **MFA / 2FA** | 完全不存在 |

**关键问题**：暴力破解防护仅针对已存在的用户名，对不存在用户名的请求完全无限制。

---

## 九、组织结构差距

### 9.1 已实现

- materialized path 部门树（`/1/21/106/`）
- `UserDepartment` 多对多支持

### 9.2 深度缺失

| 功能 | 现状 |
|---|---|
| **角色继承/层级** | ❌ 无 `parent_role_id` |
| **岗位/职位表** | ❌ 无 |
| **汇报线（manager_id）** | ❌ 无 |
| **代理权限（Acting As）** | ❌ 无 |
| **动态用户组（LDAP-style filter）** | ❌ 用户组是静态的 |
| **用户类型分类** | 只有 `local` vs SSO source，无 service account / guest |

---

## 十、UserCenter API 完备性

### 10.1 已实现

`login`, `logout`, `regist`, `info`, `list`, `create`, `update`, `reset_password`, `change_password`, `avatar`, `get_captcha`, `public_key`

### 10.2 缺失的关键接口

| 接口 | 用途 |
|---|---|
| `GET /users/{id}` | 按 ID 获取单个用户档案 |
| `PATCH /users/{id}` | 更新用户档案 |
| `DELETE /users/{id}` | 硬删除 |
| `POST /users/import` | CSV 批量导入 |
| `GET /users/export` | 用户数据导出 |
| `GET /users/me/sessions` | 当前用户所有会话列表 |
| `DELETE /users/me/sessions/{sid}` | 主动下线指定会话 |
| `GET /users/me/login-history` | 登录历史 |
| `POST /users/{id}/unlock` | 解锁（区别于重新启用） |
| `POST /users/{id}/transfer-ownership` | 转移资源所有权 |
| `POST /users/{id}/mfa/setup` | MFA 配置 |
| `GET /users/search` | 全文搜索 |

---

## 十一、高优先级差距汇总

| 优先级 | 维度 | 具体差距 |
|---|---|---|
| 🔴 高 | 安全 | 无 MFA、无 IP 限速、无密码历史、暴力破解防护仅针对已存在用户名 |
| 🔴 高 | 批量 | 无 CSV 导入、无批量启用/禁用/删除 |
| 🔴 高 | 前端 | 无用户详情页、无批量操作 UI、无会话管理 |
| 🔴 高 | 生命周期 | 无数据导出、无所有权转移、无锁定/解锁区分 |
| 🟡 中 | 数据模型 | 无自定义字段、无 `last_login_*`、无 `email_verified` |
| 🟡 中 | 密码 | 策略硬编码、无历史防重用、无主动过期通知 |
| 🟡 中 | API | 无 PATCH profile、无会话列表接口、无 MFA 接口 |
| 🟡 中 | 组织 | 无角色层级、无岗位表、无汇报线 |

---

## 十二、改造路线建议

**第一阶段（安全加固）**：MFA + IP 限速 + 密码历史 + 登录异常检测
**第二阶段（批量能力）**：CSV 导入 + 批量操作 + 用户合并 + GDPR 导出
**第三阶段（用户中心 UI）**：独立用户管理模块 + 详情页 + 会话管理 + 密码策略配置

---

## 十三、关键文件索引

| 组件 | 关键文件 |
|---|---|
| JWT / Auth | `src/backend/bisheng/user/domain/services/auth.py` |
| 登录 API | `src/backend/bisheng/user/api/user.py` |
| 用户模型 | `src/backend/bisheng/user/domain/models/user.py` |
| 密码服务 | `src/backend/bisheng/user/domain/services/user.py` |
| HMAC SSO | `src/backend/bisheng/sso_sync/domain/services/hmac_auth.py` |
| SSO 登录同步 | `src/backend/bisheng/sso_sync/domain/services/login_sync_service.py` |
| OpenFGA | `src/backend/bisheng/core/openfga/` |
| 权限服务 | `src/backend/bisheng/permission/domain/services/permission_service.py` |
| 租户隔离 | `src/backend/bisheng/core/database/tenant_filter.py` |
| 架构文档 | `docs/architecture/10-permission-rbac.md`、`11-gateway.md`、`12-multi-tenant.md` |
