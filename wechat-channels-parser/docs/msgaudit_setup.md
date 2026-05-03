# 会话内容存档（msgaudit）开通指南

## 前置条件

| 项 | 要求 |
|---|---|
| 企业认证 | **必须企业认证**（个人/无认证企业开不了） |
| 付费 | 「会话内容存档」是付费功能，按"被存档员工人数 × 年"计费 |
| 员工授权 | 每个被存档的员工，要在自己的企业微信 App 内**手动确认**「同意被存档」 |

## 开通步骤

### 1. 企业微信后台 → 启用「聊天内容存档」

1. 登录 https://work.weixin.qq.com/
2. 「**管理工具**」→「**聊天内容存档**」→ 点开通 / 购买
3. 配置「**存档范围**」：选择哪些员工被存档（至少要包含**接收客户视频号转发的那个员工**）
4. 进入存档应用页面 → 拿到 **Secret**（写到 `.env` 的 `WECHAT_MSGAUDIT_SECRET`）

### 2. 生成 RSA 密钥对

本地生成（任何 OpenSSL 都行）：

```bash
# 生成 2048-bit 私钥（PKCS1 格式）
openssl genrsa -out rsa_private_key.pem 2048

# 导出公钥
openssl rsa -in rsa_private_key.pem -pubout -out rsa_public_key.pem
```

### 3. 上传公钥 → 拿 publickey_ver

1. 后台「聊天内容存档」页面 → 「**消息加密公钥**」→ 上传 `rsa_public_key.pem`
2. 拿到「**公钥版本号**」（`publickey_ver`）
3. **私钥 `rsa_private_key.pem` 妥善保管，绝对不要入 git 仓库**
4. 把绝对路径写进 `.env` 的 `RSA_PRIVATE_KEY_PATH`

### 4. 员工授权（被存档员工本人操作）

1. 员工打开企业微信 App → 收到一条「您所在企业开启了会话存档」的系统通知
2. 点「同意」→ 该员工的所有会话从此被记录
3. 如果是被新加入存档范围的员工，App 内会重新弹通知

⚠️ **重要**：员工不点同意，存档不生效。这是企业微信的隐私保护设计，绕不过去。

## 验证开通

用 SDK 调一次 `GetChatData(seq=0, limit=10)`：
- 如果返回非空 → 开通成功
- 如果返回空但无错误 → 还没有任何被存档的员工有过聊天记录（让员工随便发条消息测试）
- 如果报权限错 → 检查 Secret + 私钥版本

## 常见坑

1. **Secret 重置后旧值失效** — 重置 Secret 后必须改 `.env` 重启 worker
2. **公钥版本不匹配** — 解密时报版本错，说明这条消息用的是旧版本公钥加密的，需要保留旧私钥（多版本管理）
3. **存档延迟** — 客户发消息 → SDK 拉到 ~10 秒到几十秒，**不是实时**
4. **跨语言 SDK** — 官方只有 C/C++，Python 必须用 ctypes 或第三方包，详见 `python_sdk_options.md`

## 官方文档锚点

- 总览：https://developer.work.weixin.qq.com/document/path/91774
- 使用前帮助：https://developer.work.weixin.qq.com/document/path/91361
- 常见问题：https://developer.work.weixin.qq.com/document/path/91552
- 案例演示：https://developer.work.weixin.qq.com/document/path/91551
