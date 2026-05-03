# OSPAY API & CI TEST 

##### This is a project with front-end and back-end separation.

##### Backend by python with tornado

# How to OSPAY API project in Development

### Clone ospay_api project

```git clone https://github.com/baofeng16888/ospay_api```

Before start running the project.

### Setup Config Files

1. In the ```root``` directory.
2. Copy, paste and rename the files from ```/config.example.py``` to```config.py```, ```config.py``` with some xxxxxx,
   you can skip it.

- These files are necessary for the platform service api and some functionality to work successfully.

### Run Project in Terminal with Docker

```
$ docker-compose build
$ docker-compose up
```

#### How to Use

Go to http://127.0.0.1:9000 via Postman or Browser

## EasyPaisa 运行态约定

EasyPaisa 当前运行态已经统一到 `application/easypaisa_runtime/`：

1. `easypaisa_runtime:snapshot:{payment_id}`
   - 单账号主状态
2. `easypaisa_runtime:index:online`
   - 钱包在线索引
3. `easypaisa_runtime:index:dispatch_df`
   - 代付/接单在线索引
4. `easypaisa_runtime:index:dispatch_ds`
   - 采集/代收在线索引

补充字段约定：

- `snapshot.channels`
  - EasyPaisa 当前允许投影到哪些 `payment_active_{channel}` 队列
  - 统一保存为字符串数组，例如 `["1001"]`

兼容层约定：

- `payment_online_df`
- `payment_online_ds`
- `payment_active_{channel}`
- `login_on_easypaisa_*`
- `hash_easypaisa`
- `set_easypaisa`

这些 key 仍会存在，但只允许作为 runtime 派生投影，不允许再被当成 EasyPaisa 主真相源。

分层边界：

- SQL 是配置唯一源，`payment.status`、`certified`、`manual_status`、`channel` 等字段只能从 SQL 判断。
- `easypaisa_runtime:session:{payment_id}` 是登录真相源，登录流程不得用 legacy 在线 key 反推登录态。
- `easypaisa_runtime:snapshot:{payment_id}` 与 `easypaisa_runtime:index:*` 是运行调度真相源。
- `hash_easypaisa` / `set_easypaisa` 是 runtime 给 Pakistanpay worker 的任务投影，生产代码应通过 `keyspace.JOB_HASH` / `keyspace.JOB_SET` 引用。
- Pakistanpay worker 的调试读取只允许看 worker 投影和 worker 私有缓存，不允许读取 `login_on_easypaisa_*`、`payment_online_*`、`payment_active_*`、`kick_off_*`。
- legacy key 只能由 runtime service/legacy bridge 生成或清理，不能作为 EasyPaisa 接单、登录或排障事实。

其中：

- `dispatch_ds=true` 时
  - 必须同步投影到 `payment_online_ds`
  - 必须按 `snapshot.channels` 投影到对应的 `payment_active_{channel}`
- `dispatch_ds=false` 时
  - 必须同时从上述集合/队列移除

读面口径：

- `/user/upi.place_order_status` -> `dispatch_df`
- `/user/upi.selling_order_status` -> `dispatch_ds`
- `app/my.getpayment.online_df` -> `dispatch_df`
- `app/my.getpayment.online_ds` -> `dispatch_ds`

写面口径：

- EasyPaisa app 接单开关 `selling_active/selling_inactive`
  - 必须通过 `EasyPaisaRuntimeService.set_collection_dispatch(...)` 同步 `dispatch_ds`
  - 不能再只改 `payment.certified`
- `jobs/easypaisa/easypaisa_monitor.py`
  - 对数据库仍满足 `payment.status=1 && payment.certified=1` 的账号，在线恢复时必须显式回写 `dispatch_ds=true`
  - 不能继续继承旧 snapshot 里的 `dispatch_ds=false`
- admin `force_reset`
  - 必须一起清：
    - `easypaisa_runtime:index:dispatch_ds`
    - `payment_online_ds`
    - `payment_active_{channel}`

## EasyPaisa 回调与 jobs 写面约定

EasyPaisa 当前代收闭环有两个必须遵守的约定：

1. `jobs/pakistanpay_v2.py`
   - 回调 URL 必须通过 `get_order_success_url()` 规范化
   - `send()` 必须优先走 `internal_callback_host`，默认是 `http://127.0.0.1:9000/order/Success`
   - 仅当内部地址缺失时，才回退到 `ospay_api_host`
   - 当 `ospay_api_host` 配成 `http://host/api` 时，真实回调地址仍应是 `http://host/order/Success`
   - 不能为了修 EasyPaisa job 的内部回调，去全局删掉公网域名上的 `/api`
   - 回调失败时不能写入 `if_callback_easypaisa`
2. `application/easypaisa_runtime/sync_runtime_service.py`
   - `sync_collection_job_state()` 回写 `hash_easypaisa` 时必须合并已有登录态
   - 不能用最小 runtime 投影覆盖已有完整会话字段，如：
     - `authorization`
     - `headers`
     - `qr_channel`
     - `account_entire`

3. `jobs/pakistanpay_v2.py`
   - `423 云机正忙查单` 属于临时抓账异常
   - `grabstatement` 和 `verify_and_handle_abnormal_payout()` 遇到这类错误时，不能执行 `on_off(_on=0)`
   - 这类异常只能保留失败标记和重试，不能误移除 `payment_active_{channel}`

线上补单约定：

- 若 `/order/Success` 因超过 8 分钟匹配窗返回 `Order not found`，应先确认是否已落一条 `bank_record(callback=0)`。
- 若已落库，使用正式补单入口 `/pay/ds/utr` 完成闭环，不要直接手改订单成功状态。
- 若 jobs 与 API 不在同一台机器，可通过环境变量 `API_INTERNAL_CALLBACK_HOST` 指定内部回调地址。
- 若需要继续保留公网回调域名 `api.aweces.com`，线上 nginx 的 `api.aweces.com.conf` 必须把 `api.aweces.com` 放进 `server_name`。
- 当前公网回调入口口径是：
  - `http://api.aweces.com/api/order/Success` -> 301 到 HTTPS
  - `https://api.aweces.com/api/order/Success` -> 可命中 API
  - `https://api.aweces.com/order/Success` -> 404

## how to send SMS messages in DEV

```python
import global_resources
import logging
from redis import asyncio as aioredis
from application.lakshmi_api.services.sms_service import SmsService
from config import get_config
conf = get_config()
logger = logging.getLogger()
redis = aioredis.from_url('redis://%s' % conf['redis_host'], encoding="utf-8", decode_responses=True)
global_resources.redis = redis
global_resources.logger = logger
sms_service = SmsService()
if await sms_service.send_fast2_sms('999999999'):
    print("do something")

# you can check it in console 'phonecode999999999_2704'
```

## create lakshmi_api_setting

```python
from prisma import Prisma

prisma = Prisma()
await prisma.connect()
await prisma.lakshmi_api_setting.create_many(
    data=[
        {'genre': 'USDT', 'name': 'usdt_exchange_rate', 'key': 'rate', 'value': '15729'},
        {'genre': 'USDT', 'name': 'usdt_exchange_status', 'key': 'status', 'value': 'False'}
    ]
)
```

## add lakshmi_api_setting order_amount_filter

```python
from prisma import Prisma

prisma = Prisma()
await prisma.connect()
await prisma.lakshmi_api_setting.create_many(
    data=[
        {'genre': 'order_amount_filter', 'name': 'range 1', 'key': 'range 1', 'value': '500'},
        {'genre': 'order_amount_filter', 'name': 'range 2', 'key': 'range 2', 'value': '999'},
        {'genre': 'order_amount_filter', 'name': 'range 3', 'key': 'range 3', 'value': '1999'},
        {'genre': 'order_amount_filter', 'name': 'range 4', 'key': 'range 4', 'value': '4999'},
        {'genre': 'order_amount_filter', 'name': 'range 5', 'key': 'range 5', 'value': '10000'}
    ]
)
```

## add default logo_url for bank_type

```python
from prisma import Prisma

prisma = Prisma()
await prisma.connect()

await prisma.bank_type.update_many(
    where={},
    data={
        'logo_url': 'https://dummyimage.com/32x32/000/fff',
    }
)
```

## add text_materials

```python
from prisma import Prisma

prisma = Prisma()
await prisma.connect()

text_materials = [
    {'title': 'About Us', 'genre': 'about_us', 'content': '''Welcome to Lakshmi, your premier destination for buying and selling Laktokens effortlessly.
        At Lakshmi, we understand the importance of creating a seamless platform where users can engage in transactions with confidence and convenience. Whether you're looking to purchase Laktokens to access exclusive services or wish to sell them for profit, Lakshmi provides a secure and user-friendly environment to meet your needs.
        Our mission is to empower individuals by providing them with a reliable marketplace to trade Laktokens, without the complexities often associated with traditional financial transactions. With Lakshmi, you can unlock new opportunities and harness the full potential of Laktokens.
        Join our community today and experience the future of token trading with Lakshmi.'''},
    {'title': 'Privacy Policy', 'genre': 'private_policy', 'content': '''At Lakshmi, we are committed to protecting your privacy and ensuring the security of your personal information. This Privacy Policy outlines how we collect, use, and safeguard your data when you use our mobile application.
        We may collect personal information such as your name, email address, and payment details when you register an account with Lakshmi or make transactions within the app. This information is used to facilitate your transactions and provide you with personalized services.
        We implement industry-standard security measures to protect your personal information from unauthorized access, disclosure, alteration, or destruction. Your data is stored securely on our servers and is accessible only to authorized personnel.
        We do not sell, trade, or rent your personal information to third parties. However, we may share your data with trusted service providers who assist us in operating our app or conducting business activities on our behalf.
        Lakshmi may use cookies and similar tracking technologies to enhance your user experience and analyze app usage patterns. These technologies collect information such as your device type, IP address, and browsing behavior to improve our services and marketing efforts.
        Our app may contain links to third-party websites or services that are not owned or controlled by Lakshmi. We are not responsible for the privacy practices or content of these third parties. We encourage you to review the privacy policies of any third-party sites you visit.
        We reserve the right to update or modify this Privacy Policy at any time. Any changes will be effective immediately upon posting the updated policy on our app. By continuing to use Lakshmi after any changes, you accept the revised Privacy Policy.
        If you have any questions or concerns about this Privacy Policy or our data practices, please contact us.'''},
]

for material in text_materials:
    text_material = await prisma.text_materials.create(data=material)
    print(text_material)
```

## how to use python console call websocket

`root@d9818d165dcf:/usr/src/app# ipython`

```python
import asyncio
import aioredis
import json
from config import get_config

conf = get_config()
redis_pub = await aioredis.create_redis((conf['redis_host'], 6379))
public_channel_name = 'public_channel'
await redis_pub.publish(
    public_channel_name,
    json.dumps(
        {
            "type": "publish_everyone",
            "content": 'test'
        }
    )
)
```

## how to check how many channel

`root@d9818d165dcf:/usr/src/app# ipython`

```python
import asyncio
import aioredis
from config import get_config

conf = get_config()
redis_sub = await aioredis.create_redis((conf['redis_host'], 6379))
channels = await redis.execute('pubsub', 'channels')
channels
# [b'public_channel', b'user_channel_c9ec6352-e7eb-44dc-bd40-1b4dd5ef905f']
result = await redis.execute('pubsub', 'numsub', 'public_channel')
result
# [b'public_channel', 9]
```

## how to query via orm

`root@d9818d165dcf:/usr/src/app# ipython`

```python
from tornado_sqlalchemy import SQLAlchemy
from config import get_config

conf = get_config()
db_orm = SQLAlchemy()
db_orm.configure(
    url=f"mysql+pymysql://{conf['mysql_user']}:{conf['mysql_password']}@{conf['mysql_host']}/{conf['mysql_database']}?charset=utf8",
    engine_options={
        "pool_size": 20,
        "max_overflow": 10,
        "echo": True
    }
)
global_resources.db_orm = db_orm
from application.lakshmi_api.models import *

session = db_orm.sessionmaker()
current_user = session.query(User).filter_by(id=1).first()
balance_change_records = current_user.balance_change_records.order_by(BalanceRecord.id.desc()).limit(10).all()
```

## testing ws service

```python
import aioredis
from tornado_sqlalchemy import SQLAlchemy
from config import get_config

conf = get_config()
db_orm = SQLAlchemy()
db_orm.configure(
    url=f"mysql+pymysql://{conf['mysql_user']}:{conf['mysql_password']}@{conf['mysql_host']}/{conf['mysql_database']}?charset=utf8",
    engine_options={
        "pool_size": 20,
        "max_overflow": 10,
        "echo": True
    }
)
redis_pub = await aioredis.create_redis((conf['redis_host'], 6379))

from application.lakshmi_api.services.websockets.user_service import UserPushService

await UserPushService.disconnect_user_channel(db_orm, redis_pub, 1)
```

```python
import asyncio
from application.lakshmi_api.models import *
from application.lakshmi_api.services.partner_tree_service import PartnerTreeService
import logging
from datetime import datetime, timedelta, time
from tornado_sqlalchemy import SQLAlchemy
from config import get_config

conf = get_config()
db_orm = SQLAlchemy()
db_orm.configure(
    url=f"mysql+pymysql://{conf['mysql_user']}:{conf['mysql_password']}@{conf['mysql_host']}/{conf['mysql_database']}?charset=utf8",
    engine_options={
        "pool_size": 20,
        "max_overflow": 10,
        "echo": True
    }
)
session = db_orm.sessionmaker()
parent_id = 'xxxxx'
start_at = datetime.combine(datetime.now() - timedelta(days=90), datetime.min.time())
logger = logging.getLogger()
partner_service = PartnerTreeService()
partners =asyncio.run(partner_service.self_and_descendants(parent_id))
```

```python
import asyncio
import redis

redis = redis.Redis(host='redis', port=6379)
redis.sadd('payment_online_df', '500678')
```

## how to test transitions(state_machine)

`root@d9818d165dcf:/usr/src/app# ipython`

```python
from transitions import Machine
from application.lakshmi_api.models.usdt_deposit_order import UsdtDepositOrder

states = ['pending', 'submitted', 'failed', 'paid', 'revoked']
transitions = [
    {'trigger': 'process', 'source': 'pending', 'dest': 'submitted'},
    {'trigger': 'reject', 'source': 'pending', 'dest': 'failed'},
    {'trigger': 'approve', 'source': 'submitted', 'dest': 'paid'},
    {'trigger': 'failure', 'source': 'submitted', 'dest': 'failed'},
    {'trigger': 'refund', 'source': 'paid', 'dest': 'revoked'}]
order = UsdtDepositOrder()
machine = Machine(order, states=states, transitions=transitions, initial='pending')

order.state
order.process()
```

```python
from application.lakshmi_api.models import *
import global_resources
import logging
from redis import asyncio as aioredis
from config import get_config
from tornado_sqlalchemy import SQLAlchemy
conf = get_config()
logger = logging.getLogger()
redis = aioredis.from_url('redis://%s' % conf['redis_host'], encoding="utf-8", decode_responses=True)
global_resources.redis = redis
global_resources.logger = logger
db_orm = SQLAlchemy()
db_orm.configure(
    url=f"mysql+pymysql://{conf['mysql_user']}:{conf['mysql_password']}@{conf['mysql_host']}/{conf['mysql_database']}?charset=utf8",
    engine_options={
        "pool_size": 20,
        "max_overflow": 10,
        "echo": True
    }
)
global_resources.db_orm = db_orm

from sqlalchemy import and_, update, func, case, and_, text
from sqlalchemy.orm import joinedload
session = db_orm.sessionmaker()
```
