# WatchSieve

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

打开后是带筛选和分页的标题列表：关键词、来源、类型、日期。点「查询」过滤，点「刷新」重新抓取。

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

这里假设 SnailJob 在 macOS Docker Desktop 中运行、Python 执行器在宿主机运行。`SNAIL_SERVER_HOST` 是 Python 访问 Docker 映射端口的地址；`SNAIL_HOST_IP` 是 SnailJob 容器回调 Python 执行器时使用的地址。

启动执行器：

```bash
watch-sieve-snailjob
```

看到 `watchSieveRefresh` 注册成功后，在 SnailJob 控制台新建定时任务：

- 执行器类型：`Python`
- 执行器名称：`watchSieveRefresh`
- 任务类型：`集群`
- 路由策略：任选一台健康实例
- 阻塞策略：丢弃后续调度
- 超时时间：应大于所有站点最坏抓取时间之和，当前建议 `180` 秒
- 触发间隔：例如固定间隔 `300` 秒

任务参数可以留空，默认读取 `configs/sites.yaml`。也可以传 JSON 指定其他配置：

```json
{"config":"configs/sites.example.yaml"}
```

执行器会把摘要和错误写入 SnailJob 实时日志。只要有一个站点失败，本次任务就会上报失败；Web 手动刷新与 SnailJob 抓取使用跨进程锁，不会同时覆盖缓存。
