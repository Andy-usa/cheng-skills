# Python ↔ 会话存档 C SDK 集成方案对比

企业微信会话存档**官方只发 C/C++ SDK**（Linux x86/ARM + Windows）。Python 调用有三条路：

## 方案 A：自行 ctypes 包 C SDK ⭐ 最可控

**步骤**：
1. 从企业微信文档下载 `WeWorkFinanceSdk_C` 对应平台的 `.so` / `.dll`
2. 用 `ctypes` 在 Python 里 `CDLL` 加载
3. 按 SDK 头文件 `WeWorkFinanceSdk_C.h` 在 Python 里复刻函数签名
4. 处理字符串编码（C 的 char* ↔ Python str）、内存释放

**优点**：完全可控、零第三方依赖、ABI 升级时直接换 .so 即可。
**缺点**：要自己写 ~200 行 boilerplate，C 内存管理小心翼翼，崩溃了 Python 不报错只 segfault。

**参考实现**：把 `MsgAuditClient.__init__` / `get_chat_data` / `decrypt` 三个方法用 ctypes 封一遍。

---

## 方案 B：用第三方 PyPI 包

GitHub 搜 `wxwork-finance-sdk` 有几个候选，质量参差。**本地接手时先核实**：
- 仓库最近有维护吗（>= 2024 还在更新）
- 用的是哪一版 C SDK（`v3` 是当前主流）
- ABI 是否匹配你机器（`manylinux2014` vs `musllinux`）
- 有没有 type hints / 测试

**优点**：装上即用，不用写 ctypes。
**缺点**：依赖第三方维护质量，封装可能不全（比如不支持新版 SDK 的某些 API）。

**当前推荐做法**：搜到一个看着靠谱的包后，**只用它 wrap 我们已经定义好的 `MsgAuditClient` 接口**，业务代码不直接依赖第三方包。这样未来换包成本最小。

---

## 方案 C：独立 Go / Java 服务 + HTTP

写一个独立的 sidecar 服务，用官方 Go/Java SDK，暴露 `/get_chat_data` + `/decrypt` HTTP 端点；Python 这边纯 HTTP 调。

**优点**：彻底隔离 ABI 问题；Go / Java SDK 也是官方支持，更稳。
**缺点**：多一个进程要部署 + 运维；HTTP 序列化开销（密文体可能很大）。

**适用场景**：你这台机器上 Python 已经依赖一堆 native 扩展（比如 numpy/torch），不想再引入潜在的 ABI 冲突。

---

## 决策建议

| 情况 | 选哪个 |
|---|---|
| 个人 / 小团队、想快速跑通 | **B**（找一个靠谱第三方包试试，不行再退到 A）|
| 生产环境、规模化、稳定性优先 | **A**（ctypes 自己写）|
| 多语言混部、已有 Go/Java 服务运维 | **C** |

**本项目当前架构（`app/msgaudit/client.py`）**：定义了 `MsgAuditClient` 抽象接口，不绑定任何具体 SDK。本地接手时挑一个方案实现这三个方法即可，业务层（`worker.py` / `pipelines/sphfeed_to_lark.py`）不需要动。

## 立即可做的事

1. `pip search` 类似 `wxwork-finance-sdk-python` 看 PyPI 有没有现成包
2. 在 `app/msgaudit/client.py` 把 `get_chat_data` / `decrypt` 三个方法填上
3. 写一个 `tests/test_msgaudit_client.py`，**用 SDK 自带的 demo 数据做测试**（C SDK 包里通常带了 `test_data.txt` 的密文样本）
