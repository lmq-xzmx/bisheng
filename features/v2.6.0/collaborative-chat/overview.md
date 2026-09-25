# 协同聊天功能设计方案

## 一、需求概述

**场景**：用户选中文件中的文本片段作为聊天焦点，多方围绕该焦点进行协同讨论。

**核心特点**：
- 以文件文本为焦点的协同讨论
- 选中文本 → 发起讨论 → 多方协同
- 实时消息同步

---

## 二、入口设计

### 入口 1：文件预览页协作（主要入口）

**路由**：`/workspace/knowledge/file/:fileId`

**交互流程**：
```
文件预览页 → 选中文本 → 浮动工具栏出现"💬 发起讨论" → 点击 → 右侧协同面板展开
```

### 入口 2：独立协同会话链接（分享用）

**路由**：`/workspace/collab/s/:sessionId`

用户通过分享链接加入协同会话时，直接进入专门的协同视图。

### 入口 3：工作台快捷入口

**路由**：`/build/client`（Platform 工作台页面）

在首页 Tab 添加"协同聊天"入口按钮，点击跳转 Client 的协同会话列表或创建页。

---

## 三、数据模型

### 新增表

#### 1. collaborative_session（协同会话）

```sql
CREATE TABLE collaborative_session (
    id VARCHAR(36) PRIMARY KEY,
    file_id VARCHAR(36) NOT NULL COMMENT '关联文件ID',
    file_version VARCHAR(36) COMMENT '文件版本',
    file_name VARCHAR(500) COMMENT '文件名（冗余存储）',
    title VARCHAR(255) NOT NULL COMMENT '会话标题',
    owner_id INT NOT NULL COMMENT '创建者用户ID',
    status TINYINT DEFAULT 1 COMMENT '状态：1-活跃 2-归档',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_file_id (file_id),
    INDEX idx_owner_id (owner_id),
    INDEX idx_status (status)
) COMMENT='协同会话';
```

#### 2. text_focus（文本焦点）

```sql
CREATE TABLE text_focus (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL COMMENT '所属协同会话ID',
    file_id VARCHAR(36) NOT NULL COMMENT '关联文件ID',
    text_content TEXT NOT NULL COMMENT '选中的原文',
    start_offset INT NOT NULL COMMENT '在文件中的起始位置',
    end_offset INT NOT NULL COMMENT '结束位置',
    highlight_order INT DEFAULT 0 COMMENT '选中顺序',
    created_by INT NOT NULL COMMENT '创建者',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_file_id (file_id),
    FOREIGN KEY (session_id) REFERENCES collaborative_session(id) ON DELETE CASCADE
) COMMENT='文本焦点';
```

#### 3. collaborative_member（会话成员）

```sql
CREATE TABLE collaborative_member (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL COMMENT '协同会话ID',
    user_id INT NOT NULL COMMENT '用户ID',
    role TINYINT DEFAULT 1 COMMENT '角色：1-参与者 2-观察者',
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_read_at DATETIME COMMENT '最后阅读时间',
    UNIQUE KEY uk_session_user (session_id, user_id),
    INDEX idx_user_id (user_id),
    FOREIGN KEY (session_id) REFERENCES collaborative_session(id) ON DELETE CASCADE
) COMMENT='协同会话成员';
```

#### 4. focus_message（焦点消息）

```sql
CREATE TABLE focus_message (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL COMMENT '协同会话ID',
    focus_id VARCHAR(36) COMMENT '关联的文本焦点ID，可空',
    user_id INT NOT NULL COMMENT '发送者用户ID',
    message TEXT NOT NULL COMMENT '消息内容',
    type TINYINT DEFAULT 1 COMMENT '类型：1-文本 2-引用 3-图片',
    parent_id VARCHAR(36) COMMENT '父消息ID（回复关系）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_focus_id (focus_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (session_id) REFERENCES collaborative_session(id) ON DELETE CASCADE,
    FOREIGN KEY (focus_id) REFERENCES text_focus(id) ON DELETE SET NULL
) COMMENT='焦点消息';
```

#### 5. message_reaction（消息反应）

```sql
CREATE TABLE message_reaction (
    id VARCHAR(36) PRIMARY KEY,
    message_id VARCHAR(36) NOT NULL COMMENT '消息ID',
    user_id INT NOT NULL COMMENT '用户ID',
    reaction_type VARCHAR(10) NOT NULL COMMENT '反应类型：thumbs_up/thumbs_down/question',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_message_user_reaction (message_id, user_id, reaction_type),
    FOREIGN KEY (message_id) REFERENCES focus_message(id) ON DELETE CASCADE
) COMMENT='消息反应';
```

### 改造现有表

#### message_session 新增字段

```sql
ALTER TABLE message_session ADD COLUMN collaborative_session_id VARCHAR(36);
ALTER TABLE message_session ADD COLUMN is_collaborative BOOLEAN DEFAULT FALSE;
```

---

## 四、后端 API 设计

### 新增路由：`/api/v1/collaborative/`

#### 会话管理

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/sessions` | 创建协同会话 | `{fileId, fileName, title, textContent?, startOffset?, endOffset?}` | `CollaborativeSession` |
| GET | `/sessions` | 获取会话列表 | Query: `status`, `fileId`, `page`, `pageSize` | `{list: [], total}` |
| GET | `/sessions/:id` | 获取会话详情 | - | `SessionDetail`（含成员、焦点） |
| PATCH | `/sessions/:id` | 更新会话 | `{title?, status?}` | `CollaborativeSession` |
| DELETE | `/sessions/:id` | 删除会话 | - | `{success: true}` |
| POST | `/sessions/:id/join` | 加入会话 | - | `CollaborativeMember` |
| POST | `/sessions/:id/leave` | 离开会话 | - | `{success: true}` |
| GET | `/sessions/:id/members` | 获取成员列表 | - | `User[]` |

#### 焦点管理

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/focuses` | 创建文本焦点 | `{sessionId, fileId, textContent, startOffset, endOffset}` | `TextFocus` |
| GET | `/focuses` | 获取会话的所有焦点 | Query: `sessionId` | `TextFocus[]` |
| DELETE | `/focuses/:id` | 删除焦点 | - | `{success: true}` |

#### 消息管理

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/messages` | 获取消息列表 | Query: `sessionId`, `focusId`, `page`, `pageSize` | `{list: [], total}` |
| POST | `/messages` | 发送消息 | `{sessionId, focusId?, message, type?, parentId?}` | `FocusMessage` |
| DELETE | `/messages/:id` | 删除消息 | - | `{success: true}` |
| POST | `/messages/:id/reactions` | 添加反应 | `{reactionType}` | `MessageReaction` |
| DELETE | `/messages/:id/reactions/:type` | 移除反应 | - | `{success: true}` |

#### WebSocket

| 路径 | 说明 |
|------|------|
| WS `/ws/collab/:sessionId` | 协同会话实时通信 |

---

## 五、WebSocket 实时通信协议

### 连接建立

```javascript
// 客户端连接
ws://host/ws/collab/{sessionId}?token={jwt_token}

// 连接成功后的认证消息
{ "type": "auth", "userId": 123 }
```

### 客户端 → 服务端消息

```typescript
// 1. 加入会话
{ "type": "join", "sessionId": "xxx" }

// 2. 发送消息
{ "type": "message", "focusId": "xxx", "content": "讨论内容", "parentId?": "yyy" }

// 3. 正在输入
{ "type": "typing", "focusId": "xxx" }

// 4. 光标位置（用于高亮同步）
{ "type": "cursor", "focusId": "xxx", "start": 100, "end": 150 }

// 5. 离开会话
{ "type": "leave" }
```

### 服务端 → 客户端消息

```typescript
// 1. 用户加入通知
{ "type": "user_joined", "user": { "id": 123, "name": "张三", "avatar": "xxx" } }

// 2. 用户离开通知
{ "type": "user_left", "userId": 123 }

// 3. 新消息（广播给所有成员）
{ "type": "new_message", "message": { "id": "m1", "focusId": "f1", "userId": 123, ... }, "sessionId": "s1" }

// 4. 消息删除通知
{ "type": "message_deleted", "messageId": "m1", "sessionId": "s1" }

// 5. 焦点创建通知
{ "type": "focus_created", "focus": { "id": "f1", "textContent": "产品定义", ... } }

// 6. 焦点删除通知
{ "type": "focus_deleted", "focusId": "f1" }

// 7. 正在输入通知
{ "type": "user_typing", "userId": 123, "focusId": "f1" }

// 8. 光标位置同步
{ "type": "cursor_update", "userId": 123, "focusId": "f1", "start": 100, "end": 150 }

// 9. 成员列表更新
{ "type": "members_updated", "members": [{ "id": 123, "name": "张三", "online": true }, ...] }

// 10. 错误消息
{ "type": "error", "code": "UNAUTHORIZED", "message": "无权访问该会话" }
```

### 心跳机制

```typescript
// 客户端每 30 秒发送一次 ping
{ "type": "ping" }

// 服务端响应
{ "type": "pong" }
```

---

## 六、前端改造

### Client 端（/workspace）

#### 新增页面

| 路由 | 组件 | 说明 |
|------|------|------|
| `/workspace/collab/s/:sessionId` | `CollaborativeSessionPage` | 独立协同会话页（分享链接入口） |

#### 改造页面

| 页面 | 改动 |
|------|------|
| `/workspace/knowledge/file/:fileId` | 添加协同面板组件 |

#### 核心组件

```
src/components/Collaborative/
├── CollaborativePanel.tsx       # 协同讨论主面板
├── FocusList.tsx                # 焦点列表
├── FocusThread.tsx              # 单个焦点的讨论线程
├── MessageBubble.tsx            # 消息气泡
├── MemberAvatars.tsx            # 在线成员头像
├── SelectionToolbar.tsx         # 选中文本浮动工具栏
├── TextHighlighter.tsx          # 文档文本高亮
└── TypingIndicator.tsx          # 正在输入提示
```

#### Recoil Store

```typescript
// store/slices/collaborative.ts
export const collaborativeState = atom({
  key: 'collaborative',
  default: {
    activeSession: null as CollaborativeSession | null,
    focuses: {} as Record<string, TextFocus[]>,
    messages: {} as Record<string, FocusMessage[]>,
    onlineMembers: {} as Record<string, User[]>,
    selectedText: null as { text: string; start: number; end: number } | null,
    activeFocusId: null as string | null,
    panelOpen: false,
  }
});
```

### Platform 端（/admin）

#### 工作台入口

在 `/build/client` 的首页 Tab（`Index` 组件）添加"协同聊天"入口按钮：

```
┌─────────────────────────────────────────────────────────────┐
│  首页    知识空间    订阅    应用中心                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [🤖 AI 对话]              [💬 协同聊天]  ← 新增              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

点击"协同聊天"按钮，跳转到 `/workspace/collab/sessions` 或创建新会话。

---

## 七、分屏布局设计

### 默认布局（适合长文档）

```
┌─────────────────────────────┬──────────────────────────────┐
│       文件预览区              │        协同讨论面板            │
│                              │  [👤👤👤 3人在线] [📤 邀请]   │
│  第1段███████████████        │  ─────────────────────────   │
│        ↑ 黄色高亮(焦点1)      │  📌 焦点1 — "产品定义"       │
│                              │    ├ 张三：这里的"产品"指什么？ │
│  第2段████████ 绿色(焦点2) ██│    ├ 李四：应该是指广义产品     │
│                              │    └ 王五：同意楼上观点        │
│  第3段███████████████        │  ─────────────────────────   │
│                              │  📌 焦点2 — "硬件设备定义"    │
│                              │    ├ 张三：这块需要明确范围     │
│                              │  ─────────────────────────   │
│                              │  [输入框...] [发送]          │
└─────────────────────────────┴──────────────────────────────┘
```

### 交互说明

1. **选中文本** → 浮动工具栏出现"💬 发起讨论"
2. **点击"发起讨论"** → 右侧面板自动展开，定位到新焦点
3. **点击右侧焦点** → 左侧自动滚动到对应位置
4. **消息按 focusId 分组** → 每个焦点一个讨论线程
5. **回复消息** → 嵌套显示，形成对话树

---

## 八、技术实现要点

### 1. 文本位置映射

- 使用 `startOffset` 和 `endOffset`（字符级偏移）标记焦点位置
- 文件预览时，将偏移转换为行号进行渲染
- 支持增量更新：文件修改后只影响偏移量变化的焦点

### 2. 高并发写处理

- 消息优先写入 MySQL（持久化）
- Redis 缓存最新 N 条消息（加速读取）
- WebSocket 广播使用 Redis Pub/Sub 跨实例同步

### 3. 权限控制

- 协同会话权限继承自文件的读写权限
- 参与者可发言，观察者只能看
- 通过现有的 RBAC + OpenFGA 体系控制

### 4. 离线消息

- 入会时从 MySQL 拉取历史消息
- Redis 存储未读计数
- WebSocket 重连后自动同步离线消息

---

## 九、改造工作量估算

| 模块 | 改动量 | 备注 |
|------|--------|------|
| 数据模型 | 新增 5 张表 | 改动较小 |
| 后端 API | 新增 15+ 接口 | 参照现有 chat_router |
| WebSocket | 新增协作频道 | 复用 ChatManager |
| Client 页面 | 新建 5-8 组件 | 需熟悉 Client 架构 |
| Client 状态 | 新增 1 Recoil slice | |
| Platform 工作台 | 新增 1 入口按钮 | 改动最小 |

---

## 十、扩展方向（后续）

1. **AI 辅助**：LLM 总结讨论要点、自动生成结论
2. **版本对比**：同一文件不同版本间的协同历史
3. **@提及**：消息中 @用户，自动通知
4. **表情反应**：针对消息/焦点表态 👍👎❓
5. **协作光标**：显示其他用户当前选中的文本
