# Python 并行加速实战：从单线程到多核，再到 PyTorch 多卡

> 一个反直觉的开场：有人把脚本从 1 个线程改成 16 个，跑得更慢了；另一个人只改了 3 行代码，速度涨了 5 倍，而且一个线程都没加。

*工程 · 性能 · 2026 ｜ 更新于 2026-11-06 ｜ 阅读约 25 分钟 ｜ 全部代码本地实测 ｜ 附 3 个可运行文件*

覆盖：`ThreadPoolExecutor` · `ProcessPoolExecutor` · `asyncio` · `NumPy / Numba` · `Dask / Ray` · free-threading · PyTorch `AMP / DDP / FSDP2`

> **本文的核心判断**：并行加速的胜负手，从来不在「开了几个 worker」，而在**任务形状、瓶颈类型、以及你真正能用到的算力**。所有结论都配有可复现的实测数据；代码块与配套脚本一一对应，可直接下载运行。

---

## 一、先分清三件事

### 1.1 并发 ≠ 并行

- **并发（concurrency）**：多个任务在重叠的时间段里推进，重点是「别让 CPU 干等」。
- **并行（parallelism）**：多个任务在同一时刻真的同时执行，重点是「多核算力」。

I/O 密集型要的是并发，CPU 密集型要的是并行。把两者混为一谈，是 90% 失败改造的起点。

### 1.2 GIL 到底锁了什么

CPython 的 GIL 保证同一时刻只有一个线程执行 **Python 字节码**。但有两个关键例外：

- **阻塞 I/O**（`socket`、`time.sleep`、文件读写）会释放 GIL → 所以爬虫用线程池有效；
- **C 扩展里的计算**（NumPy、hashlib、压缩）通常也释放 GIL，而且本身就在 C 层跑 → 所以向量化往往比「多进程 + Python 循环」快一个数量级。

> [!TIP]
> **一句话判据**：你的时间花在「等」还是「算」？等 → 线程 / 协程；算 → 进程 / C 层 / JIT / GPU。

### 1.3 2026 年的 GIL 现状（别再背十年前的八股）

从 3.13 起，CPython 提供禁用 GIL 的 **free-threaded 构建**，让线程能在多核上真正并行；`sys._is_gil_enabled()` 与 `sysconfig.get_config_var("Py_GIL_DISABLED")` 可在运行时判断解释器状态。3.14 通过 PEP 779 把它从「实验性」升级为官方支持，重新启用自适应专用解释器后，单线程开销从 3.13 的 20–40% 收敛到约 5–10%，代价是内存多 15–20%。

但**默认构建依然带 GIL**，需要主动选 `python3.14t`；而且只要 import 一个没声明 `Py_mod_gil` 的 C 扩展，整个进程会**静默重新启用 GIL**——不报错、不警告，并行收益凭空消失。务必在**所有 import 之后**再检查状态，并可用 `-W default::RuntimeWarning` 观察重新启用提示。生态仍在追赶：截至 2026 年 9 月，PyPI 下载量前 360 的包里约一半提供自由线程轮子；把自由线程设为默认构建的第三阶段，目前仍没有确定时间表。

> [!WARNING]
> **务实结论**：今天写新代码，仍按「GIL 存在」设计——CPU 密集用进程或 C 层 / GPU，I/O 密集用 asyncio；把 free-threading 当作需要验证整条依赖链后才能启用的**部署选项**。I/O 密集型服务切到无 GIL 构建几乎没有收益，因为等待期间本来就不持有 GIL。

### 1.4 Amdahl 定律：先算上限，再写代码

$$
S = \frac{1}{(1-p) + \frac{p}{N}}
$$

其中 `p` 是可并行部分占比，`N` 是处理器数。`p=0.5` 时，就算有无限核，最多也只快 2 倍。所以第一步永远是 **profile**，而不是选框架：`cProfile` 找热点函数，`py-spy` 看线上壁钟时间，`line_profiler` 定位到行。优化掉一个 O(n²) 的查找，常常比上任何并行框架都有效。

---

## 二、方案全景与适用领域

| 方案 | 本质 | 适用领域 | 不适用 / 代价 |
|---|---|---|---|
| **ThreadPoolExecutor** | 线程并发，GIL 下交替执行 | I/O 密集：HTTP、DB、文件、同步 SDK | CPU 密集纯 Python 循环无效 |
| **asyncio** | 单线程事件循环 + 协作式调度 | 高并发 I/O：爬虫、WebSocket、API 网关 | 一个同步阻塞调用卡死整个循环 |
| **ProcessPoolExecutor** | 多进程，各自独立 GIL | CPU 密集纯 Python：解析、校验、加密、仿真 | 序列化 / 启动开销，内存翻倍 |
| **NumPy / Pandas 向量化** | 把循环推进 C 层 | 数值计算、数组变换、统计聚合（首选） | 算法难以表达成批量运算时 |
| Numba / Cython + OpenMP | JIT / 编译到机器码 + `prange` | 自定义数值内核、无法向量化的循环 | 首次编译耗时，Python 对象支持有限 |
| joblib `Parallel` | 封装进程/线程后端 + memmap | sklearn 调参、交叉验证、notebook 实验 | 通用工程不如 `concurrent.futures` 直观 |
| Dask / Ray | 任务图 + 分布式调度 | 超内存数据集、多机集群、超参搜索 | 单机小任务调度开销大于收益 |
| **PyTorch (AMP / DDP / FSDP2)** | GPU 算子并行 + 数据并行 + 参数分片 | 深度学习训练与推理 | 数据搬运、显存、NCCL 拓扑 |
| CuPy / JAX | GPU 大规模同构计算 | 矩阵运算、科学计算 | 显存与生态绑定 |
| `concurrent.interpreters`（3.14+） | 进程内多解释器隔离 | 跑不完全可信的代码、避免 IPC | 生态尚新，对象不能直接共享 |
| free-threaded 构建（3.14t） | 无 GIL 的线程真并行 | 内存敏感、需共享大对象的 CPU 负载 | 依赖链必须全适配，单线程略慢 |

### 2.1 选型决策树

📄 `decision_tree.txt`

```text
瓶颈是「等」还是「算」？
├─ 等（网络 / 磁盘 / DB）
│  ├─ 并发量 < 几百、生态是同步库 → ThreadPoolExecutor
│  └─ 并发量高 / 全链路可 async   → asyncio
└─ 算（CPU / GPU）
   ├─ 能写成数组运算吗？        → NumPy / Pandas 向量化 ★首选
   ├─ 是紧凑数值循环吗？        → Numba njit(parallel=True) / Cython+OpenMP
   ├─ 是纯 Python 逻辑、任务独立 → ProcessPoolExecutor（或 joblib）
   ├─ 是张量 / 神经网络计算     → GPU：AMP → DDP → FSDP2（见第七章）
   ├─ 数据超过内存 / 要跨机     → Dask / Ray
   └─ 依赖已全适配 + 想免掉 IPC → 3.14t 自由线程构建（先验证 GIL 状态）
```

---

## 三、把单线程代码改造成并行代码：七步最佳实践

**第 1 步 · Profile，不要猜**
`cProfile` 找热点 → 确认是 CPU 还是 I/O → 记录改造前的**壁钟时间**和**输出基准值**。没有基准，就没有「加速」这回事。

**第 2 步 · 确认你真的有多核算力**
`os.cpu_count()` 是「可见核数」，不是「可用核数」。容器 / K8s 里 `cpu.max`（cgroup v2）或 `cpu.cfs_quota_us`（v1）常把进程限制在 1 核，这时开 16 个进程只是把 1 核算力切得更碎。本文实测环境就踩了这个坑。

📄 `算力自检.py`

```python
def cpu_quota_cores():
    """容器里真正能用到的核数：K8s / Docker 的 CPU limit 常远小于 os.cpu_count()。"""
    try:
        parts = open("/sys/fs/cgroup/cpu.max", encoding="utf-8").read().split()
        if len(parts) >= 2 and parts[0] != "max":
            return float(parts[0]) / float(parts[1])          # cgroup v2
    except (OSError, ValueError):
        pass
    try:                                                       # cgroup v1
        q = float(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
        p = float(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
        return None if q < 0 else q / p
    except (OSError, ValueError):
        return None
```

**第 3 步 · 找出可独立切分的单元**
理想形状是 **map → reduce**：输入能分片，每片算出的部分结果可合并。改造前先审问三件事：有没有跨迭代状态（累加器、缓存字典、`counter += 1`）？有没有顺序依赖？有没有共享随机源 / 全局连接？对应做法：每片局部累加最后归约；串行段保留（它决定 Amdahl 上限）；每 worker 用 `default_rng(seed + task_id)`、每进程自建连接。

**第 4 步 · 按瓶颈选模型，不按「听起来快」选**
CPU 密集开线程池是经典反面教材；I/O 密集开进程池则白付序列化与内存。混合负载正确姿势是**分层**：事件循环管 I/O，进程池管 CPU。

**第 5 步 · 控制粒度与通信开销（最易忽略）**
片数 ≈ worker 数的 2～8 倍；用 `executor.map(..., chunksize=...)` 合批；**传索引 / 种子 / 文件路径，别传大对象**；共享大数组用 `shared_memory` / `memmap`；批量合并 I/O 通常比并发 1000 次小请求更快。

**第 6 步 · 让共享状态消失，而不是加锁**
优先不可变数据 + 局部状态。无 GIL 构建下更要重新审计：过去被 GIL「顺手兜住」的 `if not cache: cache = build()` 这类 check-then-act，现在会真实产生竞态。

**第 7 步 · 可观测、可回退、可校验**
`as_completed` + `future.result(timeout=...)`；并行版与串行版输出误差要在容差内；并发度做成配置项，留 `workers=1` 串行开关；压测看 **p99 尾延迟**而非只看平均值。

> [!TIP]
> **上线 Checklist**
> - [x] profile 过，知道瓶颈是 CPU 还是 I/O
> - [x] 查过 cgroup CPU 配额 / 可用 GPU 数
> - [x] 无共享可变状态，分片可归约
> - [x] 传给 worker 的是小参数（索引 / 路径 / seed）
> - [x] 有超时、异常传播与结果一致性校验
> - [x] 有串行回退开关，压测过 p99

---

## 四、实战 A：CPU 密集，逐版改造（附实测）

统一任务，保证「同一算法、只换执行方式」，对比才公平：对 N 个点求 `f(x) = Σ(k=1..40) sin(kx)·cos(x/(k+1))` 的总和，`N = 120000`。

### v1 · 单线程基线

📄 `v1_serial.py`

```python
import math

K = 40
N = 120_000
XS = [i * 0.001 for i in range(N)]

def f(x):
    s = 0.0
    for k in range(1, K + 1):
        s += math.sin(k * x) * math.cos(x / (k + 1))
    return s

def sum_chunk(xs):                 # 一个「可独立计算」的片 —— 全部改造的地基
    return sum(f(x) for x in xs)

baseline = sum_chunk(XS)           # 实测 0.714 s
```

**思路**：先把循环体抽成一个**纯函数** `sum_chunk(xs)`。这一步是全部改造的地基——如果代码是一坨带全局状态的大循环，任何并行框架都救不了。

### v2 · 线程池（反面教材）

📄 `v2_threads.py`

```python
from concurrent.futures import ThreadPoolExecutor

def chunks_of(seq, m):
    step = max(1, (len(seq) + m - 1) // m)
    return [seq[i:i + step] for i in range(0, len(seq), step)]

def v2_threads(workers=4):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return sum(ex.map(sum_chunk, chunks_of(XS, workers * 2)))
# 实测 0.754 s —— 比单线程还慢：GIL 下线程只是轮流跑字节码
```

实测 **0.754 s，比基线还慢 6%**。GIL 让 4 个线程轮流执行字节码，还额外付了线程切换与调度成本。**线程池不是加速 CPU 的工具**，它只是把「等待」重叠起来。

### v3 · 进程池（踩了序列化的坑）

📄 `v3_processes.py`

```python
import os
from concurrent.futures import ProcessPoolExecutor

def v3_processes(workers=None):
    workers = workers or os.cpu_count() or 2
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return sum(ex.map(sum_chunk, chunks_of(XS, workers * 4), chunksize=1))
# 实测 0.777 s：12 万个 float 被 pickle 给子进程 + 容器只有 1 核算力
```

实测 **0.777 s —— 依然没快**。两个原因叠加：每台子进程要 pickle 接收一大片 float 列表，12 万个浮点数的序列化吃掉了并行省下的时间；更致命的是本次环境 cgroup CPU 配额只有 **1.00 核**（虽然 `os.cpu_count()` 报 2 核），多进程根本无核可用，只剩启动开销。

> [!IMPORTANT]
> **生产最高频的隐形坑**：本地 8 核跑得飞快，上到 K8s `limits.cpu: "1"` 的 Pod 里反而更慢。改造前先看 `cpu.max` / GPU 可见性。

### v3b · 传索引，不传数据

📄 `v3b_indices.py`

```python
def sum_range(bounds):
    lo, hi = bounds
    return sum(f(i * 0.001) for i in range(lo, hi))   # worker 自己生成输入

def v3b_processes_indices(workers=None):
    workers = workers or os.cpu_count() or 2
    pieces = workers * 4
    step = (N + pieces - 1) // pieces
    bounds = [(i, min(i + step, N)) for i in range(0, N, step)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return sum(ex.map(sum_range, bounds, chunksize=1))
# 每个任务只传两个整数 —— 进程池的正确写法
```

每个任务只传两个整数，序列化成本趋近于零。**这才是进程池的正确写法**：数据大、任务多、核数足时，v3 与 v3b 的差距会随数据量线性放大。本环境 1 核配额下两者都淹没在噪声里，但原则不变。

### v4 · NumPy 向量化（真正的 5 倍）

📄 `v4_numpy.py`

```python
import numpy as np

def v4_numpy():
    x = np.asarray(XS, dtype=np.float64)      # 只转换一次
    s = np.zeros_like(x)
    for k in range(1, K + 1):
        s += np.sin(k * x) * np.cos(x / (k + 1))
    return float(s.sum())                    # 实测 0.139 s，5.1×
```

实测 **0.139 s，5.1×**。没开一个线程、一个进程，只是把 480 万次 Python 层函数调用搬进 C 层循环。**优先级永远高于并行框架**：先消掉 Python 循环，再谈分几片。

### v5 · Numba JIT + `prange`

📄 `v5_numba.py`

```python
from numba import njit, prange

@njit(parallel=True, fastmath=True)
def kernel(x):
    total = 0.0
    for i in prange(x.shape[0]):              # 自动多核并行 for
        xx = x[i]
        s = 0.0
        for k in range(1, 41):
            s += math.sin(k * xx) * math.cos(xx / (k + 1))
        total += s                           # Numba 自动处理归约
    return total

v5 = float(kernel(np.asarray(XS)))           # benchmark 前先预热，排除 JIT 编译
                                             # 实测 0.070 s，10.2×
```

实测 **0.070 s，10.2×**。编译成机器码 + 无 Python 对象开销 + 多核 `prange`。注意首次调用含 JIT 编译时间，benchmark 必须先预热。

### 4.1 实测汇总

环境：Python 3.10.12 / numpy 2.2.6 / numba 0.68.1 / 可见 2 核、**cgroup 配额 1.00 核** / N=120000。所有版本输出误差 < 1e-14，证明改造没改变语义。

| 版本 | 耗时 | 相对 v1 | 结论 |
|---|---|---|---|
| v1 单线程 | 0.714 s | 1.0× | 基线 |
| v2 线程池 4 worker | 0.754 s | 0.95× | GIL 下做 CPU 活，白干 |
| v3 进程池（传数据） | 0.777 s | 0.92× | 被 pickle + 1 核配额拖死 |
| v3b 进程池（传索引） | 0.815 s | 0.88× | 写法正确，但此环境无多核可吃 |
| **v4 NumPy 向量化** | **0.139 s** | **5.1×** | 把循环推进 C 层 |
| **v5 Numba prange** | **0.070 s** | **10.2×** | 编译 + 多核 |

> [!TIP]
> **这张表最该记住的是「层次」**：算法 / 数据结构层（v4/v5）拿到数量级收益；并行框架层（v3）最多 N 倍且要付通信税；调参（`workers` / `chunksize`）只影响最后 10%。在多核机器上执行 `DEMO_N=600000 python3 parallel_demo.py cpu`，会看到 v3b 接近核数倍的加速——demo 把规模做成环境变量正是为此。

---

## 五、实战 B：I/O 密集，并发才是解药

24 次「网络请求」，每次等待 50 ms（用 `time.sleep` 模拟，阻塞期间释放 GIL）：

📄 `io_concurrency.py`

```python
import asyncio, time
from concurrent.futures import ThreadPoolExecutor

IO_N, LATENCY = 24, 0.05

def request(i):
    time.sleep(LATENCY)          # 模拟网络往返；阻塞期间释放 GIL
    return i * i

# ① 串行                             → 1.223 s
def io_serial():
    return sum(request(i) for i in range(IO_N))

# ② 线程池：同步代码零改动           → 0.154 s（7.9×）
def io_threads(workers=8):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return sum(ex.map(request, range(IO_N)))

# ③ asyncio：单线程扛高并发          → 0.052 s（23.5×）
async def io_async():
    async def one(i):
        await asyncio.sleep(LATENCY)
        return i * i
    return sum(await asyncio.gather(*(one(i) for i in range(IO_N))))
```

| 方案 | 耗时 | 加速 |
|---|---|---|
| 串行 | 1.223 s | 1× |
| `ThreadPoolExecutor(8)` | 0.154 s | **7.9×** |
| `asyncio.gather` | 0.052 s | **23.5×** |

**思路**：线程 / 协程的收益来自「把等待时间重叠」，与 GIL 无关。同步遗留代码用线程池（改动最小）；新项目、高并发、全链路 async 用 asyncio。反面提醒：在 async 函数里直接调用同步阻塞函数会把整个事件循环卡住——必须 `await loop.run_in_executor(...)` 或换 async 客户端。

---

## 六、实战 C：混合管道（最常见的生产形态）

真实任务往往「下载 → 解析 → 重计算」混在一起。正确做法是**分层并行**，而不是给整个管道套一个池子：

📄 `hybrid_pipeline.py`

```python
async def pipeline(batch_ids, loop, pool):
    async def fetch(i):
        await asyncio.sleep(0.02)                  # 阶段 1：并发 I/O
        return [(i * 1000 + j) * 0.001 for j in range(2000)]

    raw = await asyncio.gather(*(fetch(i) for i in batch_ids))

    # 阶段 2：CPU 密集部分卸载到进程池，绝不 await 一个同步重函数
    pending = [loop.run_in_executor(pool, sum_chunk, part) for part in raw]
    return sum(await asyncio.gather(*pending))

# with ProcessPoolExecutor(...) as pool:
#     loop.run_until_complete(pipeline(range(8), loop, pool))
# 串行 0.264 s → 分层并行 0.081 s（3.26×）
```

实测串行管道 0.264 s → 分层并行 **0.081 s，3.26×**。三个要点：I/O 阶段用事件循环吃并发；CPU 阶段用进程池绕开 GIL；`run_in_executor` 是两者之间唯一的桥，且传进去的必须是可 pickle 的纯函数。

---

## 七、PyTorch 并行化专题：GPU、数据与分布式

> 深度学习里「并行」是分层的：CPU 把数据喂给 GPU、GPU 内部成千上万个核做算子级并行、多卡之间做数据并行、模型太大时再把参数切片。任何一层饿了，其他层都在空转。**优化顺序永远是：先让 GPU 吃饱，再让单卡算得快，最后才加卡。**

### 7.1 并行的四个层次

| 层次 | 关注点 | 做法 | 目标 |
|---|---|---|---|
| Layer 1 · 数据 | CPU → GPU 供给 | DataLoader 多进程预取、页锁定内存、异步 H2D 拷贝 | GPU 利用率 > 90% |
| Layer 2 · 单卡 | 算子与精度 | AMP 混合精度、Tensor Cores、channels_last、TF32、`torch.compile`、CUDA Graphs | 单步时间最短 |
| Layer 3 · 多卡 | 数据并行 | 每卡一个进程 + 完整模型副本，反向时 All-Reduce 同步梯度 | 近线性扩展吞吐 |
| Layer 4 · 大模型 | 参数分片 | FSDP2 切参数/梯度/优化器状态，再叠加张量并行、流水线并行 | 单卡放不下也能训 |

把前六章的通用原则搬过来，几乎逐条对应：`num_workers` 就是「把等待重叠」；AMP / `torch.compile` 就是「把循环推进 C 层」；DDP 的 All-Reduce 就是「map → reduce」；而 `DistributedSampler` 的 `set_epoch` 就是「别让共享状态产生隐式顺序依赖」。

### 7.2 先诊断：GPU 在摸鱼吗？

不要一上来就加卡。先用 `nvidia-smi dmon` 看利用率，再用 `torch.profiler` 看时间线——按 `cuda_time_total` 排序，若 `cpu_time_total` 远大于它，说明 GPU 在等 CPU。务必先 warmup 若干步，前几步的 cuDNN 自动调优和编译会污染 trace。

📄 `profile_step.py`

```python
from torch.profiler import profile, ProfilerActivity, schedule

with profile(
    activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
    schedule=schedule(wait=1, warmup=1, active=3, repeat=1),  # 先 warmup 再采
    on_trace_ready=torch.profiler.tensorboard_trace_handler("./prof_logs"),
    record_shapes=True, profile_memory=True,
) as prof:
    for step, (x, y) in enumerate(loader):
        if step >= 6:
            break
        train_step(x, y)
        prof.step()

print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=15))
# cpu_time_total 远大于 cuda_time_total → GPU 在等 CPU（数据或同步问题）
```

| ✕ 三类典型瓶颈 | ✓ 正确的观测姿势 |
|---|---|
| **输入饥饿**：GPU 利用率低但 CPU 忙 → 调 `num_workers` / `prefetch_factor`、换 NVMe、预解码 | 累计 loss 留在 GPU 上，每 100 步才 `.item()` 一次 |
| **同步阻塞**：每步 `loss.item()`、`.cpu()`、隐式同步 → 强制 CPU 等 GPU，流水线断裂 | `torch.backends.cudnn.benchmark=True` 仅在输入形状固定时开启 |
| **算子低效**：小 kernel 太多、形状不对齐 Tensor Cores → 混合精度 / 编译融合 | 记录 `torch.cuda.max_memory_allocated()`；`record_shapes=True` 抓意外变大的张量 |

### 7.3 数据管道最佳实践

📄 `build_loader.py`

```python
from torch.utils.data import DataLoader
from torch.utils.data.distributed import DistributedSampler

sampler = DistributedSampler(dataset, shuffle=True, drop_last=True) if ddp else None

loader = DataLoader(
    dataset,
    batch_size=64,                 # 尽量大到接近显存上限
    shuffle=(sampler is None),     # ⚠ 用了 DistributedSampler 就别再 shuffle
    sampler=sampler,
    num_workers=recommended_workers(),   # 按容器真实配额，而非 os.cpu_count()
    pin_memory=True,               # 页锁定内存：异步 H2D 的前提（仅 CUDA）
    persistent_workers=True,       # 省掉每 epoch 重建 worker
    prefetch_factor=2,             # GPU 仍饥饿时调到 4
    drop_last=True,                # 形状稳定 → compile / benchmark / CUDA Graphs 受益
)

for x, y in loader:
    x = x.to(device, non_blocking=True)                 # 与 pin_memory 配套
    x = x.to(memory_format=torch.channels_last)          # 卷积 + AMP 更快
    y = y.to(device, non_blocking=True)
```

| 参数 | 推荐值 | 为什么 | 坑 |
|---|---|---|---|
| **num_workers** | 可用 CPU 核的 1/2，约 1–8 | 读取 / 解码 / 增强与训练重叠 | 按 `os.cpu_count()` 设会超配额；Windows 必须 `if __name__ == "__main__"` |
| **pin_memory** | CUDA 时 True | 页锁定内存，异步 H2D 的前提 | 不开它，`non_blocking=True` 基本白设 |
| **non_blocking** | `.to(device, non_blocking=True)` | 主线程不等待拷贝完成 | 只有 pin_memory + 合适 stream 才能真正与计算重叠 |
| persistent_workers | True（`num_workers>0`） | 省掉每 epoch 重建 worker 的开销 | `num_workers=0` 时不可用 |
| prefetch_factor | 2–4 | 每个 worker 预取的 batch 数 | 太大吃内存，只在确实饥饿时调大 |
| drop_last / batch_size | 尽量大 + True | 形状稳定 → 编译 / benchmark / CUDA Graphs 都受益 | 梯度累积 ≠ 真大 batch（BN 统计仍按 micro-batch） |
| DistributedSampler | DDP 必配 | 每 rank 看不同数据，避免重复训练 | 配了 sampler 后 `shuffle` 必须 False；每 epoch 调 `set_epoch()` |

> [!WARNING]
> **与前文呼应**：第三章的 CPU 配额检查在这里同样适用，`num_workers` 的上限是容器真实配额，不是宿主机核数。配套脚本的 `--config-only` 会直接把推荐值算给你看（无需 torch / GPU）。

### 7.4 单卡计算：精度、内存布局与编译

#### ① AMP 混合精度（收益最大、改动最小）

📄 `amp_recipe.py`

```python
# 推荐：BF16（Ampere+）无需 GradScaler；FP16 必须配
amp_on = precision != "fp32"
amp_dtype = torch.bfloat16 if precision == "bf16" else torch.float16
scaler = torch.amp.GradScaler("cuda", enabled=(precision == "fp16"))

with torch.amp.autocast(device_type="cuda", dtype=amp_dtype, enabled=amp_on):
    loss = criterion(model(x), y)          # 只包 forward + loss，别把模型 .half()

scaler.scale(loss).backward()
scaler.unscale_(optimizer)                 # ⚠ 梯度裁剪必须放在 unscale_ 之后
torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
scaler.step(optimizer)                     # 出现 inf/NaN 时自动跳过本次 step
scaler.update()                            # 并缩小 scale
optimizer.zero_grad(set_to_none=True)      # 比 zero_grad() 少一次全量 memset
```

- **BF16 优先**（Ampere 及以上）：数值范围与 FP32 一致，通常**不需要 GradScaler**；FP16 必须配 `GradScaler`，否则小梯度下溢成 0。
- `autocast` 只包 forward + loss，**不要把整个模型 `.half()`**：权重主副本保持 FP32，省的主要是激活显存与矩阵乘时间。
- 梯度裁剪必须在 `scaler.unscale_(opt)` **之后**，否则裁剪的是被放大的梯度；`scaler.step` 会在出现 inf/NaN 时自动跳过本次更新并缩小 scale。
- 推理 / 验证用 `torch.inference_mode()`（比 `no_grad()` 更快），卷积 + AMP 时配合 `channels_last` 吃满 Tensor Cores。

#### ② 一个把要点串起来的训练步

📄 `train_one_epoch.py`

```python
def train_one_epoch(forward_model, optimizer, criterion, loader, scaler, cfg, sampler):
    sampler.set_epoch(epoch) if sampler is not None else None
    forward_model.train()
    optimizer.zero_grad(set_to_none=True)
    running = None                         # loss 留在 GPU 上累加，不每步 .item()

    for step, (x, y) in enumerate(loader):
        x = x.to(cfg.device, non_blocking=True)
        y = y.to(cfg.device, non_blocking=True)

        is_sync_step = (step + 1) % cfg.accum == 0
        ctx = (forward_model.no_sync()           # 累积步之间跳过 All-Reduce
               if ddp and not is_sync_step else contextlib.nullcontext())

        with ctx, torch.amp.autocast(device_type=cfg.device.type,
                                     dtype=amp_dtype, enabled=amp_on):
            loss = criterion(forward_model(x), y) / cfg.accum   # 按累积步数缩放

        scaler.scale(loss).backward() if use_scaler else loss.backward()
        running = loss.detach() if running is None else running + loss.detach()

        if is_sync_step:
            if use_scaler:
                scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(forward_model.parameters(), 1.0)
            if use_scaler:
                scaler.step(optimizer); scaler.update()
            else:
                optimizer.step()
            optimizer.zero_grad(set_to_none=True)

    return float(running.item())           # 整个 epoch 只同步一次
```

这一段同时做了五件事：异步搬运、AMP、梯度累积、DDP `no_sync()` 跳过中间步的 All-Reduce、以及避免每步 `.item()` 的隐式同步。完整可运行版本见配套脚本 `pytorch_parallel_demo.py`。

#### ③ 编译、TF32 与形状稳定

📄 `kernel_tuning.py`

```python
# 输入形状固定时才有收益
torch.backends.cudnn.benchmark = True
torch.backends.cuda.matmul.allow_tf32 = True      # FP32 matmul 透明加速
torch.backends.cudnn.allow_tf32 = True

model = model.to(device)
model = model.to(memory_format=torch.channels_last)  # NCHW → NHWC
model = torch.compile(model, mode="max-autotune")    # ⚠ 在 DDP/FSDP wrap 之后

# CUDA Graphs 仅适用于形状与控制流完全稳定、launch 开销占比高的场景
# static_inp.copy_(x) → graph.replay()，避免每步重新分配与下发 kernel
```

> [!TIP]
> **顺序与条件**：`torch.compile` 应在 DDP / FSDP 包装**之后**应用，并预留较长 warmup；DDP + compile 目前要求 `static_graph=False`。CUDA Graphs 只在形状与控制流完全稳定、且每步 launch 开销占比高时才值得上。TF32 适合对精度不敏感的 FP32 矩阵乘。

### 7.5 多卡：从 DP 到 DDP

| | `nn.DataParallel` (DP) | `DistributedDataParallel` (DDP) | FSDP2 (`fully_shard`) |
|---|---|---|---|
| 进程模型 | 单进程多线程，受 GIL 限制 | **多进程，每 GPU 一进程** | 多进程 + 参数分片 |
| 通信 | 主卡聚合梯度，主卡显存/带宽瓶颈 | Ring All-Reduce，与反向计算重叠 | All-Gather + Reduce-Scatter |
| 显存 | 不均衡 | 每卡完整副本 | **参数/梯度/优化器状态切片，最省** |
| 扩展 | 单机、已被淘汰 | 单机多卡 / 多机，**官方推荐默认** | 单卡放不下的大模型 |
| 启动 | 普通 python | `torchrun --nproc_per_node=N` | 同上 + `fully_shard` 包装 |

**结论：新项目直接上 DDP，别再用 DP。** 启动用 `torchrun`，它自动注入 `RANK / WORLD_SIZE / LOCAL_RANK` 并提供更健壮的容错；GPU 用 NCCL，CPU 调试用 GLOO。

📄 `launch.sh`

```bash
# 单机 4 卡：每卡一个进程，torchrun 自动注入 RANK / WORLD_SIZE / LOCAL_RANK
torchrun --standalone --nproc_per_node=4 pytorch_parallel_demo.py --ddp --epochs 10

# 多机：每台机器都执行（GPU 后端用 NCCL，CPU 调试用 GLOO）
torchrun --nnodes=2 --nproc_per_node=8 --rdzv_backend=c10d \
         --rdzv_endpoint=$MASTER_ADDR:29500 train.py --ddp

# 通用并行 demo 的实测
python3 parallel_demo.py
DEMO_N=600000 python3 parallel_demo.py cpu
python3 pytorch_parallel_demo.py --config-only      # 无 torch 也能看推荐配置
```

#### DDP 最小骨架

📄 `ddp_skeleton.py`

```python
import os, torch, torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler

def main():
    rank       = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    local_rank = int(os.environ["LOCAL_RANK"])
    dist.init_process_group("nccl")                  # CPU 调试换 "gloo"
    torch.cuda.set_device(local_rank)                # 别硬编码 cuda:0
    device = torch.device("cuda", local_rank)

    model = make_model().to(device)
    model = DDP(model, device_ids=[local_rank])      # 一进程一卡

    sampler = DistributedSampler(dataset, shuffle=True)
    loader  = DataLoader(dataset, batch_size=64, sampler=sampler,  # shuffle=False
                         num_workers=4, pin_memory=True)
    opt = torch.optim.AdamW(model.parameters(),
                            lr=3e-4 * world_size)     # 线性缩放 + warmup

    for epoch in range(EPOCHS):
        sampler.set_epoch(epoch)                     # 否则每 epoch 顺序相同
        train_one_epoch(model, opt, loader, device)

        if rank == 0:                                # 只由 rank0 落盘 / 打日志
            torch.save(model.module.state_dict(), "ckpt.pt")

    dist.destroy_process_group()

if __name__ == "__main__":                           # spawn / Windows 必需
    main()
```

> [!WARNING]
> **DDP 六条铁律**
> 1. 每 rank 一个进程，`torch.cuda.set_device(local_rank)`，别靠 `cuda:0` 硬编码；
> 2. `DistributedSampler` + 每个 epoch `sampler.set_epoch(epoch)`；配了 sampler 后 DataLoader 的 `shuffle=False`；
> 3. 有效 batch = 单卡 batch × 累积步数 × world_size，按线性缩放规则调学习率并 warmup；
> 4. 梯度累积的非同步步用 `model.no_sync()`，省掉重复 All-Reduce；
> 5. 只由 `rank == 0` 保存 checkpoint、打日志、做验证，避免多进程写同一文件；
> 6. 所有 rank 必须调用同样次数的集合通信，否则会 hang；设 `timeout` 便于排查 NCCL 问题。

### 7.6 模型放不下单卡：FSDP2 与 3D 并行

FSDP2（`fully_shard`）是当前官方 API，FSDP1 已弃用。它基于 DTensor 做逐参数 dim-0 分片：forward / backward 前按需 All-Gather 出完整参数，算完立刻释放，反向用 Reduce-Scatter 汇总分片梯度，优化器只更新自己那片 FP32 主权重。相当于把 DDP 的 All-Reduce 拆成「All-Gather + Reduce-Scatter」，用通信换显存。

📄 `fsdp2_recipe.py`

```python
from torch.distributed.fsdp import fully_shard, MixedPrecisionPolicy

mp = MixedPrecisionPolicy(
    param_dtype=torch.bfloat16,    # All-Gather 出来的计算副本用 BF16
    reduce_dtype=torch.float32,    # 梯度 Reduce-Scatter 保持 FP32 更稳
)

# ⚠ 自底向上：先包每个 transformer block，再包 root，才能重叠计算与通信
for block in model.layers:
    fully_shard(block, mp_policy=mp)
fully_shard(model, mp_policy=mp)   # root

opt = torch.optim.AdamW(model.parameters(), lr=1e-4)   # 必须在分片之后创建

# 梯度累积用 FSDP2 的机制，而不是 FSDP1 的 no_sync()
model.set_requires_gradient_sync(False)
for micro_step in range(ACCUM - 1):
    loss = criterion(model(x), y) / ACCUM
    loss.backward()                                    # 暂不通信
model.set_requires_gradient_sync(True)
loss = criterion(model(x), y) / ACCUM
loss.backward()                                        # 最后一步才同步
opt.step(); opt.zero_grad(set_to_none=True)
```

- **自底向上包装**：先对每个 transformer block 调 `fully_shard`，最后包 root；只包 root 会退化成一个巨大通信组，失去计算/通信重叠。
- FSDP2 的混合精度用 `MixedPrecisionPolicy(param_dtype=bf16, reduce_dtype=fp32)`，**不是** `GradScaler`；`reduce_dtype` 保持 FP32 更稳，除非实测通信是瓶颈。
- 梯度累积用 `set_requires_gradient_sync(False)`，不要沿用 FSDP1 的 `no_sync()`；梯度裁剪要用 DTensor 兼容的方式。
- 优化器**必须在分片之后创建**；大模型用 DCP 保存分片 checkpoint，而不是单卡 `torch.save`。
- 再往上：张量并行（层内切）、流水线并行（层间切）、以及 DeepSpeed ZeRO-1/2/3（配置驱动、支持 CPU/NVMe offload）——按「先 DDP，显存不够再 FSDP2，单机还不够再 3D」的顺序演进，别一步到位。

### 7.7 推理与 PyTorch 十大坑

📄 `inference.py`

```python
@torch.inference_mode()                 # 比 no_grad() 更快，推理专用
def predict_batched(model, batch):
    x = batch.to(device, non_blocking=True)
    with torch.amp.autocast("cuda", dtype=torch.bfloat16):
        return model(x).argmax(1)       # 尽量批量，别逐样本调用

# 只在边界同步一次：把结果留在 GPU 上聚合，最后再 .cpu()
# 反例：循环里 pred.item() / .cpu() → 每步强制同步，GPU 流水线断裂
```

1. **没 profile 就加卡**：80% 的「GPU 利用率低」其实是数据加载或 `.item()` 同步。
2. **pin_memory 与 non_blocking 只开一个**：两者是配套，缺一不可。
3. **num_workers 按宿主机核数设**：容器配额 1 核开 16 个 worker，只会更慢。
4. **把模型 `.half()` 当 AMP**：FP16 权重会让更新精度丢失；正确做法是 autocast + FP32 主权重。
5. **FP16 忘了 GradScaler / 裁剪忘了 unscale_**：前者 NaN，后者裁剪阈值失效。
6. **autocast 里手工创建的张量类型不一致**：FP32 mask 加到 BF16 激活会把结果提升回 FP32，显存悄悄翻倍。
7. **用 DP 而不是 DDP**：单进程多线程 + GIL + 主卡瓶颈，官方已不推荐。
8. **DDP 忘了 set_epoch / sampler 与 shuffle 同时开**：要么每 epoch 数据顺序一样，要么直接报错。
9. **每个 rank 都 save / log**：文件互相覆盖、日志刷屏、集合通信次数不一致导致 hang。
10. **cudnn.benchmark 用在动态形状上**：每次新形状都重新 autotune，反而抖动；形状固定才开。

另外别忘了 PyTorch 自己也是「多线程程序」：DataLoader worker、NCCL 线程、BLAS/OMP 线程、DDP reducer 线程叠加在一起，容易 oversubscription。容器里显式设 `OMP_NUM_THREADS`，并把 `num_workers` 与 BLAS 线程数一起纳入算力预算。

> [!TIP]
> **PyTorch 速查表**：单卡 AMP(BF16) → channels_last → compile → 固定形状 CUDA Graphs｜数据 `num_workers ≈ 可用核/2` + pin_memory + non_blocking｜多卡 DDP + torchrun + NCCL｜放不下 FSDP2 自底向上分片｜推理 inference_mode + 批处理 + 只在边界同步。

---

## 八、通用高频坑（跨方案）

1. **CPU 密集用线程池**：GIL 下等于串行 + 切换开销（见 v2）。
2. **不看容器 CPU 配额**：`os.cpu_count()` ≠ 可用核数。
3. **把大对象 pickle 给子进程**：传索引 / 路径 / memmap，别传百万级 list。
4. **任务切得太碎**：每任务只算 1 ms，调度比计算还贵；用 `chunksize` 合批。
5. **嵌套并行 / oversubscription**：进程池里再开 Numba `prange` 或 BLAS 多线程；设 `OMP_NUM_THREADS=1`。
6. **共享可变状态**：改成局部状态 + 最终归约。
7. **随机数不可复现**：每片用 `default_rng(seed + task_id)`。
8. **忘了 `if __name__ == "__main__":`**：spawn 平台上无限递归创建子进程。
9. **吞掉异常**：`executor.map` 的异常在取结果时才抛；用 `as_completed` + `result(timeout=...)`。
10. **只测平均值**：并行常让 p99 变糟；保留 `workers=1` 串行回退开关。

关于自由线程构建再补一条：迁移时别只测纯 Python 算力。`python3.14t` 下 import 任一未适配的 C 扩展都会**静默把 GIL 打开**，基准跑得漂亮、一上生产就打回原形；在所有依赖 import 之后检查 `sys._is_gil_enabled()`。

---

## 九、速查表与小结

| 你的情况 | 直接这么干 |
|---|---|
| 循环里做数值运算 | 先 NumPy 向量化；不行再 Numba `prange` |
| 纯 Python 逻辑、任务独立 | `ProcessPoolExecutor` + 传索引 + 结果归约 |
| 一堆 HTTP / DB 调用，同步 SDK | `ThreadPoolExecutor` |
| 高并发网络服务 | `asyncio` + async 客户端 |
| 下载 + 重计算混合 | `asyncio` + `run_in_executor(进程池)` |
| 数据超内存 / 要跨机 | Dask / Ray |
| 张量 / 神经网络，单卡 | AMP(BF16) + channels_last + compile + 喂饱 DataLoader |
| 张量 / 神经网络，多卡 | DDP + torchrun + NCCL；放不下再 FSDP2 |
| 依赖已全适配、被多进程内存拖累 | 3.14t 自由线程构建，先验证 GIL 状态 |

**一句话方法论**：先 profile 找瓶颈 → 确认算力上限 → 把代码整理成「纯函数 + 可分片 + 可归约」的形状 → 优先消掉 Python 层循环 → 再按瓶颈选并发模型 → 最后用真实数据验证加速比与输出一致性。并行不是给程序「加几个 worker」，而是先把程序**整理成值得并行的样子**。改造成功的标志，往往是你为了并行而做的那次函数拆分和状态清理，本身就让串行版也变快了。

---

## 延伸阅读 / 官方文档

- [Python 官方文档 · 对自由线程的支持（PEP 703 / 3.13+）](https://docs.python.org/zh-cn/3/howto/free-threading-python.html)
- [Python 官方文档 · concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html)
- [PyTorch · Performance Tuning Guide](https://pytorch.org/tutorials/recipes/recipes/tuning_guide.html)
- [PyTorch · Getting Started with FSDP2](https://pytorch.org/tutorials/intermediate/FSDP_tutorial.html)
- [PyTorch · Automatic Mixed Precision 示例](https://pytorch.org/docs/stable/notes/amp_examples.html)
- [PyTorch · DistributedDataParallel API](https://pytorch.org/docs/stable/generated/torch.nn.parallel.DistributedDataParallel.html)
- [PyTorch · pin_memory 与 non_blocking 使用指南](https://pytorch.org/tutorials/intermediate/pinmem_nonblock.html)
