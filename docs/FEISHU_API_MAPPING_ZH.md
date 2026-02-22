# 飞书 API 接口映射（当前实现）

本文档用于说明 `localFile_cloudSync_Server` 当前实际调用的飞书 OpenAPI 接口，便于排障、权限申请和后续扩展。

## 1. 实现范围说明

- 当前已实现：**Drive 文件型同步**（文件/文件夹元数据、上传下载、移动重命名、删除）。
- 当前鉴权主链路：**用户身份 user_access_token**（OAuth 授权码模式）。
- 当前未实现：飞书云文档内容级接口（Docx/Sheet/Bitable/Wiki 内容读写）。

## 2. 鉴权接口（OAuth / Token）

| 用途 | 方法 | 飞书接口 |
| --- | --- | --- |
| 生成授权链接 | 浏览器跳转 | `https://open.feishu.cn/open-apis/authen/v1/index` |
| code 换 user_access_token | `POST` | `/open-apis/authen/v1/access_token` |
| refresh_token 刷新 user_access_token | `POST` | `/open-apis/authen/v1/refresh_access_token` |
| 备用：tenant_access_token（当前非主链路） | `POST` | `/open-apis/auth/v3/tenant_access_token/internal` |

代码位置：`app/app/providers/feishu_legacy/feishu_client.py`

## 3. Drive 文件型接口

| 用途 | 方法 | 飞书接口 |
| --- | --- | --- |
| 获取根目录 token | `GET` | `/open-apis/drive/explorer/v2/root_folder/meta` |
| 列出目录文件 | `GET` | `/open-apis/drive/v1/files` |
| 创建文件夹 | `POST` | `/open-apis/drive/v1/files/create_folder` |
| 上传文件 | `POST` | `/open-apis/drive/v1/files/upload_all` |
| 下载文件 | `GET` | `/open-apis/drive/v1/files/{file_token}/download` |
| 重命名文件/文件夹 | `PATCH` | `/open-apis/drive/v1/files/{file_token}` |
| 移动文件/文件夹 | `POST` | `/open-apis/drive/v1/files/{file_token}/move` |
| 删除文件/文件夹 | `DELETE` | `/open-apis/drive/v1/files/{file_token}?type={file_type}` |
| 读取元数据 | `GET` | `/open-apis/drive/v1/metas/{file_token}` |

代码位置：`app/app/providers/feishu_legacy/feishu_client.py`

## 4. 项目内接口到飞书接口的对应

### 4.1 CLI

- `python -m localfilesync.cli.main auth-url` -> 飞书 OAuth 授权入口
- `python -m localfilesync.cli.main auth-exchange --code ...` -> `authen/v1/access_token`
- `python -m localfilesync.cli.main auth-refresh --force` -> `authen/v1/refresh_access_token`
- `python -m localfilesync.cli.main run-once` -> 触发 Drive 同步流程（可能调用列表/上传/下载/重命名/移动/删除）

### 4.2 Web API

- `POST /api/auth/url` -> 生成 OAuth 授权链接
- `POST /api/auth/exchange` -> code 换 token
- `POST /api/auth/refresh` -> 刷新 token
- `GET /api/status/feishu` -> 连通性探测（含根目录 token 探测）
- `POST /api/actions/run-once` -> 执行一次 Drive 同步
- `GET /api/drive/tree` -> 获取 Drive 目录树（基于 `drive/v1/files`）

## 5. 未实现能力（当前明确）

以下能力当前**未接入**，因此本版本不提供对应同步：

- 文档内容 API（Docx 正文结构化读写）
- 表格内容 API（Sheet/Bitable 单元格级操作）
- 知识库页面内容 API（Wiki 页面结构化修改）
- 图片内容级处理 API（除文件上传下载外）

说明：当前版本定位为“Drive 文件型同步器”，后续如扩展内容级同步，建议单独增加 provider 层并保持与现有文件型能力解耦。

## 6. 官方文档入口（建议）

- API 调用流程总览：<https://open.feishu.cn/document/server-docs/api-call-guide/calling-process/overview>
- 获取 access token：<https://open.feishu.cn/document/server-docs/api-call-guide/calling-process/get-access-token>
- 服务端 API 列表：<https://open.feishu.cn/document/server-docs/api-call-guide/server-api-list>
- 云文档总览：<https://open.feishu.cn/document/server-docs/docs/docs-overview>
- 云文档 FAQ：<https://open.feishu.cn/document/server-docs/docs/faq>
- Drive 接口总览：<https://open.feishu.cn/document/server-docs/docs/drive-v1/introduction>
- Drive FAQ：<https://open.feishu.cn/document/server-docs/docs/drive-v1/faq>
- Wiki 总览：<https://open.feishu.cn/document/server-docs/docs/wiki-v2/wiki-overview>
- Docx 总览：<https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/docx-overview>
