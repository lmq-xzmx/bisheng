# F043 - 用户同步：LDAP + OAuth 统一认证

**版本**: v2.6.0
**创建日期**: 2026-09-06
**状态**: Draft

---

## 1. 概述与目标

### 1.1 背景

当前 BiSheng 系统支持：
- 本地用户名密码登录
- HMAC-SSO（通过 Java Gateway）
- 企业微信/飞书/钉钉组织同步

**缺失能力**：
- LDAP 企业账号登录（商业版专属，开源版未实现）
- OAuth 社交登录（Google/GitHub/微信/支付宝）

### 1.2 目标

构建统一的用户同步抽象层，支持 LDAP 和 OAuth 两种外部认证方式：
- **Phase 1**: LDAP + Google OAuth 各实现一个 Provider，验证架构
- **Phase 2**: 扩展更多 OAuth Provider（GitHub/微信/支付宝）

### 1.3 设计原则

| 原则 | 遵循情况 |
|------|----------|
| C1 DDD分层 | ✅ Router → Endpoint → Service → Repository |
| C3 多租户 | ✅ 所有配置下沉到租户级别 |
| C5 错误码 | ✅ 认证错误码 191xx |
| 架构复用 | ✅ 抽取 `UserSyncProvider(ABC)` 基类 |

---

## 2. 用户故事

### 2.1 LDAP 登录

| 角色 | 故事 |
|------|------|
| 企业员工 | 作为企业员工，我希望使用公司 AD/LDAP 账号登录 BiSheng，无需单独注册 |
| 管理员 | 作为系统管理员，我希望配置全局 LDAP 服务器，让所有租户使用；同时允许租户覆盖为自己的 LDAP |
| 管理员 | 我希望控制首次登录时是否自动创建本地账号，或要求管理员预分配 |

### 2.2 OAuth 登录

| 角色 | 故事 |
|------|------|
| 最终用户 | 作为用户，我希望使用 Google/GitHub 账号登录 BiSheng |
| 管理员 | 作为系统管理员，我希望在数据库配置启用的 OAuth Provider，用户登录页动态显示可用选项 |
| 最终用户 | 作为已登录用户，我登出 BiSheng 时不希望同时登出 Google/GitHub 会话 |

---

## 3. 架构设计

### 3.1 模块结构

```
src/backend/bisheng/
├── user_sync/                        # 新增：统一用户同步模块
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py                # 路由汇总
│   │   ├── ldap.py                  # LDAP 端点
│   │   ├── oauth.py                 # OAuth 端点
│   │   └── providers.py             # Provider 配置 API
│   └── domain/
│       ├── __init__.py
│       ├── constants.py             # SOURCE 常量
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py              # UserSyncProvider(ABC)
│       │   ├── ldap_provider.py     # LDAP 实现
│       │   └── oauth_provider.py    # OAuth 实现
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── ldap.py              # LDAP 请求/响应 Schema
│       │   └── oauth.py             # OAuth 请求/响应 Schema
│       └── services/
│           ├── __init__.py
│           ├── user_upsert_service.py    # 公共用户 upsert
│           ├── department_sync_service.py # 公共部门同步
│           └── oauth_state_service.py    # OAuth state 管理
```

### 3.2 抽象层设计

#### UserSyncProvider (ABC)

```python
class UserSyncProvider(ABC):
    """用户同步 Provider 抽象基类"""

    @property
    @abstractmethod
    def source(self) -> str:
        """认证源标识：ldap / google / github / wechat / alipay"""
        pass

    @abstractmethod
    async def authenticate(self, request: Request) -> AuthResult:
        """
        验证请求并返回认证结果
        - LDAP: Bind 用户
        - OAuth: 交换 token 并验证
        """
        pass

    @abstractmethod
    async def get_user_attrs(self, auth_result: AuthResult) -> UserAttrs:
        """从认证结果提取用户属性"""
        pass

    async def sync_user(
        self,
        external_id: str,
        user_attrs: UserAttrs,
        tenant_id: int,
        options: SyncOptions
    ) -> User:
        """
        公共用户同步逻辑（已实现，可被子类复用或 override）
        包含：用户 upsert、部门同步、叶租户同步、JWT 签发
        """
        pass
```

#### SyncOptions 配置

```python
class SyncOptions:
    auto_register: bool          # 是否自动创建用户
    sync_email: SyncStrategy     # 邮箱同步策略
    sync_phone: SyncStrategy     # 手机同步策略
    sync_name: SyncStrategy      # 姓名同步策略
    sync_department: bool        # 是否同步部门
    logout_redirect_oauth: bool  # 登出时是否重定向到 OAuth Provider
```

#### SyncStrategy 枚举

```python
class SyncStrategy(Enum):
    ALWAYS = "always"           # 每次登录同步
    FIRST_ONLY = "first_only"   # 仅首次同步
    MANUAL = "manual"           # 手动同步
    NEVER = "never"             # 从不同步
```

### 3.3 数据模型

#### 新增配置表

**oauth_provider_config** - OAuth Provider 配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK |  |
| tenant_id | int FK | 租户 ID，NULL 表示全局 |
| provider | str | google / github / wechat / alipay |
| enabled | bool | 是否启用 |
| client_id | str | OAuth Client ID |
| client_secret_encrypted | str | 加密后的 Client Secret |
| redirect_uri | str | 回调地址 |
| scopes | str | 权限范围，JSON |
| config_json | JSON | Provider 特定配置 |
| created_at | datetime |  |
| updated_at | datetime |  |

**ldap_config** - LDAP 配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK |  |
| tenant_id | int FK | 租户 ID，NULL 表示全局 |
| enabled | bool | 是否启用 |
| server_url | str | ldap:// 或 ldaps:// |
| base_dn | str | 搜索基础 DN |
| bind_dn | str | 绑定 DN |
| bind_password_encrypted | str | 加密后的密码 |
| user_filter | str | 用户搜索过滤器 |
| use_ssl | bool | 是否 SSL |
| timeout | int | 超时秒数 |
| auto_register | bool | 是否自动创建 |
| sync_strategies | JSON | 各字段同步策略 |
| created_at | datetime |  |
| updated_at | datetime |  |

**user_sync_config** - 用户同步行为配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK |  |
| tenant_id | int FK | 租户 ID |
| source | str | ldap / google / ... |
| auto_register | bool |  |
| sync_email | str | SyncStrategy |
| sync_phone | str | SyncStrategy |
| sync_name | str | SyncStrategy |
| sync_department | bool |  |
| logout_redirect_oauth | bool |  |

---

## 4. API 设计

### 4.1 LDAP 端点

#### POST /api/v1/user/ldap/login

**描述**: LDAP 用户登录

**请求**:
```json
{
  "username": "zhangsan",
  "password": "encrypted_password",
  "tenant_id": 1,
  "captcha_key": "xxx",
  "captcha": "1234"
}
```

**响应** (成功):
```json
{
  "user_id": 123,
  "user_name": "张三",
  "access_token": "eyJ...",
  "token_type": "bearer",
  "is_global_super": false,
  "default_entry": "client"
}
```

**响应** (需要 2FA):
```json
{
  "require_2fa": true,
  "temp_token": "xxx"
}
```

### 4.2 OAuth 端点

#### GET /api/v1/oauth/{provider}/authorize

**描述**: 获取 OAuth 授权 URL

**参数**:
- `provider`: google / github / wechat / alipay
- `state`: CSRF protection
- `redirect_uri`: 登录成功后的跳转地址（可选）

**响应**:
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

#### GET /api/v1/oauth/{provider}/callback

**描述**: OAuth 回调端点

**参数**:
- `provider`: google / github / wechat / alipay
- `code`: Authorization Code
- `state`: CSRF token

**响应**: 与 LDAP 登录相同

#### GET /api/v1/oauth/providers

**描述**: 获取启用的 OAuth Provider 列表（前端动态渲染用）

**响应**:
```json
{
  "providers": [
    {"id": "google", "name": "Google", "icon": "google.svg", "enabled": true},
    {"id": "github", "name": "GitHub", "icon": "github.svg", "enabled": true},
    {"id": "wechat", "name": "微信", "icon": "wechat.svg", "enabled": false}
  ]
}
```

### 4.3 管理员配置端点

#### GET /api/v1/admin/oauth-providers

**描述**: 获取 OAuth Provider 配置列表

#### POST /api/v1/admin/oauth-providers

**描述**: 创建 OAuth Provider 配置

#### PUT /api/v1/admin/oauth-providers/{id}

**描述**: 更新 OAuth Provider 配置

#### GET /api/v1/admin/ldap-config

**描述**: 获取 LDAP 配置

#### PUT /api/v1/admin/ldap-config

**描述**: 更新 LDAP 配置

---

## 5. 前端集成

### 5.1 社交登录动态渲染

**修改文件**: `src/frontend/client/src/components/Auth/SocialLoginRender.tsx`

**改动**:
1. 移除硬编码的 Provider 列表
2. 登录页加载时调用 `GET /api/v1/oauth/providers`
3. 根据返回的 `providers` 数组动态渲染登录按钮

### 5.2 LDAP 登录

**修改文件**: `src/frontend/platform/src/pages/LoginPage/login.tsx`

**改动**:
1. 移除对 `pro.ts` 中 `ldapLoginApi()` 的依赖
2. 改为调用新的 `/api/v1/user/ldap/login` 端点

---

## 6. 错误处理

### 6.1 错误码

| 错误码 | 说明 |
|--------|------|
| 19101 | LDAP 连接失败 |
| 19102 | LDAP 认证失败（用户名或密码错误） |
| 19103 | LDAP 用户不存在 |
| 19104 | LDAP 账号已禁用 |
| 19201 | OAuth Provider 不可用 |
| 19202 | OAuth 授权失败 |
| 19203 | OAuth State 验证失败 |
| 19204 | OAuth Token 交换失败 |
| 19205 | OAuth 用户信息获取失败 |

### 6.2 错误展示策略

| 场景 | 用户看到 | 日志记录 |
|------|----------|----------|
| 认证失败 | "登录失败，请联系管理员" | 详细错误原因 |
| 网络错误 | "网络连接失败，请重试" | 完整堆栈 |
| 配置错误 | "服务暂时不可用" | 详细配置问题 |

---

## 7. 安全考虑

### 7.1 OAuth 安全

- **State 参数**: 随机生成，存 Redis，5分钟过期
- **HMAC 签名**: 可选的请求完整性验证
- **Token 处理**: Access Token 不存储，仅用一次获取用户信息

### 7.2 LDAP 安全

- **密码传输**: 前端 RSA 加密传输
- **Bind DN 最小权限**: 不使用管理员账号绑定
- **连接加密**: 支持 LDAPS (SSL)

---

## 8. Phase 1 范围

### 8.1 完成标准

| 功能 | 验收条件 |
|------|----------|
| LDAP 登录 | 能用企业 AD/LDAP 账号登录 |
| LDAP 配置 | 管理员能在后台配置 LDAP 服务器 |
| Google OAuth | 能用 Google 账号登录 |
| OAuth 动态渲染 | 登录页根据配置动态显示 Provider |
| 架构验证 | 能快速添加新 Provider（GitHub） |

### 8.2 不在 Phase 1 范围

- 微信/支付宝 OAuth（Phase 2）
- 用户信息手动同步按钮
- LDAP 写回（修改密码等）
- 多 LDAP 源同时支持

---

## 9. 参考资料

- [Constitution](../constitution.md)
- [SSO Sync 模块](../sso_sync/) - 现有 HMAC-SSO 实现
- [Permission Architecture](../architecture/10-permission-rbac.md)
- [Multi-tenant Architecture](../architecture/12-multi-tenant.md)
