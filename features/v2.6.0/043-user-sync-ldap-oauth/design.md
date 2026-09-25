# Design: LDAP + OAuth 统一用户同步

**关联规格**: [spec.md](./spec.md)
**版本**: v2.6.0
**状态**: Draft

---

## 调整原则

> 如果实现过程中发现规格不可行，在这里记录调整决策（§3 SDD-Guide）。

---

## 1. 架构概览

### 1.1 设计目标

构建统一的用户同步抽象层 `user_sync`，支持 LDAP 和 OAuth 两种外部认证方式，与现有 `sso_sync` 模块并行存在。

**核心原则**：
- **完整抽象**: 抽取 `UserSyncProvider(ABC)` 基类，复用 `LoginSyncService` 的公共逻辑
- **配置驱动**: OAuth Provider 列表由数据库配置，前端动态渲染
- **多租户友好**: 所有配置下沉到租户级别

### 1.2 模块关系图

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Client/Platform)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    user_sync/api/                           │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────────┐ │
│  │  ldap.py │  │ oauth.py │  │ providers  │  │admin_xxx │ │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘  └────┬─────┘ │
└───────┼─────────────┼──────────────┼──────────────┼───────┘
        │             │              │              │
        ▼             ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│               user_sync/domain/providers/                   │
│  ┌────────────────────────┐  ┌────────────────────────────┐│
│  │   UserSyncProvider     │  │   OAuthProvider (ABC)      ││
│  │   (ABC)                │  │                            ││
│  └───────────┬────────────┘  └────────────┬───────────────┘│
│              │                            │                 │
│     ┌────────┴────────┐          ┌───────┴───────┐         │
│     ▼                 ▼          ▼               ▼         │
│ ┌────────┐      ┌────────┐  ┌────────┐     ┌──────────┐   │
│ │  LDAP  │      │OAuth   │  │ Google │     │  GitHub  │   │
│ │Provider│      │Provider│  │Provider│     │ Provider │   │
│ └────────┘      └────────┘  └────────┘     └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               user_sync/domain/services/                    │
│  ┌──────────────────────┐  ┌──────────────────────────────┐│
│  │  UserUpsertService   │  │  DepartmentSyncService       ││
│  │  (抽取自 sso_sync)    │  │  (抽取自 sso_sync)           ││
│  └──────────────────────┘  └──────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 1.3 与 sso_sync 的关系

| 方面 | sso_sync | user_sync |
|------|----------|-----------|
| 定位 | Java Gateway HMAC-SSO 回调 | LDAP/OAuth 直接集成 |
| 认证协议 | HMAC-SHA256 签名 | LDAP Bind / OAuth2 |
| 用户来源 | Gateway 推送 | 实时认证 |
| 典型场景 | 企业微信/飞书/钉钉 | 企业 AD / 社交登录 |

**复用策略**：
- `UserUpsertService` 从 `LoginSyncService._upsert_user` 抽取
- `DepartmentSyncService` 从 `LoginSyncService` 的部门逻辑抽取
- `UserTenantSyncService` 已在 `tenant/` 模块，直接复用

---

## 2. 核心组件设计

### 2.1 UserSyncProvider (ABC)

**文件**: `user_sync/domain/providers/base.py`

```python
class UserSyncProvider(ABC):
    """用户同步 Provider 抽象基类"""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

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
        options: SyncOptions
    ) -> tuple[User, str]:
        """
        公共用户同步逻辑
        返回: (User, access_token)
        """
        # 1. 用户 upsert
        user = await UserUpsertService.upsert_user(
            source=self.source,
            external_id=external_id,
            user_attrs=user_attrs,
            tenant_id=self.tenant_id,
            options=options,
        )

        # 2. JWT 签发
        token = AuthJwt.create_access_token(user)

        return user, token
```

### 2.2 LDAP Provider 实现

**文件**: `user_sync/domain/providers/ldap_provider.py`

**关键设计点**：

1. **连接池管理**: 使用 `ldap3.ServerPool` + `ldap3.Connection Pool`
2. **用户标识**: 以员工号(uid)为主键，邮箱/手机为备用查找键
3. **认证流程**:
   - 用户提供 username + 加密密码
   - 构建 Bind DN: `uid={username},ou=users,{base_dn}`
   - 执行 LDAP Bind
   - 查询用户属性（姓名、邮箱、手机、部门）

4. **配置优先级**: 租户级配置 > 全局配置

```python
class LdapProvider(UserSyncProvider):
    source = "ldap"

    def __init__(self, tenant_id: int):
        super().__init__(tenant_id)
        self.config = self._get_config()  # 混合模式配置获取

    def _get_config(self) -> LdapConfig:
        # 1. 查租户级配置
        # 2. 如果没有，查全局配置
        # 3. 如果都没有，抛异常
        pass

    async def authenticate(self, request: Request) -> AuthResult:
        body = await request.json()
        username = body["username"]
        password = decrypt_password(body["password"])  # 前端RSA加密

        # 构建 Bind DN
        bind_dn = self._build_bind_dn(username)

        # 使用连接池执行 Bind
        with self._get_connection() as conn:
            # 1. Bind 认证
            conn.bind()

            # 2. 查询用户信息
            user_entry = self._search_user(conn, username)

            return AuthResult(
                external_id=user_entry["uid"],
                name=user_entry["cn"],
                email=user_entry.get("mail"),
                phone=user_entry.get("mobile"),
                department=user_entry.get("department"),
                raw_attributes=user_entry,
            )
```

### 2.3 OAuth Provider 实现

**文件**: `user_sync/domain/providers/oauth_provider.py`

```python
class OAuthProvider(UserSyncProvider):
    """OAuth Provider 基类"""

    def __init__(self, tenant_id: int, provider: str):
        super().__init__(tenant_id)
        self.provider = provider
        self.config = self._get_config(provider)

    @abstractmethod
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """生成授权 URL"""
        pass

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        """交换 authorization code 获取 token"""
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> UserAttrs:
        """获取用户信息"""
        pass

    async def authenticate(self, request: Request) -> AuthResult:
        # 1. 验证 state
        state = request.query_params.get("state")
        code = request.query_params.get("code")

        await OAuthStateService.verify_and_delete(state, self.provider)

        # 2. 交换 token
        tokens = await self.exchange_code(code)

        # 3. 获取用户信息
        user_attrs = await self.get_user_info(tokens["access_token"])

        return AuthResult(
            external_id=user_attrs.sub or user_attrs.email,
            name=user_attrs.name,
            email=user_attrs.email,
            phone=user_attrs.phone,
        )
```

### 2.4 Google Provider 实现

**文件**: `user_sync/domain/providers/google_provider.py`

```python
class GoogleProvider(OAuthProvider):
    source = "google"

    def __init__(self, tenant_id: int):
        super().__init__(tenant_id, "google")

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "redirect_uri": self.config.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            return resp.json()

    async def get_user_info(self, access_token: str) -> UserAttrs:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()
            return UserAttrs(
                sub=data["id"],
                name=data["name"],
                email=data["email"],
                picture=data.get("picture"),
            )
```

---

## 3. 数据模型设计

### 3.1 OAuth 配置表 (oauth_provider_config)

```python
class OAuthProviderConfig(SQLModel, table=True):
    __tablename__ = "oauth_provider_config"

    id: int = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, index=True)  # NULL = 全局
    provider: str = Field(max_length=32, index=True)  # google/github/wechat/alipay
    enabled: bool = Field(default=False)
    client_id: str = Field(max_length=256)
    client_secret_encrypted: str = Field(max_length=512)
    redirect_uri: str = Field(max_length=512)
    scopes: str = Field(default="openid email profile")  # JSON string
    config_json: dict = Field(default={}, sa_type=JSON)  # Provider 特定配置
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider"),
    )
```

### 3.2 LDAP 配置表 (ldap_config)

```python
class LdapConfig(SQLModel, table=True):
    __tablename__ = "ldap_config"

    id: int = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, index=True)  # NULL = 全局
    enabled: bool = Field(default=False)
    server_url: str = Field(max_length=512)  # ldap:// 或 ldaps://
    base_dn: str = Field(max_length=256)
    bind_dn: str = Field(max_length=256)
    bind_password_encrypted: str = Field(max_length=512)
    user_filter: str = Field(max_length=512)  # 默认: (uid={username})
    use_ssl: bool = Field(default=True)
    timeout: int = Field(default=30)
    auto_register: bool = Field(default=True)
    sync_strategies: dict = Field(default={}, sa_type=JSON)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id"),
    )
```

### 3.3 用户同步配置表 (user_sync_config)

```python
class UserSyncConfig(SQLModel, table=True):
    __tablename__ = "user_sync_config"

    id: int = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    source: str = Field(max_length=32, index=True)  # ldap / google / ...
    auto_register: bool = Field(default=True)
    sync_email: SyncStrategy = Field(default=SyncStrategy.FIRST_ONLY)
    sync_phone: SyncStrategy = Field(default=SyncStrategy.FIRST_ONLY)
    sync_name: SyncStrategy = Field(default=SyncStrategy.NEVER)
    sync_department: bool = Field(default=False)
    logout_redirect_oauth: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source"),
    )
```

---

## 4. API 设计

### 4.1 LDAP 登录

**端点**: `POST /api/v1/user/ldap/login`

```python
@router.post("/user/ldap/login")
async def ldap_login(
    body: LdapLoginRequest,
    request: Request,
):
    """LDAP 用户登录"""
    # 1. 验证码校验
    await CaptchaService.verify(body.captcha_key, body.captcha)

    # 2. 获取 LDAP Provider
    provider = LdapProvider(tenant_id=body.tenant_id)

    # 3. 认证
    auth_result = await provider.authenticate(request)

    # 4. 同步用户
    user, token = await provider.sync_user(
        external_id=auth_result.external_id,
        user_attrs=auth_result.to_user_attrs(),
        options=await SyncOptions.from_config(provider.tenant_id, "ldap"),
    )

    # 5. 响应
    return LoginResponse(
        user_id=user.user_id,
        user_name=user.user_name,
        access_token=token,
        is_global_super=user.is_global_super,
        default_entry=user.default_entry,
    )
```

### 4.2 OAuth 授权

**端点**: `GET /api/v1/oauth/{provider}/authorize`

```python
@router.get("/oauth/{provider}/authorize")
async def get_authorization_url(
    provider: str,
    state: str,
    redirect_uri: str | None = None,
    tenant_id: int = Depends(get_tenant_id),
):
    """获取 OAuth 授权 URL"""
    oauth_provider = get_oauth_provider(provider, tenant_id)

    # 生成带 HMAC 签名的 state
    state = await OAuthStateService.create(
        provider=provider,
        redirect_uri=redirect_uri,
        tenant_id=tenant_id,
    )

    # 构建回调 URL
    callback_uri = f"/api/v1/oauth/{provider}/callback"
    if redirect_uri:
        callback_uri += f"?redirect_uri={quote(redirect_uri)}"

    auth_url = await oauth_provider.get_authorization_url(state, callback_uri)

    return {"authorization_url": auth_url}
```

### 4.3 OAuth 回调

**端点**: `GET /api/v1/oauth/{provider}/callback`

```python
@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
):
    """OAuth 回调"""
    # 1. 验证并消耗 state
    state_data = await OAuthStateService.verify_and_delete(state, provider)

    # 2. 获取 Provider 并认证
    oauth_provider = get_oauth_provider(provider, state_data.tenant_id)
    auth_result = await oauth_provider.authenticate_callback(code)

    # 3. 同步用户
    user, token = await oauth_provider.sync_user(
        external_id=auth_result.external_id,
        user_attrs=auth_result.to_user_attrs(),
        options=await SyncOptions.from_config(state_data.tenant_id, provider),
    )

    # 4. 重定向到前端
    frontend_redirect = state_data.redirect_uri or get_default_redirect(user)
    return RedirectResponse(url=f"{frontend_redirect}?token={token}")
```

### 4.4 OAuth Provider 列表

**端点**: `GET /api/v1/oauth/providers`

```python
@router.get("/oauth/providers")
async def list_providers(tenant_id: int = Depends(get_tenant_id)):
    """获取启用的 OAuth Provider 列表（前端动态渲染用）"""
    configs = OAuthProviderConfigDao.get_enabled_for_tenant(tenant_id)

    return {
        "providers": [
            {
                "id": config.provider,
                "name": get_provider_name(config.provider),
                "icon": f"{config.provider}.svg",
                "enabled": config.enabled,
            }
            for config in configs
        ]
    }
```

---

## 5. 前端集成

### 5.1 SocialLoginRender 改造

**目标**: 配置驱动，移除硬编码

**改动**:

```typescript
// src/frontend/client/src/components/Auth/SocialLoginRender.tsx

// Before: 硬编码
const SOCIAL_PROVIDERS = ['discord', 'facebook', 'github', 'google', 'apple', 'openid'];

// After: 从 API 获取
const { data: providersData } = useQuery({
  queryKey: ['oauth-providers'],
  queryFn: () => api.get('/api/v1/oauth/providers'),
});

const enabledProviders = providersData?.providers || [];
```

### 5.2 LDAP 登录改造

**目标**: 移除对 `pro.ts` 的依赖

**改动**:

```typescript
// src/frontend/platform/src/pages/LoginPage/login.tsx

// Before: pro.ts 中 ldapLoginApi()
import { ldapLoginApi } from '@/controllers/API/pro';

// After: 直接调用 user_sync API
import { ldapLogin } from '@/controllers/API/userSync';

const handleLdapLogin = async (username: string, password: string) => {
  const encryptedPassword = await encryptPassword(password);
  return ldapLogin({
    username,
    password: encryptedPassword,
    tenant_id: currentTenantId,
    captcha_key,
    captcha,
  });
};
```

---

## 6. 安全设计

### 6.1 OAuth State 管理

**策略**: Redis 存储 + HMAC 签名

```python
class OAuthStateService:
    STATE_TTL = 300  # 5 分钟

    @staticmethod
    async def create(provider: str, redirect_uri: str, tenant_id: int) -> str:
        state_data = {
            "provider": provider,
            "redirect_uri": redirect_uri,
            "tenant_id": tenant_id,
            "exp": time.time() + OAuthStateService.STATE_TTL,
        }
        # 签名防止篡改
        state_data["sig"] = compute_hmac_signature(state_data)

        state = base64url_encode(json.dumps(state_data))
        await redis.setex(
            f"oauth:state:{state}",
            OAuthStateService.STATE_TTL,
            json.dumps(state_data),
        )
        return state

    @staticmethod
    async def verify_and_delete(state: str, provider: str) -> StateData:
        # 1. 解析 state
        # 2. 验证 HMAC 签名
        # 3. 验证 provider 匹配
        # 4. 删除 state（防止重放）
        pass
```

### 6.2 LDAP 密码传输

**策略**: 前端 RSA 公钥加密

```typescript
// 前端
const publicKey = await fetchPublicKey();
const encryptedPassword = rsaEncrypt(password, publicKey);

// 后端
password = rsa_decrypt(encrypted_password)  # 使用私钥解密
```

---

## 7. 错误处理

### 7.1 错误码定义

```python
# src/backend/bisheng/common/errcode/user_sync.py

class LdapErrorCode(BaseErrorCode):
    LDAP_CONNECTION_FAILED = 19101, "LDAP 服务器连接失败"
    LDAP_AUTH_FAILED = 19102, "用户名或密码错误"
    LDAP_USER_NOT_FOUND = 19103, "用户不存在"
    LDAP_USER_DISABLED = 19104, "账号已禁用"
    LDAP_CONFIG_NOT_FOUND = 19105, "LDAP 未配置"


class OAuthErrorCode(BaseErrorCode):
    OAUTH_PROVIDER_DISABLED = 19201, "OAuth Provider 未启用"
    OAUTH_AUTH_FAILED = 19202, "授权失败"
    OAUTH_STATE_INVALID = 19203, "State 验证失败"
    OAUTH_TOKEN_EXCHANGE_FAILED = 19204, "Token 交换失败"
    OAUTH_USER_INFO_FAILED = 19205, "获取用户信息失败"
```

### 7.2 分级展示

| 用户看到 | 日志记录 |
|----------|----------|
| "登录失败，请联系管理员" | 详细错误原因 |
| "网络连接失败，请重试" | 完整堆栈 |
| "服务暂时不可用" | 配置问题详情 |

---

## 8. 配置管理

### 8.1 环境变量配置

```bash
# OAuth Provider 敏感信息（全局默认值）
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx

# LDAP 全局默认配置
LDAP_SERVER_URL=ldap://ldap.example.com:389
LDAP_BASE_DN=dc=example,dc=com
```

### 8.2 数据库配置优先级

```
请求 → 租户级配置 → 全局配置 → 环境变量默认值
```

---

## 9. 已知坑与风险

### 9.1 坑 1: sso_sync 紧耦合

**问题**: `LoginSyncService` 高度耦合，直接抽取困难

**解决**: 采用"提取公共逻辑到新 Service"而非"重构 sso_sync"，避免破坏现有功能

### 9.2 坑 2: LDAP 连接管理

**问题**: ldap3 连接池在线程/异步环境下可能有问题

**解决**: 使用 `ldap3.ServerPool` 的 `ROUND_ROBIN` 策略，每次请求创建新 Connection，用完关闭

### 9.3 风险: OAuth Token 安全

**风险**: Access Token 不存储可能影响后续 API 调用

**缓解**: 如需用户头像等，使用 ID Token 或仅在登录时获取一次

---

## 10. 测试策略

### 10.1 单元测试

- `test_ldap_provider.py`: Mock ldap3 Server/Connection
- `test_google_provider.py`: Mock httpx 响应
- `test_user_upsert_service.py`: Mock DAO 层

### 10.2 集成测试

- `test_ldap_api.py`: TestClient + 模拟 LDAP Server
- `test_oauth_api.py`: Mock OAuth Provider 端点

### 10.3 E2E 测试

- 手动验证 LDAP 登录流程
- 手动验证 Google OAuth 登录流程

---

## 11. 里程碑

| Phase | 内容 | 验收条件 |
|-------|------|----------|
| Phase 1.1 | LDAP Provider + 登录 | 能用 AD/LDAP 账号登录 |
| Phase 1.2 | Google OAuth Provider | 能用 Google 账号登录 |
| Phase 1.3 | 前端动态渲染 | 登录页根据配置显示 Provider |
| Phase 2 | GitHub/微信/支付宝 | 扩展更多 Provider |
