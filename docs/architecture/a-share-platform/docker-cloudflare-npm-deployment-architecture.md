# Visory Docker、Cloudflare、NPM 与访问安全架构 v1

状态：Design Approved
最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 **D-032**：

- 平台使用独立域名通过公网访问，DNS托管在Cloudflare；
- A/AAAA/CNAME Web记录开启Cloudflare代理，即橙云`Proxied`；
- 源站采用Nginx Proxy Manager（下称NPM）统一接收80/443并转发至Visory；
- Cloudflare SSL/TLS模式固定为`Full (strict)`，禁止`Flexible`；
- NPM使用Let's Encrypt DNS-01和仅限目标Zone的Cloudflare API Token自动申请与续期源站证书；
- 用户访问链路为`Browser → Cloudflare → NPM → visory-api`；
- 浏览器只使用Visory自己的一个owner密码登录，不叠加NPM Basic Auth或第二套Cloudflare Access登录；
- Visory登录页集成Cloudflare Turnstile，浏览器取得的Token必须由FastAPI调用Siteverify完成服务端验证；
- Cloudflare WAF负责边缘风险检测、登录入口规则和速率限制，Turnstile负责人机验证，Visory密码负责身份认证；
- 除登录页所需静态资源和登录/Turnstile最小接口外，所有页面、API、SSE、Artifact和管理入口都必须认证；
- NPM管理端口81不通过域名公开，只绑定`127.0.0.1`并通过SSH端口转发访问；
- `visory-api:8000`、PostgreSQL 5432、Worker和Scheduler均不映射公网端口；
- 源站80/443只接受Cloudflare官方IP段，避免攻击者绕过Cloudflare直连公网IP；
- NPM和平台使用两个Compose Project，通过专用外部Docker网络连接；
- 项目源码、Compose、配置、密钥、数据、NPM状态、日志和备份全部位于`/data/daily_stock_analysis`下；
- 应用、Scheduler和Worker使用非root用户；NPM按官方镜像支持边界运行，但不得使用`privileged`或Docker Socket；
- 当前服务器保持单重任务Worker，不因加入NPM和Cloudflare改变盘后资源优先级；
- v1不引入Cloudflare Tunnel、Kubernetes、Redis、Kafka、NATS或第二台网关；
- v1公网部署关闭viewer和外部PAT，只有一个owner浏览器密码；需要Bot/API访问时以后单独评审受限Token。

## 2. 目标

本部署必须同时满足可访问性、单机资源约束、数据安全和可恢复性：

1. 用户通过一个固定HTTPS域名访问完整平台；
2. 域名入口经过Cloudflare代理、NPM源站TLS和Visory登录三层保护；
3. 登录必须同时通过Turnstile和owner密码验证；
4. 未认证用户不能读取市场、板块、个股、研究、策略、回测和复盘内容；
5. 直接访问服务器IP、8000、5432或81不能绕过保护；
6. SSE任务进度和未来WebSocket在Cloudflare/NPM链路下稳定工作；
7. Visory可以识别经验证的真实客户端IP，用于限流和审计；
8. 所有持久目录都在`/data/daily_stock_analysis`内，方便统一备份和迁移；
9. 配置、密钥、数据和可重建缓存具有不同权限与备份等级；
10. 容器升级不会覆盖数据、证书、任务、策略或审计；
11. 单个容器故障不会破坏已经发布的不可变Result；
12. 能在另一台兼容主机按文档恢复Cloudflare源站、NPM、PostgreSQL和平台数据；
13. 当前服务器资源优先保障16:00盘后数据与正式策略；
14. 公网安全模式不能由Web页面意外关闭认证。

## 3. 非目标

v1不负责：

- 多源站负载均衡和跨地域容灾；
- 面向公众开放注册、找回密码邮件和多人账号体系；
- 通过Cloudflare代理SSH、PostgreSQL或其他非HTTP协议；
- 将NPM管理页面暴露为`npm.example.com`；
- 使用NPM Access List Basic Auth替代应用认证；
- 使用Cloudflare Access再增加一次邮箱、OTP或企业身份登录；
- 使用Cloudflare缓存API、HTML、研究结果或用户数据；
- 把NPM数据库与平台PostgreSQL混用；
- 把Cloudflare API Global Key交给NPM；
- 把Docker Socket挂载到NPM、平台或运维页面；
- 通过公网直接访问Hikyuu、DuckDB、文件目录或Worker；
- 在没有完整备份和回滚点的情况下自动升级镜像。

## 4. 访问拓扑

```text
                         Cloudflare Zone
                 DNS Proxy / TLS / WAF / Turnstile
                                │
                                │ HTTPS 443
                                ▼
                    ┌──────────────────────┐
                    │ Nginx Proxy Manager  │
                    │ 80/443 public        │
                    │ 81 loopback only     │
                    └──────────┬───────────┘
                               │ visory_proxy_net
                               │ http://visory-api:8000
                               ▼
                    ┌──────────────────────┐
                    │ visory-api          │
                    │ React + FastAPI      │
                    │ Password + Session   │
                    │ Turnstile Siteverify │
                    └──────────┬───────────┘
                               │ visory_backend_net
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
          PostgreSQL      Scheduler      Durable Worker
          no host port    no host port   no host port
                                              │
                                              ▼
                              Parquet / DuckDB / Hikyuu
```

### 4.1 浏览器登录流

```text
GET /login
  → Cloudflare边缘检查
  → NPM转发登录壳
  → React显式渲染Turnstile
  → 用户输入唯一owner密码
  → POST /api/v1/auth/login(password, turnstile_token)
  → FastAPI调用Cloudflare Siteverify
  → 校验success、hostname和action
  → 校验密码与登录限流
  → 签发Secure/HttpOnly Session Cookie
  → 允许访问平台页面和API
```

Turnstile不是身份认证，不能替代密码；密码验证也不能替代Turnstile服务端验证。

## 5. 域名与Cloudflare DNS

### 5.1 域名变量

文档使用占位符：

```text
<A_STOCK_HOSTNAME> = stock.example.com
<ORIGIN_IPV4>       = 服务器公网IPv4
<ORIGIN_IPV6>       = 服务器公网IPv6，可选
```

实际配置时替换为用户自己的域名，不在Git仓库写入真实IP和Token。

### 5.2 DNS记录

建议仅创建一个平台入口：

| 类型 | 名称 | 内容 | Proxy | TTL |
| --- | --- | --- | --- | --- |
| A | `stock`或实际子域 | `<ORIGIN_IPV4>` | Proxied | Auto |
| AAAA | 同一子域，可选 | `<ORIGIN_IPV6>` | Proxied | Auto |

规则：

- Web记录必须为橙云`Proxied`；
- 不创建指向源站的DNS-only同义子域；
- 不创建独立`api.`域名，前端与API保持同源；
- NPM管理端不创建公网DNS记录；
- SSH使用服务器地址和严格防火墙，不借用Web域名的Cloudflare代理；
- 审查历史DNS、邮件和其他记录，避免泄露同一源站IP；
- Cloudflare记录必须指向真实源站IP，不能指向Cloudflare IP或形成代理回环。

## 6. Cloudflare TLS

### 6.1 加密模式

固定配置：

```text
SSL/TLS encryption mode: Full (strict)
Always Use HTTPS: Enabled
Minimum TLS Version: TLS 1.2
Automatic HTTPS Rewrites: Enabled only after mixed-content check
```

禁止：

- `Flexible`：Cloudflare到源站之间会失去HTTPS；
- 仅`Full`不校验证书：不能确认源站证书有效性；
- 在NPM证书尚未生效时提前切换Strict导致526；
- 使用过期、域名不匹配或自签名且Cloudflare不信任的证书。

### 6.2 源站证书方案

v1选择：

```text
NPM → Let's Encrypt → DNS-01 → Cloudflare API Token
```

原因：

- 不依赖源站80端口完成HTTP Challenge；
- 证书是公开信任证书，满足Cloudflare Full (strict)；
- NPM可以自动续期；
- 后续临时绕过Cloudflare做受控诊断时，浏览器仍可验证证书；
- 不需要手工维护长期Cloudflare Origin CA证书。

### 6.3 Cloudflare DNS Token

Cloudflare Token要求：

- 使用API Token，不使用Global API Key；
- 权限仅为目标Zone的`Zone / DNS / Edit`；
- Resource仅包含实际域名Zone；
- 如Certbot/NPM版本实际需要，再增加最小`Zone / Zone / Read`，不预授予账户级权限；
- 可将Token来源IP限制为服务器固定出口IP；
- Token命名包含用途，如`npm-dns01-stock-origin`；
- Token不进入`.env.example`、Compose、Git、截图和普通备份日志；
- NPM数据备份视为敏感备份，因为其中可能包含证书和DNS凭据；
- 轮换Token后立即执行一次受控证书续期测试；
- 监控证书剩余30、14和7天，续期失败必须告警。

### 6.4 HSTS

- 首次上线不立即启用长周期HSTS；
- HTTPS、证书续期、回滚和所有子域确认正常后，先使用短`max-age`；
- 观察至少一个发布周期后再提高；
- 未确认所有子域HTTPS前不启用`includeSubDomains`；
- 不在首版加入浏览器Preload列表。

## 7. Cloudflare WAF、人机验证与缓存

### 7.1 安全职责

| 层 | 职责 | 不能替代 |
| --- | --- | --- |
| Cloudflare Proxy/WAF | DDoS、边缘规则、速率和风险检测 | DSA身份认证 |
| Turnstile | 登录人机验证 | owner密码 |
| NPM | 源站TLS、Host路由、反向代理 | 应用权限 |
| Visory Session | 身份、授权、CSRF和审计 | Cloudflare源站保护 |

### 7.2 Turnstile配置

生产Widget：

```text
Widget name: visory-owner-login-prod
Allowed hostname: <A_STOCK_HOSTNAME>
Widget mode: Managed
Appearance: interaction-only 或 always
Environment: production
```

实现规则：

- React SPA使用显式渲染；
- Site Key可以进入前端运行时配置，它不是秘密；
- Secret Key只在FastAPI后端读取；
- 登录请求增加`turnstile_token`；
- FastAPI调用`POST https://challenges.cloudflare.com/turnstile/v0/siteverify`；
- 必须校验`success=true`；
- 必须校验返回`hostname`等于`<A_STOCK_HOSTNAME>`；
- Widget使用`action=owner_login`时必须校验Action；
- Token最长2048字符、五分钟有效且单次使用，重复或过期必须重新挑战；
- Siteverify设置短连接和总超时，不无限等待；
- 生产环境验证服务不可用时，新登录默认Fail Closed；
- 已有有效Session不因一次Siteverify故障立即失效；
- Turnstile失败只记录错误码、Ray ID和Hash，不记录Token或Secret；
- 开发和测试使用Cloudflare测试Key，不把生产Secret复制到CI。

### 7.3 WAF规则

建议规则顺序：

1. 只允许目标Host访问平台，未知Host阻断；
2. 对明显恶意路径扫描、异常Method和已知攻击模式阻断；
3. 对`GET /login`的高风险或异常访问使用Managed Challenge；
4. 对`POST /api/v1/auth/login`设置严格速率限制；
5. 对持续失败来源临时阻断；
6. 对正常已认证API、SSE和Artifact下载避免通用浏览器Challenge；
7. Bot相关功能不能一刀切挑战所有`/api/*`，以免破坏XHR和SSE。

不要对登录POST直接返回不可预测的HTML Challenge来代替Turnstile，否则React会收到非JSON响应。登录POST以Turnstile+Rate Limit为主。

### 7.4 缓存规则

明确绕过Cloudflare缓存：

```text
/api/*
/login
/research/*
/strategies/*
/backtests/*
/reviews/*
/operations/*
任何带Set-Cookie或Authorization的响应
```

允许缓存：

- 带内容Hash的`/assets/*`；
- 公开字体、图标和不含用户数据的静态文件；
- 缓存键包含完整文件名Hash。

禁止`Cache Everything`覆盖HTML和API。源站对动态响应设置`Cache-Control: private, no-store`。

## 8. 唯一密码访问墙

### 8.1 v1身份模型

公网v1固定为：

```text
一个owner
一个浏览器登录密码
viewer = disabled
public signup = disabled
password recovery by email = disabled
external PAT = disabled
```

NPM自身管理员凭据只用于基础设施配置，且端口81不公开，不属于平台页面登录链路。

### 8.2 未认证可访问面

只允许：

- `/login`登录壳；
- 登录壳所需的内容Hash静态JS/CSS/字体；
- `/api/v1/auth/status`，只返回认证启用状态和Turnstile Site Key等非敏感信息；
- `/api/v1/auth/login`，仅接受密码和Turnstile Token；
- 内部容器网络健康检查，不通过公网域名暴露详细状态。

生产公网禁止未认证访问：

- 所有业务页面；
- 所有市场、板块、个股、研究、策略、回测和复盘API；
- SSE任务事件；
- Artifact、图片、报告和导出；
- `/docs`、`/redoc`和`/openapi.json`；
- 系统配置、用量、日志、任务和健康详情；
- 旧版兼容端点。

### 8.3 页面访问行为

- 未登录访问任意业务路由时跳转到`/login?next=<safe_path>`；
- `next`只允许本站相对路径，防止开放重定向；
- React不能在认证状态确定前渲染上一次用户数据；
- Zustand/localStorage不保存报告正文、密钥、密码和Session；
- 401清理内存中的敏感页面状态并跳转登录；
- 403显示权限错误，不尝试重复登录；
- 登出后使服务端Session失效，不能只删除浏览器Cookie；
- 浏览器后退不能从前端缓存重新显示敏感内容。

### 8.4 API访问行为

- 所有API由服务端Middleware强制认证，不能仅依靠React路由守卫；
- SSE建立连接前验证Session，长连接期间Session过期时安全终止；
- Artifact下载每次验证Session和资源权限；
- 旧`analysis`、`history`、`screening`等路由执行相同认证；
- Cookie认证写请求增加CSRF验证；
- CORS只允许`https://<A_STOCK_HOSTNAME>`，生产禁用`CORS_ALLOW_ALL`；
- 不接受通过Query String传递密码、Session或Turnstile Secret。

### 8.5 密码和Session

目标安全基线：

- owner密码至少14位，推荐密码管理器生成；
- 密码Hash使用项目批准的强KDF和随机Salt；
- 登录错误不区分密码错误、用户不存在或Turnstile策略细节；
- 连续失败同时受DSA、NPM/Cloudflare两层限流；
- Session Cookie固定为`Secure`、`HttpOnly`和`SameSite=Lax`或更严格；
- Session默认12小时绝对过期，后续可增加空闲过期；
- 登录成功轮换Session，修改密码后撤销旧Session；
- 认证开关、密码变更和Session撤销必须审计；
- 公网模式下不能从Web设置页关闭`ADMIN_AUTH_ENABLED`。

### 8.6 公网模式启动门禁

目标实现新增或固化等价部署契约：

```text
PUBLIC_DOMAIN_MODE=true
ADMIN_AUTH_ENABLED=true
ADMIN_SESSION_MAX_AGE_HOURS=12
CORS_ALLOW_ALL=false
CORS_ORIGINS=https://<A_STOCK_HOSTNAME>
TURNSTILE_ENABLED=true
TURNSTILE_SITE_KEY=<public-site-key>
TURNSTILE_SECRET_FILE=/run/secrets/turnstile_secret
TURNSTILE_EXPECTED_HOSTNAME=<A_STOCK_HOSTNAME>
TURNSTILE_EXPECTED_ACTION=owner_login
```

其中`PUBLIC_DOMAIN_MODE`、Turnstile相关键和Secret File支持属于目标实现要求，不假设当前版本已经具备。

启动时以下任一条件成立必须失败：

- 公网模式但`ADMIN_AUTH_ENABLED`不是true；
- Turnstile未启用、缺少Secret或Hostname不匹配；
- `CORS_ALLOW_ALL=true`；
- Web监听公网接口且未启用认证；
- 生产环境使用Cloudflare Turnstile测试Key；
- Session Secret不可持久或文件权限过宽。

## 9. NPM部署

### 9.1 独立Compose Project

NPM单独作为`visory-edge`项目：

```text
compose project: visory-edge
service: npm
network: visory_proxy_net
```

平台作为`visory-platform`项目：

```text
compose project: visory-platform
services:
  visory-api
  visory-scheduler
  visory-worker
  postgres
networks:
  visory_proxy_net
  visory_backend_net
```

两套Compose可独立升级，NPM故障不应修改平台数据库，平台升级也不覆盖NPM证书。

### 9.2 NPM端口

| Host | Container | 暴露范围 | 用途 |
| --- | --- | --- | --- |
| 80 | 80 | Cloudflare IP段 | HTTP入口和重定向 |
| 443 | 443 | Cloudflare IP段 | HTTPS源站入口 |
| 127.0.0.1:81 | 81 | 本机回环 | NPM管理UI |

NPM管理方式：

```text
SSH到服务器
建立本地端口转发 localhost:8181 → server:127.0.0.1:81
浏览器访问 http://127.0.0.1:8181
```

禁止将81绑定`0.0.0.0`或通过Cloudflare域名公开。

### 9.3 NPM Proxy Host

| 字段 | 值 |
| --- | --- |
| Domain Names | `<A_STOCK_HOSTNAME>` |
| Scheme | `http` |
| Forward Hostname | `visory-api` |
| Forward Port | `8000` |
| Websockets Support | Enabled |
| Block Common Exploits | Enabled |
| Cache Assets | Disabled，由Cloudflare管理静态缓存 |
| SSL Certificate | DNS-01申请的Let's Encrypt证书 |
| Force SSL | Enabled |
| HTTP/2 Support | Enabled |
| HSTS | 初始Disabled，稳定后分阶段启用 |

不要填`127.0.0.1:8000`，NPM容器中的localhost是NPM自身；必须通过共享Docker网络使用服务名。

### 9.4 NPM Advanced配置

平台包含SSE和可能的流式Agent响应，建议Proxy Host Advanced最小配置：

```nginx
client_max_body_size 25m;
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

说明：

- `proxy_buffering off`保证SSE事件及时到达；
- `proxy_cache off`避免NPM缓存认证响应；
- 长Read Timeout只允许受认证的SSE使用，普通长计算仍走Task；
- 上传限制应与FastAPI接口限制取更小值；
- 不在Advanced中粘贴来源不明的“大而全优化模板”；
- 修改后必须在NPM容器内先验证Nginx配置再Reload。

### 9.5 SSE要求

FastAPI SSE响应：

```text
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
Connection: keep-alive
```

- 每15至25秒发送轻量Heartbeat；
- 浏览器断线后用`Last-Event-ID`或`after_event_id`续读；
- Cloudflare缓存规则必须绕过SSE；
- NPM必须关闭Buffering；
- SSE失败时退回低频轮询；
- 任务最终状态仍以PostgreSQL查询为准。

## 10. 真实客户端IP

### 10.1 信任链

```text
Browser IP
  → Cloudflare CF-Connecting-IP
  → NPM real_ip module
  → sanitized X-Forwarded-For / X-Real-IP
  → FastAPI trusted proxy handling
```

### 10.2 NPM

- NPM只信任Cloudflare官方IP段提供的`CF-Connecting-IP`；
- 使用NPM官方支持的Cloudflare IP范围获取或版本化自定义配置；
- `real_ip_header CF-Connecting-IP`；
- 只在源站防火墙已经限制Cloudflare来源后信任该Header；
- Cloudflare IP段更新时自动提醒并受控更新；
- NPM转发的`X-Forwarded-Proto`必须为外部真实HTTPS协议。

### 10.3 FastAPI

当前DSA的`TRUST_X_FORWARDED_FOR`按单层代理设计。Cloudflare→NPM→App属于多层链路，因此目标实现必须：

- 只信任来自`visory_proxy_net`中NPM地址的Forwarded Headers；
- 不接受任意直连客户端伪造`X-Forwarded-For`；
- NPM完成Cloudflare真实IP恢复后再把确定值传给App；
- 用真实客户端IP执行登录限流和安全审计；
- 记录Cloudflare `CF-Ray`用于问题定位；
- 启用前完成伪造Header、直连和多级XFF测试。

在上述校验未完成前，不能仅将`TRUST_X_FORWARDED_FOR=true`视为完整方案。

## 11. Docker网络和端口隔离

### 11.1 网络

#### visory_proxy_net

- 外部Docker Bridge Network；
- 只有NPM和`visory-api`加入；
- NPM通过服务名访问API；
- Scheduler、Worker和PostgreSQL不加入。

#### visory_backend_net

- 平台内部Bridge Network；
- API、Scheduler、Worker和PostgreSQL加入；
- 不发布PostgreSQL端口；
- 容器保留调用Provider、Cloudflare Siteverify和LLM所需的受控出站能力；
- 不允许NPM直接访问PostgreSQL。

### 11.2 端口矩阵

| 服务 | 容器端口 | Host Publish | 公网可见 |
| --- | --- | --- | --- |
| NPM HTTP | 80 | 80 | 仅Cloudflare来源 |
| NPM HTTPS | 443 | 443 | 仅Cloudflare来源 |
| NPM Admin | 81 | `127.0.0.1:81` | 否 |
| Platform API | 8000 | 无 | 否，由NPM访问 |
| PostgreSQL | 5432 | 无 | 否 |
| Scheduler | 无 | 无 | 否 |
| Worker | 无 | 无 | 否 |
| Docker API | 2375/2376 | 无 | 否 |

### 11.3 防火墙

- 云厂商Security Group优先限制80/443只接受Cloudflare官方IPv4/IPv6范围；
- Host Firewall同步限制，避免云侧规则误改；
- Docker发布端口可能绕过简单UFW规则，必须验证`DOCKER-USER`链或等价路径；
- 81不依赖防火墙，Compose直接绑定127.0.0.1；
- SSH只允许管理IP或VPN，使用密钥，禁用密码和远程root登录；
- 所有未使用入站端口默认拒绝；
- 更新Cloudflare IP段前先添加新范围，验证后再移除旧范围，避免中断；
- 上线验收必须从外网测试源站IP直连被拒绝。

## 12. `/data/daily_stock_analysis`目录

```text
/data/daily_stock_analysis/
├── source/
│   └── daily_stock_analysis/          # Git工作树
├── compose/
│   ├── edge.compose.yml               # NPM
│   ├── platform.compose.yml           # Visory平台
│   ├── edge.env.example               # 无秘密模板
│   └── platform.env.example           # 无秘密模板
├── config/
│   ├── app/
│   │   ├── runtime.env                # 非敏感运行配置
│   │   └── logging.yaml
│   ├── platform/
│   │   ├── providers/                 # 数据集级Provider Policy，无密钥
│   │   ├── hikyuu/                    # 缓存构建和引擎非敏感配置
│   │   ├── strategies/                # Strategy/Market/Weight Policy
│   │   ├── indicators/
│   │   ├── sectors/
│   │   └── global-market/
│   ├── npm/
│   │   └── nginx-custom/              # 版本化Nginx片段
│   └── postgres/
│       └── tuning.conf
├── secrets/
│   ├── app/
│   │   ├── admin_session_secret
│   │   ├── turnstile_secret
│   │   ├── llm_keys.env
│   │   └── provider_keys.env
│   ├── postgres/
│   │   └── app_password
│   └── backup/
│       └── repository_password
├── storage/
│   ├── app/
│   │   ├── raw/
│   │   ├── normalized/
│   │   ├── features/
│   │   ├── observations/
│   │   ├── factpacks/
│   │   ├── results/
│   │   ├── artifacts/
│   │   ├── hikyuu/
│   │   ├── state/
│   │   ├── quarantine/
│   │   └── .staging/
│   ├── postgres/
│   └── npm/
│       ├── data/
│       └── letsencrypt/
├── logs/
│   ├── app/
│   ├── worker/
│   ├── scheduler/
│   ├── npm/
│   └── backup/
├── backups/
│   ├── postgres/
│   ├── npm/
│   ├── config/
│   ├── manifests/
│   └── restore-tests/
└── tmp/
    ├── app/
    ├── worker/
    └── export/
```

规则：

- 目录根路径固定，不使用宿主机`~`；
- 容器挂载必须指向明确子目录，不把整个`/data`挂进容器；
- Secret只读挂载到需要它的容器；
- Worker不挂载NPM或PostgreSQL数据目录；
- NPM不挂载应用数据、源码或Docker Socket；
- API不直接写Raw和Feature发布目录，正式写入由Worker完成；
- `tmp`可清理但不能作为正式Result唯一存储；
- 备份目录不能被应用写入覆盖；
- 源码与运行数据分开备份和恢复。

## 13. 容器清单

### 13.1 npm

- 使用官方`jc21/nginx-proxy-manager`镜像；
- 使用经过测试的固定版本或Digest，不使用无约束`latest`；
- `restart: unless-stopped`；
- 挂载`storage/npm/data`和`storage/npm/letsencrypt`；
- 使用官方`/usr/bin/check-health`健康检查；
- 不使用`privileged`；
- 不挂载Docker Socket；
- 管理端只绑定回环；
- SQLite适合个人单机v1，不与平台PostgreSQL混用；
- 升级前必须备份NPM数据和证书。

### 13.2 visory-api

- 同时提供React静态资源和FastAPI；
- `WEBUI_HOST=0.0.0.0`仅在容器网络内监听；
- `WEBUI_PORT=8000`；
- `ADMIN_AUTH_ENABLED=true`；
- 不发布Host端口；
- 使用固定非root UID/GID；
- 根文件系统尽量只读，写目录使用明确Volume或tmpfs；
- 只执行查询、认证、命令提交和SSE，不执行重计算；
- 健康检查从容器网络访问；
- 优雅停机先停止接收新请求，再等待短请求完成。

### 13.3 visory-scheduler

- 与API使用相同应用镜像和版本；
- 只持有一个PostgreSQL Singleton Lease；
- 不公开端口；
- 不直接执行长任务；
- 只挂载必要配置和状态；
- 重启后从PostgreSQL重新对账调度计划。

### 13.4 visory-worker

- 与API使用相同应用镜像和版本；
- 单`HEAVY`执行槽；
- 负责数据、Feature、Hikyuu、复盘、研究和Artifact；
- Hikyuu与L2研究使用受控子进程；
- 挂载App数据目录，不挂载NPM和PostgreSQL底层文件；
- 支持Checkpoint、取消和优雅停机；
- 16:00前停止领取P3重任务；
- 内存水位超限时不领取新任务。

### 13.5 postgres

- 使用固定PostgreSQL主版本和镜像Digest；
- 只加入Backend Network；
- 不映射5432；
- 密码使用Secret File或等价安全注入；
- 数据目录独占；
- 配置合理的连接数、共享内存和WAL；
- 健康检查只验证数据库可连接，不执行重查询；
- 大版本升级必须使用官方升级流程或逻辑导入，不能直接更换镜像读取旧目录。

## 14. 配置与密钥

### 14.1 配置分层

| 类型 | 例子 | 存放 | Git |
| --- | --- | --- | --- |
| 模板 | Compose、`.env.example` | `compose/` | 可版本化 |
| 非敏感运行配置 | 时区、端口、调度时间、日志级别 | `config/app/runtime.env` | 按需要，生产值不必入库 |
| Secret | LLM Key、Provider Key、Turnstile Secret、DB密码 | `secrets/` | 禁止 |
| 持久状态 | NPM DB、证书、PostgreSQL、Session状态 | `storage/` | 禁止 |
| 可重建缓存 | tmp、Projection Cache | `tmp/`或受控cache | 禁止 |

### 14.2 应用现有配置

当前DSA已存在的部署配置至少需要：

```text
WEBUI_HOST=0.0.0.0
WEBUI_PORT=8000
ADMIN_AUTH_ENABLED=true
ADMIN_SESSION_MAX_AGE_HOURS=12
CORS_ALLOW_ALL=false
CORS_ORIGINS=https://<A_STOCK_HOSTNAME>
```

`TRUST_X_FORWARDED_FOR`只有在第10节真实IP链验证通过后才能启用。

目标平台新增配置契约使用“非敏感值+Secret File路径”，实现时同步到`platform.env.example`与`config/app/runtime.env.example`：

```text
APP_ENV=production
PUBLIC_BASE_URL=https://<A_STOCK_HOSTNAME>
TZ=Asia/Shanghai
VISORY_RUNTIME_ROOT=/data/daily_stock_analysis
APP_STORAGE_ROOT=/var/lib/visory/app

DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=visory
DATABASE_USER=visory_app
DATABASE_PASSWORD_FILE=/run/secrets/postgres_app_password

ADMIN_PASSWORD_HASH_FILE=/run/secrets/admin_password_hash
ADMIN_SESSION_SECRET_FILE=/run/secrets/admin_session_secret
ADMIN_SESSION_MAX_AGE_HOURS=12

TURNSTILE_SITE_KEY=<PUBLIC_SITE_KEY>
TURNSTILE_SECRET_FILE=/run/secrets/turnstile_secret
TURNSTILE_EXPECTED_HOSTNAME=<A_STOCK_HOSTNAME>
TURNSTILE_EXPECTED_ACTION=owner_login

POST_CLOSE_TIME=16:00
FORMAL_STRATEGY_HARD_DEADLINE=19:00
SCHEDULER_TIMEZONE=Asia/Shanghai
TASK_WORKER_CAPABILITIES=provider,feature,hikyuu,review,research,maintenance
TASK_WORKER_HEAVY_CONCURRENCY=1
```

约束：

- `VISORY_RUNTIME_ROOT`由Compose解析宿主机挂载，不原样传入业务容器；容器内`APP_STORAGE_ROOT`只映射宿主机`/data/daily_stock_analysis/storage/app`；
- `TURNSTILE_SITE_KEY`是公开值，其他密码/Token只通过`*_FILE`读取；
- Provider、LLM和备份凭据分别挂载专用Secret文件，不合并为可被全部容器读取的全局环境文件；
- 16:00/19:00配置若改变，必须提升Schedule/Policy版本并更新SLA文档，不能只改Cron；
- `TASK_WORKER_HEAVY_CONCURRENCY`在当前服务器MVP固定为1。

### 14.3 Secret权限

- `secrets/`目录默认`0700`或按专用组`0750`；
- 单Secret文件`0600`，由对应容器UID或受控组读取；
- 配置目录默认`0750`，非秘密文件`0640`；
- App数据目录只允许App UID/GID写；
- PostgreSQL和NPM数据目录分别归属各自容器需要的UID/GID；
- 不用`chmod -R 777`解决挂载权限；
- root只用于首次创建、chown和受控运维，应用进程不长期以root运行；
- Secret备份必须加密，恢复日志不得打印值。

## 15. 资源限制

### 15.1 原则

- 至少为宿主机和Docker保留15%内存与CPU余量；
- NPM和API保持轻量，Worker获得主要计算预算；
- PostgreSQL连接池和缓存按实际内存限制，不使用默认无限增长假设；
- DuckDB线程数和Memory Limit必须显式配置；
- Hikyuu、历史回填和L2研究不能并发；
- 容器限制应使用当前服务器实际CPU/RAM换算，文档不在未知配置下伪造固定数值；
- 限制触发必须产生可见Task状态和告警，不能静默杀死后伪装成功。

### 15.2 建议预算比例

| 单元 | CPU预算 | 内存预算 | 备注 |
| --- | --- | --- | --- |
| NPM | 5%—10% | 5%—8% | TLS和代理 |
| Platform API | 10%—15% | 10%—15% | 查询与SSE |
| Scheduler | 约5% | 约5% | 轻量单例 |
| PostgreSQL | 10%—20% | 15%—20% | 控制面 |
| Worker/Hikyuu | 45%—60% | 45%—55% | 单重任务 |
| Host余量 | 至少15% | 至少15% | 内核、Docker、峰值和备份 |

比例不能简单相加为长期满载；Worker高峰时其他单元应保持低占用。

### 15.3 降级顺序

1. 暂停历史回填；
2. 停止新L2研究；
3. 延后Research Backtest；
4. 降低非核心页面Projection刷新；
5. 保留Cloudflare/NPM、API登录、PostgreSQL、P0数据和P1核心流水线；
6. 核心资源不足时阻断Formal Result，不降低真实性门槛。

## 16. 日志和监控

### 16.1 必须监控

- Cloudflare请求量、WAF事件、Managed Challenge和Rate Limit；
- Turnstile通过率、失败码、Siteverify延迟和Hostname不匹配；
- NPM 4xx/5xx、证书到期、续期失败和Upstream错误；
- FastAPI 401、403、429、登录失败、Session创建和SSE断线；
- PostgreSQL连接、容量、WAL和备份；
- Worker心跳、队列、租约、OOM和任务超时；
- `/data`磁盘水位、inode和备份增长；
- Cloudflare IP列表更新时间；
- 上次成功备份和恢复演练。

### 16.2 日志关联

请求尽量关联：

```text
CF-Ray
request_id
client_ip_hash
session_id_hash
task_id
attempt_id
snapshot_id
```

禁止记录：

- owner密码；
- Session Cookie；
- Turnstile Token和Secret；
- Cloudflare DNS Token；
- Provider/LLM Key；
- PostgreSQL密码；
- 完整敏感Prompt和未脱敏导出。

## 17. 备份设计

### 17.1 备份等级

#### A级：不可替代控制面

- PostgreSQL逻辑备份；
- StrategySpec、任务、审计和Manifest；
- NPM SQLite、配置和Let's Encrypt证书；
- App与NPM非公开配置；
- 加密Secret备份；
- Git Commit和部署版本清单。

#### B级：重要业务数据

- Raw和Normalized数据；
- FactPack、Research、Review和Backtest Artifact；
- Hikyuu必要行情缓存；
- 通知和质量报告。

#### C级：可重建数据

- 未被正式Result引用的Feature缓存；
- 页面Projection Cache；
- 临时导出和tmp；
- 可再生成的前端构建产物。

### 17.2 周期

- PostgreSQL每日逻辑备份，重大迁移前额外备份；
- NPM与证书每日一致性备份，升级前额外备份；
- Manifest、Strategy和Config每日备份；
- Raw/Normalized/Artifact使用增量备份；
- 本地保留建议为7个日备、4个周备、6个月备；
- 至少一份加密备份离开当前服务器；
- 本地`/data`备份不能被视为主机故障容灾；
- 每月至少执行一次抽样恢复，每季度执行一次完整恢复演练。

### 17.3 一致性

- PostgreSQL使用`pg_dump`等数据库一致性方式，不直接复制运行中的数据目录作为唯一备份；
- NPM使用SQLite一致性备份或短暂停写后备份，不能随意复制半写入数据库；
- Manifest与Artifact备份记录同一发布水位；
- 备份完成后计算Hash并写只读清单；
- 备份失败产生P0/P1运维告警；
- 加密备份的恢复密钥不能只保存在同一服务器。

## 18. 恢复顺序

建议恢复流程：

1. 安装兼容Docker与Compose；
2. 创建`/data/daily_stock_analysis`目录、UID/GID和权限；
3. 恢复Compose、配置和Secret；
4. 创建`visory_proxy_net`和`visory_backend_net`；
5. 恢复NPM数据与证书，但暂不切换DNS；
6. 启动PostgreSQL并导入逻辑备份；
7. 恢复Manifest、Raw、Normalized、FactPack和Artifact；
8. 启动API并在内部网络验证认证、Turnstile测试模式和只读页面；
9. 启动Scheduler和Worker，确认不会重复创建正式任务；
10. 在NPM验证证书、Host、SSE和登录；
11. 更新Cloudflare源站IP并保持Proxied；
12. 验证Full Strict、WAF、Turnstile和防火墙；
13. 完成一条历史追溯和一个非正式测试任务后恢复调度。

恢复不能直接把旧Worker标记为成功。所有租约过期Task必须对账。

## 19. 升级和回滚

### 19.1 镜像

- 平台镜像绑定Git Commit和内容Digest；
- NPM和PostgreSQL使用固定版本；
- 不执行无人值守的`latest`自动更新；
- 上线前记录当前镜像Digest、Schema Version和配置Hash；
- 镜像漏洞修复先在测试环境或离线Compose验证。

### 19.2 顺序

1. 暂停新P3任务；
2. 等待或Checkpoint当前重任务；
3. 备份PostgreSQL、NPM、配置和Manifest；
4. 拉取固定镜像；
5. 执行数据库向前兼容迁移；
6. 先升级API，再升级Scheduler和Worker；
7. 验证登录、Turnstile、SSE、查询和Task Lease；
8. 最后恢复调度；
9. NPM升级独立进行，不与平台Schema迁移同时实施。

### 19.3 回滚

- 应用回滚使用旧镜像和兼容Schema；
- 破坏性Schema迁移必须有反向方案或从备份恢复；
- NPM回滚同时恢复匹配版本的数据与证书备份；
- Cloudflare配置变更保存前后快照；
- 不把Cloudflare切为DNS-only作为常规故障排除手段；
- 紧急绕过必须有明确时限、管理IP白名单和审计。

## 20. 需要形成的配置文件

实现阶段应提供：

```text
/data/daily_stock_analysis/compose/edge.compose.yml
/data/daily_stock_analysis/compose/platform.compose.yml
/data/daily_stock_analysis/compose/edge.env.example
/data/daily_stock_analysis/compose/platform.env.example
/data/daily_stock_analysis/config/npm/nginx-custom/http_top.conf
/data/daily_stock_analysis/config/npm/nginx-custom/server_proxy.conf
/data/daily_stock_analysis/config/app/runtime.env.example
/data/daily_stock_analysis/config/platform/providers/provider-policy.example.yaml
/data/daily_stock_analysis/config/platform/hikyuu/runtime.example.yaml
/data/daily_stock_analysis/config/platform/strategies/market-rules.example.yaml
/data/daily_stock_analysis/config/platform/strategies/weight-policy.example.yaml
/data/daily_stock_analysis/config/platform/strategies/strategy.example.yaml
/data/daily_stock_analysis/config/postgres/tuning.conf.example
/data/daily_stock_analysis/scripts/preflight.sh
/data/daily_stock_analysis/scripts/backup.sh
/data/daily_stock_analysis/scripts/restore-check.sh
/data/daily_stock_analysis/scripts/update-cloudflare-ips.sh
/data/daily_stock_analysis/DEPLOYMENT-CHECKLIST.md
```

要求：

- 示例文件只含占位符；
- Secret文件由用户在服务器填写；
- Preflight检查端口、目录、UID、磁盘、DNS、证书和Docker网络；
- Backup和Restore脚本不得把Secret输出到终端；
- Cloudflare IP更新先验证签名/HTTPS来源和语法，再原子替换；
- 所有脚本默认Dry Run或明确确认破坏性操作；
- 生成Compose前先记录服务器CPU、内存、磁盘和架构，再计算资源限额。

## 21. 实施顺序

### DP0：本地生产等价预演

- 使用`VISORY_RUNTIME_ROOT`绑定仓库外部或已忽略的本地运行根，不创建真实`/data/daily_stock_analysis`；
- 使用Turnstile官方测试Key、本地owner测试密码和临时PostgreSQL Secret，禁止复制生产Secret；
- 运行Compose Config、镜像Build、空库Migration、回环登录、SSE、Artifact、备份和空目录恢复验收；
- 验证容器非root、最小挂载、无公网业务端口、健康检查、固定镜像Digest和兼容回滚；
- 生成Local Release Manifest，列出镜像、Schema、配置Hash、测试、资源Benchmark和未验证的外部项。

DP0和总指引的Local Release Gate未通过时，不执行后续DP1—DP6，不在服务器使用`sudo`创建目录、启动容器或修改Cloudflare/NPM。

### DP1：目录与镜像

- 创建`/data/daily_stock_analysis`子目录；
- 固化UID/GID和权限；
- 拉取代码到`source/`；
- 构建并固定平台镜像；
- 创建两个Docker网络。

### DP2：PostgreSQL与平台内部验证

- 启动PostgreSQL；
- 启动API、Scheduler和单Worker；
- 在Docker内部验证健康、任务和数据目录；
- 暂不开放公网端口。

### DP3：认证与Turnstile

- 实现全页面Auth Wall；
- 增加Turnstile显式Widget和Siteverify；
- 公网模式强制认证；
- 保护Docs、SSE、Artifact和旧端点；
- 完成密码、Session、CSRF、限流和Fail Closed测试。

### DP4：NPM

- 启动NPM；
- 81绑定回环并修改初始管理员凭据；
- 配置Proxy Host、共享网络和Advanced；
- 使用DNS-01申请证书；
- 在本地Host映射或受控测试域名验证Full Strict前置条件。

### DP5：Cloudflare

- 创建Proxied DNS；
- 设置Full Strict和Always HTTPS；
- 配置Turnstile、缓存、WAF和Rate Limit；
- 限制源站80/443只接受Cloudflare IP；
- 验证真实IP和CF-Ray。

### DP6：备份和上线

- 完成首份PostgreSQL、NPM、Manifest和Secret加密备份；
- 执行恢复抽测；
- 验证登录、页面、API、SSE、下载和登出；
- 验证直接IP、81、8000和5432无法公网访问；
- 再启用16:00正式调度。

## 22. 验收标准

1. `<A_STOCK_HOSTNAME>`为Cloudflare Proxied记录；
2. 浏览器到Cloudflare、Cloudflare到NPM均为加密连接；
3. Cloudflare使用Full (strict)，证书有效且匹配域名；
4. NPM证书可以通过DNS-01受控续期；
5. Cloudflare Token仅拥有目标Zone DNS权限；
6. 未登录用户只能看到登录壳，不能读取任何业务数据；
7. 所有业务页面、API、SSE、Artifact和旧端点均验证Session；
8. 登录必须同时通过Turnstile服务端验证和owner密码；
9. 伪造、过期、重复或Hostname不匹配的Turnstile Token被拒绝；
10. Turnstile Secret不会进入前端、日志、Git和普通响应；
11. 公网模式不能关闭`ADMIN_AUTH_ENABLED`；
12. `/docs`、`/redoc`和`/openapi.json`不向未认证公网用户开放；
13. NPM管理端81仅能经本机回环/SSH隧道访问；
14. 平台8000和PostgreSQL 5432没有Host Publish；
15. 源站80/443拒绝非Cloudflare来源直连；
16. Docker端口规则不会绕过Host/云防火墙；
17. FastAPI审计获得经过可信链恢复的真实客户端IP；
18. SSE经过Cloudflare和NPM持续工作、定期Heartbeat且可断线续读；
19. Cloudflare不缓存API、HTML、登录、SSE和个性化响应；
20. 全部持久目录位于`/data/daily_stock_analysis`下；
21. NPM、平台、PostgreSQL分别使用最小挂载，不共享底层数据目录；
22. 应用、Scheduler和Worker不以root运行；
23. 没有容器使用`privileged`或挂载Docker Socket；
24. 单重Worker维持P0/P1优先级和16:00资源门禁；
25. PostgreSQL、NPM、Manifest和Secret存在可验证加密备份；
26. 完整恢复演练能重建域名入口、认证、任务和历史追溯；
27. 镜像、Git Commit、Schema和配置Hash可追溯；
28. 直接访问公网IP不会出现可用的平台登录或业务页面。

## 23. 上线时由owner提供的环境输入

架构和Compose边界已经确定。以下值不能写入仓库，必须在实际上线时由owner提供或在服务器生成：

1. 实际平台域名；
2. Cloudflare Zone ID与受限DNS Token；
3. Turnstile Site Key与Secret Key；
4. owner初始强密码；
5. 服务器公网IPv4/IPv6和云Security Group权限；
6. 服务器实际CPU、内存和磁盘，用于换算Docker限额；
7. 加密离机备份目标；
8. SSH管理来源IP或VPN范围。

Claude Code或Codex在缺少这些值时仍可生成无密钥模板、运行Compose静态校验、构建镜像和完成本地Loopback测试，但不能宣称Cloudflare公网链路或恢复目标已经验收。MVP实施和阶段门禁见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。

## 24. 参考资料

- [Cloudflare Proxy status](https://developers.cloudflare.com/dns/proxy-status/)
- [Cloudflare支持的代理端口](https://developers.cloudflare.com/fundamentals/reference/network-ports/)
- [Cloudflare Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
- [Cloudflare保护源站](https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/)
- [Cloudflare IP地址与源站Allowlist](https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/)
- [Cloudflare HTTP Headers与CF-Connecting-IP](https://developers.cloudflare.com/fundamentals/reference/http-headers/)
- [Cloudflare Turnstile入门](https://developers.cloudflare.com/turnstile/get-started/)
- [Cloudflare Turnstile服务端验证](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)
- [Cloudflare Turnstile React/SPA显式渲染](https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/)
- [Cloudflare WAF Managed Challenge](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/create-custom-rule/)
- [Cloudflare API Token最小权限](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
- [Nginx Proxy Manager官方仓库](https://github.com/NginxProxyManager/nginx-proxy-manager)
- [Nginx Proxy Manager安装](https://github.com/NginxProxyManager/nginx-proxy-manager/blob/develop/docs/src/setup/index.md)
- [Nginx Proxy Manager高级配置与Docker Network](https://github.com/NginxProxyManager/nginx-proxy-manager/blob/develop/docs/src/advanced-config/index.md)
- [A 股主平台模块化单体、API、任务与权限架构 v1](platform-shell-api-task-permission-architecture.md)
- [盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
