# WatchSieve

## 本机 Docker 部署（默认）

Web 与 SnailJob 执行器由本仓库 `docker-compose.yml` 分别管理，共用镜像和原有 `data/`。
统一入口 `/Users/conchi/docker-compose/watch-sieve/docker-compose.yml` 引用本仓库配置。

```bash
./scripts/start.sh build   # 首次部署或代码更新后构建（包含前端和 Linux Chromium）
./scripts/start.sh start
./scripts/start.sh status
./scripts/start.sh logs
./scripts/start.sh stop
```

页面：http://127.0.0.1:47863 。本机与 Mac mini 使用相同的宿主机端口 47863；容器内部仍监听 8000，宿主机仅开放回环端口。
两个容器使用 `restart: unless-stopped`，Docker Desktop 启动后恢复；主动 stop 后保持停止，需执行 start 恢复。
不会在每次登录时构建镜像，也不依赖 Context Router 运行。Docker Desktop 仍须由 macOS 登录项启动。

依赖既有的 `vibedeploy-shared` 网络及其中的 `postgres16:5432`、`snail-job-server:17888`、
`local-config-center:18527`。不创建或迁移这些依赖，也不修改 SnailJob 的任务计划。
`.env` 提供现有账号和 Token，不打入镜像；Compose 覆盖容器中的连接地址。
数据库 URL 只替换主机，保留原用户、密码、库名和查询参数。
执行器注册地址为 `watch-sieve-worker:17889`，服务端通过共享网络回调，无需发布此端口到宿主机。

Web/worker 启动时等待 PostgreSQL，worker 还等待 SnailJob TCP 端口；120 秒超时后退出，由重启策略重试。
模型网关暂时不可用不阻止 Web 启动，调用模型时按现有逻辑报错。
Web `/api/health` 检查数据库查询；worker 容器健康检查只代表回调端口存活，
完整验收还需确认 SnailJob 服务端登记节点、心跳和任务结果。

现有 `data/` 原地绑定到两个容器，保留缓存和跨进程锁；`configs/` 只读挂载。
日志由 Docker 管理（每服务最多 3 × 10 MB）；旧 `log/` 保留作历史记录。
不要同时运行下面的宿主机 Web/执行器命令，以免重复注册或争用端口。


监控指定网站并稳定抓取正文。当前 MVP 只做一件事：把页面内容拿到手。

抓取路径参考了 Crawl4AI、DrissionPage、Firecrawl：

1. HTTP 先抓（浏览器请求头、编码探测、失败重试）
2. 质量门判断空页、验证码页、JS 空壳
3. 不过关再走 Playwright（`domcontentloaded` + 可选 CSS 等待）
4. 清掉脚本/导航后转成 Markdown

动态填站点和大模型筛选还没做；定时抓取可通过 SnailJob 执行器接入。

## 起步

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

复制 `.env.example` 为 `.env`，填入 `WATCH_SIEVE_DATABASE_URL`。标题存在本机 `postgres16` 容器的独立库 `watch_sieve` 中，不要写进 `snail_job`。

大模型、生图、TTS、听写一律走本机网关 `local_config_center`（需本机 `make run`），不要在本仓库写厂商 API Key 或厂商 Base URL。

```bash
docker exec postgres16 psql -U conchi -d postgres -c "CREATE DATABASE watch_sieve OWNER conchi;"
watch-sieve --config configs/sites.example.yaml
watch-sieve --url https://example.com
```

`quotes.toscrape.com/js/` 用来验证 HTTP 拿不到正文时会自动切到浏览器。

## 标题墙

```bash
cd web && npm install && npm run build && cd ..
pip install -e ".[dev]"
watch-sieve-web
```

打开后是带筛选和分页的标题列表：关键词、来源、类型、日期。点「查询」过滤，点「刷新」重新抓取。顶部菜单是「标题」「分类」「关注」。分类页在有入库结果时用模型分类，未判定的标题先走关键词。关注页用本机网关 chat 模型筛选兴趣标题：`POST /api/watches/run`。定时分类和关注走独立执行器 `watchSieveJudge`，不进抓取锁。

在 `.env` 中增加本机网关地址和密钥（密钥以配置中心页面右上角为准，未改时是 `local-gateway`）：

```dotenv
WATCH_SIEVE_GATEWAY_BASE_URL=http://127.0.0.1:18527
WATCH_SIEVE_GATEWAY_AUTH=local-gateway
```

`WATCH_SIEVE_CHAT_MODEL` 指定分类和关注用的 chat slug，必须带前缀。当前默认是 `aurora/gpt-5-6-mini`。不填则用 `GET /v1/models` 里第一个 `kind=chat` 的模型。合同见 `local_config_center` 的 `docs/ACCESS.md`。

## 接入 SnailJob

项目使用独立的 Python 执行器连接 SnailJob，避免 Web 服务启用多个 worker 时重复注册任务。

```bash
pip install -e ".[dev,snailjob]"
cp .env.example .env
```

在 SnailJob 控制台创建命名空间和执行器组，然后把命名空间 ID、组名和组 Token 填入 `.env`：

```dotenv
SNAIL_SERVER_HOST=127.0.0.1
SNAIL_SERVER_PORT=17888
SNAIL_HOST_IP=host.docker.internal
SNAIL_HOST_PORT=17889
SNAIL_NAMESPACE=控制台中的命名空间ID
SNAIL_GROUP_NAME=watch_sieve
SNAIL_TOKEN=控制台中的组Token
```

上面的地址示例适用于 SnailJob 在 Docker Desktop 中运行、Python 执行器在宿主机运行。`SNAIL_SERVER_HOST` 是 Python 访问服务端的地址；`SNAIL_HOST_IP` 是服务端回调 Python 执行器时使用的地址，必须从 SnailJob 容器中可解析且端口可达。

- Docker Desktop 通常可用 `host.docker.internal`；当前 Colima 默认也有对应映射，实际取决于版本与 DNS 配置。
- Linux Docker 可在 **SnailJob 服务端容器**增加 `extra_hosts: ["host.docker.internal:host-gateway"]`，或填写容器可达的宿主机 IP。虚拟机环境需确认网关指向的是哪一层宿主机，不能直接套用。
- 客户端可注册并不代表回调可用：在控制台核对节点地址，并从服务端容器检查该地址的 `17889` 端口。仅能解析域名还不够。

程序显式读取源码仓库根目录的 `.env`，无需从根目录启动；已设置的环境变量优先于文件。`.env` 不提交到 Git，也可以完全使用环境变量。命名空间填 ID，Token 填组 Token，组名必须与控制台完全一致。

启动执行器：

```bash
watch-sieve-snailjob
```

本地“成功注册执行器”日志只表示登记了函数；确认控制台出现在线 Python 客户端后，在 SnailJob 控制台新建定时任务：

- 执行器类型：`Python`
- 执行器名称：`watchSieveRefresh`
- 任务类型：`集群`
- 路由策略：任选一台健康实例
- 阻塞策略：丢弃后续调度
- 超时时间：联调可先用 `600` 秒，再按实测调整；这不是硬性耗时保证。HTTP 最多尝试 3 次，每站浏览器最多尝试 2 次，`180` 秒可能不足
- 触发间隔：联调先手动执行；定时启用后按实际耗时设置
- 失败重试：联调先关闭；启用后会按服务端策略重新抓取全部站点

任务参数可以留空，默认读取 `configs/sites.yaml`。也可以传 JSON 指定其他配置：

```json
{"config":"configs/sites.example.yaml"}
```

分类和关注用同一进程上的第二个执行器，不要写进 `watchSieveRefresh`。再新建一条定时任务：

- 执行器类型：`Python`
- 执行器名称：`watchSieveJudge`
- 任务类型：`集群`
- 阻塞策略：丢弃后续调度
- 超时时间：`600` 秒
- 触发间隔：分钟 `5、20、35、50`（避开 V2EX 的 8 和 38）
- 任务参数：留空；每轮先给未分类标题打标签（最多 45 条），再筛关注（最多 30 条）
- 失败重试：联调先关闭

执行器会把摘要和错误写入 SnailJob 实时日志。当前语义：

- 任一站点失败，任务仍上报失败。成功站点更新缓存；失败站点保留同一来源 URL 的历史标题和原抓取时间，并在页面提示失败。首次失败没有历史标题时显示为空。
- Web 与执行器通过同一个文件锁判断抓取状态，需要共享同一 `data` 目录。遇到已有抓取时立即返回缓存，`refreshing=true`，不会排队再抓一遍；SnailJob 将这次调度记为成功跳过。持锁进程退出后操作系统自动释放锁。
- 页面每 2 秒查询缓存；轮询不触发抓取，不替换筛选表单或打断中文输入。抓取在后台进行，页面不显示抓取中，也不改当前表格。
- 执行器检查 `ThreadPoolCache.event_is_set`，在站点、HTTP 重试和浏览器阶段之间响应停止。检测到停止后不启动后续阶段、不写入本轮缓存，返回失败。正在阻塞的网络或 Playwright 调用仍需返回或达到自身超时；服务端超时也需停止信号实际送达，不是强制杀进程。缓存提交前最后一次检查之后到原子替换之间仍有极短竞态。

### 联调验收

1. 创建命名空间与组，填写配置，启动执行器，确认控制台在线节点及回调地址。
2. 手动执行 `watchSieveRefresh`，核对实时日志、任务结果和 `data/latest.json` 的更新。
3. 创建并手动执行 `watchSieveJudge`，核对分类入库和关注筛选日志；打开分类/关注页不应自动调模型。
4. 抓取期间打开页面，表格仍是上次结果，按钮保持「刷新」；重复刷新不应触发第二轮抓取。
5. 验证部分站点失败时任务标红、成功站点更新、失败站点旧标题及时间保留。
6. 执行期间停止任务，待当前阻塞调用返回，确认不抓后续站点且本轮缓存没有提交。

`pytest` 覆盖本地结果映射、启动调用顺序、跨进程锁、缓存与协作式停止。SDK 的真实注册、心跳、回调和服务端超时仍须上述联调验证；单元测试通过不代表已经接通。

页面刷新回归检查（使用模拟 API，不连接真实站点）：

```bash
npm --prefix web run typecheck
npm --prefix web run build
.venv/bin/python scripts/check_refresh_ui.py
```
