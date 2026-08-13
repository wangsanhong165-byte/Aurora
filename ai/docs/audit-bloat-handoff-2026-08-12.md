# 体积/残余代码全面审查 — 移交材料(给 Codex)

> 日期: 2026-08-12
> 目的: 记录全项目体积臃肿与残余代码审查结果，供 Codex 接手清理。**本文件自包含，不依赖会话上下文。**
> 方法: 7 维度并行审查(磁盘/后端/前端/测试/配置/历史/运维)+ 9 条 P0/P1 对抗性验证。共 76 条发现，8 条高优先确认、1 条被证伪(见 §4.0)。
> 基线: 全程只读，**未修改任何文件、未执行 gc、未改 .gitignore**。当前工作区有大量未提交改动(Live2D framework 半提交状态)，清理前必须先提交。

---

## 一、项目现状速查

| 项 | 数值 | 说明 |
|---|---|---|
| 仓库根 | `C:\Users\LENOVO\Desktop\c++`(父目录) | **ai 只是子目录**，`.git` 在父目录，含 3 个无关子项目 |
| git 跟踪 | 871 文件(ai) + 220(Open-LLM-VTuber-1.2.1) + 43(git/) | 父 `.gitignore` 只排除 ccx/code/dev c++/python |
| 磁盘 | ~20GB | models 19GB + config 542M + frontend 581M + 其余 ~30M |
| `.git` pack | 665MB | 其中 ~537MB 可安全回收(见 §2.5) |
| 代码量 | 后端 app/ 197 py / 21,343 行 | 前端真实代码 ~20.6K 行(TS+CSS+cjs) |
| 前端厂商代码 | live2d/framework 23,881 行 + **WebSDK 死拷贝 22,413 行** | 死拷贝全仓库零引用 |
| 提交 | 156 个，全在 2026 | 历史上有 427 个文件被删(79.9MB)，经历 3 次整系统重写 |

---

## 二、P0/P1 — 优先处理(均已对抗性验证，标注 verified)

### 2.1 🔴 P0 安全：DeepSeek API 密钥已泄露并推送到 GitHub — verified
- **位置**: `git/.env`(父目录 c++/ 下，V1.1 旧项目的 43 个文件之一)。`DEEPSEEK_API_KEY=sk-f799...(35 字符，真实密钥)`，键值已打码。
- **事实**: 该文件在 commit `fc1eb3d`("v1.1-final" 2026-06-04)入库，**已随 origin/v1.1-final 推送到 GitHub**(`wangsanhong165-byte/peibanxingai`，14 个远程分支包含该 commit，远程跟踪 ref 直接可读出密钥)。当前 `ai/.env`、`ai/config/.env` 均正确忽略，泄露只来自这个旧原型。
- **处理**: ① **立即在 DeepSeek 后台 rotate/revoke 该密钥**；② 从跟踪移除 `git/.env`(git rm --cached)；③ 从 GitHub 历史清除需历史重写(filter-repo --path git/.env + force-push)，**与仓库拆分(§2.10)一起做**，不要零敲碎打。
- **风险**: 不 rotate 则密钥在公开/私有仓库历史中持续可用。origin/main 的树已无该文件，但历史与远程分支仍在。

### 2.2 🔴 前端运行时资产未入库 → 全新克隆运行时挂掉 — verified(P1)
- **位置**: `frontend/public/libs/live2dcore-compat.js`(1.7KB，未跟踪 `??`)；`frontend/public/Framework/Shaders/WebGL/` 13 个 .frag/.vert(未跟踪 `??`)。
- **事实**: index.html 第 11 行加载 compat shim(模块加载期必需)；[cubismshader_webgl.ts:213](frontend/src/character/live2d/framework/rendering/cubismshader_webgl.ts:213) fetch `'../../Framework/Shaders/WebGL/'` 解析到 `/Framework/Shaders/WebGL/`(dev 走 public/，build 复制进 dist/)。**fresh clone 后 compat 缺失 → 枚举解析失败；shader 缺失 → 404**。
- **处理**: 提交 `frontend/public/libs/live2dcore-compat.js` 与 `frontend/public/Framework/Shaders/WebGL/*`。空目录 `frontend/public/Framework/` 其余部分无需跟踪。
- **验证备注**: shader 相对路径本身解析正确(经 HTTP document root)，dist 已含复制产物，只是源码未入库。

### 2.3 🔴 5 个 Live2D 自定义框架文件未跟踪 → 全新克隆构建失败 — verified(P1)
- **位置**: `frontend/src/character/live2d/framework/` 处于**半提交状态**(46 跟踪 + 55 修改 + 16 未跟踪)。
- **5 个必需未跟踪文件**(被活代码 import，缺失即 vite/tsc 构建失败):
  - `cubismmodelmultiplyandscreencolor.ts`(被 model/cubismmodel.ts import)
  - `cubismarrayutils.ts`(被 cubismmotion/cubismphysics/cubismoffscreenmanager/cubismrenderer_webgl import)
  - `cubismoffscreenmanager.ts`、`cubismoffscreenrendertarget_webgl.ts`、`cubismrendertarget_webgl.ts`(被 rendering/cubismrenderer_webgl.ts import)
- **另有 11 个未跟踪文件是死代码，应删不应提交**: `cubismlook`、8 个 `cubism*updater`、`icubismupdater`、`iparameterprovider`。
- **处理**: 一次性提交当前 framework 全量(让磁盘状态可复现)，**同时删掉那 11 个死文件**。目录内加 vendoring 说明(该目录是 WebSDK/Framework 的深度修改 fork)。

### 2.4 🔴 默认角色 alice 的角色卡完全未跟踪 — verified(P1)
- **位置**: [config/characters/index.yaml](config/characters/index.yaml) 提交了 `characters:[monika, alice]` + `default: alice`；但 `config/characters/alice/`(character.json 10.7KB + pinned.md)是 `??` 未跟踪。
- **事实**: [app/character/registry.py:42-49](app/character/registry.py) `_scan` 只加载磁盘存在的卡，default 落空时**静默回退到 monika**——新环境启动后默认角色与提交的 index.yaml 不符，且 alice 人设不在版本控制内，有丢失风险。历史：alice 卡曾在 e9c1b81 提交、ee6c85c 删除时 index.yaml 未同步。
- **处理**: 把 `config/characters/alice/` 纳入版本控制；并加一致性检查(index.yaml 每个 id 必须在 config/characters/ 有已提交的 character.json)。

### 2.5 🟠 git 历史 537MB 可安全回收(reflog 悬挂，非改写) — verified(P1)
- **位置**: `.git` 在 `C:\Users\LENOVO\Desktop\c++\.git`，4 个 pack，pack-c75affb6 617MB。
- **事实**: 3 个巨大 blob(Monika.char 260.1MB + Monika-e15.ckpt 148.1MB + Monika_e8_s224.pth 128.7MB = ~537MB)曾在 v2.0 分支(commit 4c2ca6c)提交后 amend/reset 悬空，现**仅被 reflog(115 条)钉住**。`git fsck --unreachable` 看不到它们(默认 reflog-aware)，`git gc` 默认 keep-unreachable 也不会回收，**所以它们一直占着**。git hash-object 已确认三者与当前磁盘的 Monika.char / 两个语音权重逐字节一致。当前 refs 与工作树不含它们。reachable 唯一 blob 仅 ~148MB。
- **处理**(在仓库根执行，安全、不触碰任何 refs)：
  ```
  git reflog expire --expire=now --all && git gc --prune=now
  ```
  `.git` 从 667MB → ~130MB。
- **验证冲突澄清**: git 维度有一条 "89% 不可达垃圾" 被证伪——它声称 blob "不在任何 commit/tag/reflog"。**实情是它们在 reflog 里**，所以普通 `git gc` 不回收；但上面的 `reflog expire + gc --prune=now` 组合**确实可以回收**。结论一致：537MB 可安全释放，只是必须先 expire reflog。

### 2.6 🟠 Monika 自定义语音权重双份(277MB 字节级相同) — verified(P1)
- **位置**: `config/voices/monika/{Monika-e15.ckpt, Monika_e8_s224.pth, monika_voice.flac_...wav}` 与 `models/tts/GPT-SoVITS-v2pro-20250604-nvidia50/{GPT,SoVITS}_weights_v2Pro/Monika/` 同款文件 **逐字节相同(cmp 验证，合计 ~277MB)**。
- **双源引用**: `tts_infer.yaml:6,8` 硬编码绝对路径到 `config/voices/monika/`；[run.py:234-237](run.py) 设 `GSVI_GPT_WEIGHTS/GSVI_SOVITS_WEIGHTS` 相对 GSVI 目录指向包内副本(被 `app/modules/tts/engines/gsvi_v2.py:124-125` 消费)。两套机制都活着，改任一目录就有一边失效。另 `config/characters/monika/voice/` 是第三个空目录。
- **处理**: 以 `config/voices/monika` 为唯一规范源，删除包内副本，统一引用(改 tts_infer.yaml 或 run.py 其一)。**先改配置再删，避免 TTS 断裂**。

### 2.7 🟠 TTS 模型目录 14.6GB 中仅 277MB 不可再生 — verified(P1)
- **位置**: `models/tts/GPT-SoVITS-v2pro-20250604-nvidia50`(59,340 文件)。构成：runtime/ 7,483MB(python venv)+ GPT_SoVITS/ 4,929MB(源码 750MB + pretrained_models 4,177MB)+ tools/ 1,966MB(asr/uvr5，仅数据集预处理用)+ TEMP/ 9MB。
- **不可再生**: 只有 `GPT_weights_v2Pro/Monika` 148.5MB + `SoVITS_weights_v2Pro/Monika` 128.7MB = **277MB 自定义语音**。其余全是开源 GPT-SoVITS 发行包/公开权重/venv，可重新下载。
- **处理**: ① 保守：删未用版本权重(gsv-v4-pretrained 788MB、s2Gv3.pth 733MB、gsv-v2final 338MB、s1bert25hz 148MB、s2D/s2G 190MB、sv 102MB ≈ 2.3GB)；② 激进：整体删除，用原始发行包重建(需网络+脚本，runtime/ 由 GSVI_PYTHON 直接调用，**删除会断 TTS**)。
- **验证更正**: 审查初判 sv/(102MB) 未用，实际 TTS.py:497/1264 在 v2Pro 推理时加载它，属运行时足迹(仍可重下)。

### 2.8 🟠 本地 llm 模块服务是僵尸进程 — verified(P1)
- **位置**: [config/services.json:44-49](config/services.json) 声明 llm 服务(端口 19202，command `app.modules.llm.api`)，是 text capability 的 `required_services`(未就绪则 FULL_READY 降级，[manifest.py:184-207](app/lifecycle/manifest.py))。**但运行时 LLM 路径完全绕过它**：[runtime.py:157](app/runtime/runtime.py) → `providers['llm']` → OpenAILLMProvider → [http_adapters.py:112](app/models/http_adapters.py) `OpenAILLMAdapter` 直连 `api.deepseek.com`。全仓 grep `/v1/llm`、`19202`、`LLM_URL` 无生产调用方。[app/modules/llm/api.py:104-170](app/modules/llm/api.py) 的 `call_cloud_llm/_stream_tokens` 是 OpenAILLMAdapter 的重复实现。
- **影响**: 每次启动多一个占端口的 uvicorn 进程，其失败会拖累 text capability 就绪门；两份云直连代码会漂移。
- **处理**: 二选一：① 从 services.json 移除 llm 服务 + 删 `app/modules/llm/`(推荐)；② 把 OpenAILLMAdapter 改为经该服务转发。README/ARCHITECTURE 的 19202 行同步更新。

### 2.9 🟠 文档与实现脱节 — verified(P1)
- **`--ui` TUI 模式不存在**: [README.md:78](README.md) 与 [run.py:6](run.py) docstring 都声称 `python run.py --ui tui`，但 parse_args() 只有 `--env-file/--seconds/--sample-rate/--language/--no-tts/--no-vad/--persona/--text/--audio-path/--runtime/--web`，**无 `--ui`**。实测 argparse 报 "unrecognized arguments: --ui tui" exit 2。→ 删 docstring 该行 + README 移除该命令(或补实现)。
- **`.env.example` 不存在**: README.md:59-63 让用户复制 `.env.example`，根目录无此文件；实际配置在 `config/.env`(DEFAULT_ENV_PATH)。README:141 项目树把 `.env` 列在根目录也是错的。→ README 改为指向 `config/.env` 并给模板。

### 2.10 🟠 仓库边界决策：ai 应独立成单仓库 — verified(P2，战略)
- **事实**: 整个有价值的源码历史只有 **1.77MB**；pack 里 99.7% 是包袱/垃圾。当前 HEAD 树 27.6MB 中 `Open-LLM-VTuber-1.2.1`(220 文件，第三方参考项目，单次提交从未改)占 **57%**。另 `git/`(43 文件)是 V1.1 被 ai/ 取代的 Textual-TUI 原型(含泄露密钥 + last_recording.wav)。
- **处理**: fresh repo 从当前 ai/ HEAD 文件初始化约 2-11MB，一举解决：无关子项目、密钥泄露、591MB 孤儿对象(新仓库根本不引入)、24 个 git-add 引号 bug 畸形路径(如 `"ai/live2d-models/...`、`"ppt/...`)。
- **注意**: 拆分前先删除 `ai/.git` 空目录(失败/废弃的 init 残留，`ls -la ai/.git` 确认只有 . 和 ..)；Open-LLM-VTuber-1.2.1 移到 gitignored 兄弟路径；交叉引用(docs 引用 ppt 章节等)需复核。

---

## 三、P2 — 死代码/重复/残留清理清单

### 前端
| 项 | 位置 | 证据 | 处理 |
|---|---|---|---|
| WebSDK 死拷贝 | `frontend/WebSDK/`(82 文件，22,413 行 TS) | 全仓库 grep "WebSDK" 零命中 | 删除整目录；若需类型保留 `WebSDK/Core/live2dcubismcore.d.ts` |
| 死二进制被跟踪 | `frontend/libs/`(4 个 ort-wasm ~38MB + 2 个 silero_vad onnx ~4MB + live2d.min.js 等) | 已被 `public/libs` 取代，Web VAD/onnx 管线已废弃，全仓零引用仍被 git 跟踪 | `git rm --cached frontend/libs/*` + 删除；省 ~42MB 且减 pack |
| framework 死模块 | `src/character/live2d/framework/` 内 21 个文件 ~3,929 行 | import 图不可达(cubismmodelsettingjson、cubismusermodel、csmvector/csmmap/cubismstring、8 个 cubism*updater 等) | 删除(注意与 §2.3 的 5 个必需未跟踪文件区分) |
| core 重复 | `live2dcubismcore.min.js` 3 份(public/libs、frontend/libs、WebSDK/Core)MD5 相同 | §2.2 + 本节删除后收敛 | 只留 public/libs 一份 |

### 后端
| 项 | 位置 | 证据 | 处理 |
|---|---|---|---|
| 13 个孤儿模块 | `app/tts/`(222行)、`app/utils/`(124行)、`app/project/`(65行)、`app/input/recorder.py`+`interrupt.py`、`app/telemetry/events.py`、`app/core/logging_config.py`(129)、`app/modules/sentence_divider.py`、`app/transport/v3_handler.py`(25) 等 | 静态 import 图 + grep 交叉验证，从任何入口不可达 | 删除(删前确认无历史引用) |
| 死 prompt 模板 | `app/prompts/utils/*.txt` 7 个(identity_ishiki、character_setting、role_setting、output_format、thought_protocol、pinned_memories、available_emotions) | loader 的 render()/render_optional() 全仓无调用，生产提示词来自 app/runtime/prompts.py + data/prompts/*.json | 删除 7 个 .txt 及 render/reload 死钩子 |
| 死常量 | `app/core/config.py` 的 `GSVI_HEADLESS`(:23，指向已删文件)、`DEFAULT_AUDIO_PATH`(:9)、`DEFAULT_TTS_OUTPUT_DIR`(:58) | 指向不存在的目录/文件，无消费方 | 删除常量；顺带清 .gitignore 的 temp_audio/、tts_outputs/ 死条目 |
| legacy 命名误导 | `app/legacy/` | **不是死代码**：LegacyToolProvider 是 ToolInterface 默认实现，screen_capture/get_time 是生产内置工具 | 改名 `app/tools`，更新包注释 |
| pyc 残留 | `app/providers/live2d/` 整目录仅剩 __pycache__；13 个无源 .pyc；空目录 `app/{agent,initiative,screen}`、`app/modules/live2d` | 源文件已删，磁盘残留 312/313/314 三版字节码 | 删除 + 常规清扫 |

### 配置/数据/文档
| 项 | 位置 | 处理 |
|---|---|---|
| v2 画像死资产 | `config/characters/monika/portrait/` 36 张中文名 webp(4.1MB)被跟踪 | 已无 sprites 消费方(registry 仅触发于 emotion_words 键，当前卡无) → `git rm --cached` + ignore |
| 运行时数据入库 | `data/backups/v3-protocol/*.db`(3.2MB)、`data/memory/*.jsonl`(含完整对话转写)、`recordings/latest.wav` | `git rm --cached`；.gitignore 加 `data/backups/`、`data/memory/*.jsonl`(对话记录不该进版本控制) |
| 死 prompt 存储 | `data/prompts/monika.md` 空文件被跟踪 | 已被 PromptConfigStore 的 monika.json 取代 → 删除 |
| 空目录残留 | `config/characters/monika/voice/` | V2 嵌入式声线布局残留 → 删除 |
| 声线包部分入库 | `config/voices/monika/voice.json`+ref wav 提交，但 290MB gpt/vits 权重被 ignore | 克隆无法复现 Monika 声线 → README 标注手动放置或加安装脚本 |
| 规划文档状态 | `docs/superpowers/plans` 16 份 + specs 9 份，多数无完成标记 | 抽查全部已落地 → 补"已完成"头或移入 docs/archive/ |
| 协议类型双镜像 | 前端 `src/runtime/event-types.ts` 硬编码镜像后端 50 个事件 | 当前一致但无同步校验 → 加测试断言 schema 与 TS 类型一致 |

### 测试/运维
| 项 | 位置 | 处理 |
|---|---|---|
| pytest 残留 | `_codex_tmp/final-live2d/` 8 个 tmp_path 目录 | 删除；gitignore 放宽为 `ai/_codex_tmp/`；pytest.ini norecursedirs 补 `_codex_tmp` |
| fixture 复制粘贴 | tests 无 conftest.py，`_MockLLM`×3、`tmp_compiler`×2、`_days_ago`×2、`_make_store`×2、`_FACT_JSON`×2 | 建 tests/conftest.py 集中定义 |
| 测试隔离风险 | `test_production_regressions.py:28-30` import 期无条件 os.chdir 到项目根 | chdir 移入 setUpClass 内 + monkeypatch |
| 测试 pyc | `tests/__pycache__` 3MB，含 3 个已删测试模块字节码 | 删除 |
| skills 双份 | `.claude/skills`(82) 与 `.agents/skills`(83) 逐字节相同 | 确立单一源(.claude)，另一处软链/同步，或至少在 AGENTS.md 说明分工 |
| uv 缓存混乱 | `.uv_cache`(191MB 活动) + `.uv-cache`/`.uv-python`(陈旧，且**未进 .gitignore**) | 删 `.uv-cache`/`.uv-python`；统一目录名；gitignore 补齐 |
| soulctl 死分支 | [soulctl.cjs:283](scripts/soulctl.cjs) `command === 'web' ? 'backend' : 'backend'` 恒真 | 改为 `'web' ? 'web' : 'backend'` 或直接 `'backend'` |
| dist 指纹缺失 | frontend/dist 无 `.build-manifest.json` | 每次 `soulctl.cmd electron/web` 都全量 rebuild → 补指纹文件 |
| Electron 拆分 | 根 `electron/` 3 文件 + `frontend/electron/` 13 文件，跨级 require | 归并到 frontend/electron/ |
| `.agent-runs` 残留 | 5.3MB pi.jsonl + does-not-exist.* 失败产物；tasks/ 被跟踪 | 删残留；tasks 移出跟踪 + ignore |
| 日志不轮转 | `logs/supervisor-bootstrap.log` 48KB 追加式；内容显示 **ASR 反复启动失败被 isolate** | 排查 ASR 启动根因(对照 runtime.local.json 的 D:\conda\envs)；日志轮转 |
| 空残留目录 | `frontend/src_backup_20260727_035125`(60K 空壳)、根 `__pycache__`、`data/pids/*.lock`、`frontend/console.log`、根 `.pytest_cache`、`ai/.git` | 全删 |
| 语音权重双源 | `tts_infer.yaml` 绝对路径 vs run.py 相对路径 | 随 §2.6 统一 |
| 死视图/协调器 | `src/character/live2d/viewport.ts` 与 `ModelLoadCoordinator.ts` 仅被测试 import | 移入测试或删除 |

---

## 四、已证伪 / 不要做的(避免误改)

### 4.0 被对抗性验证驳回的发现(1 条)
- "89% of pack 是不可达垃圾，可在不写历史的情况下 prune" —— **部分证伪**：那 3 个 516MB blob **在 reflog 里**(commit 4c2ca6c，refs/heads/2.0)，普通 `git gc` **不会**回收。正确做法见 §2.5(reflog expire + gc --prune=now)。"不触碰任何 refs 即可回收"这个结论仍然成立，只是必须先 expire reflog。

### 4.1 已验证健康、不要动的(防止误清理)
- **`app/modules/{tts,asr}` 与 `app/providers/{tts,asr}` 是服务端/进程内客户端两层**，不是新旧两套。删任一侧会切断 TTS/ASR。仅 llm 例外(§2.8 僵尸)。
- **`app/legacy/` 是活代码**——LegacyToolProvider 已注册为 ToolInterface 默认实现。
- **`app/core/state_store.py` 与 `app/runtime/state_store.py` 是文档化兼容 re-export**，不算重复。
- **shader 相对路径解析正确**；`frontend/dist` 与源码同步(2026-08-12 18:59 构建)；package.json 无多余依赖；vite 配置最小；ui/session/audio/runtime/conversation/core 无孤儿。
- **config 侧健康**：5 个 `avatar_profiles/*.json` 与 `models/live2d-models/` 5 个目录一一对应。
- **`models/asr`(4.4GB) 与 `models/live2d-models`(96.5MB) 是运行时必需**，可重下但删除期间对应能力不可用。

---

## 五、建议执行顺序(给 Codex)

**阶段 0 — 提交当前工作区**(前置，防丢失)：`config/characters/alice/`、`frontend/public/libs/live2dcore-compat.js`、`frontend/public/Framework/Shaders/`、`frontend/electron/wallpaper-dialog.cjs`、`frontend/src/ui/StageBackground.tsx`、framework 5 个必需未跟踪文件 + 55 个修改 + 删 11 个死文件、`app/legacy` 改名(§3)。**这是最高风险未决项**——当前磁盘状态无法从 git 复现。

**阶段 1 — 安全(用户可立即自己做)**：rotate DeepSeek 密钥(§2.1) + 仓库根 `git reflog expire --expire=now --all && git gc --prune=now`(§2.5，省 537MB)。

**阶段 2 — 一致性修复**：alice 卡入库(§2.4)、文档修正(§2.9)、llm 僵尸服务处置(§2.8)、README 声线权重标注(§3 config 表)。

**阶段 3 — 去重去死**：WebSDK 删除 + frontend/libs 出库(§3 前端)、277MB 语音权重单源化(§2.6)、TTS 未用版本权重(§2.7)、后端 13 孤儿模块 + 7 死 prompt(§3 后端)、v2 画像资产出库(§3 config 表)。

**阶段 4 — 战略决策**：ai 单仓库拆分(§2.10)，连带密钥历史清除。

**阶段 5 — 卫生**：全部 P2/P3 残留目录、缓存、日志、skills 双份、测试夹具收敛。

---

## 六、关键命令速查(全部只读或安全)

```bash
# 仓库根
cd /c/Users/LENOVO/Desktop/c++
# 看历史大 blob(不修改)
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | sort -rn | head -20
# 安全回收 537MB(§2.5)——执行前确认无未保存工作，reflog 过期不可逆
git reflog expire --expire=now --all && git gc --prune=now
# 查看被跟踪的大二进制
git ls-files | grep -E '\.(wasm|onnx|db|ckpt|pth|wav|webp|png)$'
# 运行时数据误提交检查
git ls-files data/ recordings/
```

---

## 七、边界与约束

- 本项目实际由 Codex 主导开发(DeepSeek 后端)，有 Pi 委派链(AGENTS.md)。本材料是**清理任务的输入**，不是执行指令——Codex 应自己复核每个 file:line 再动手。
- 历史重写(filter-repo)、force-push、删除生产数据等**破坏性操作**需用户明确授权。
- 所有"已验证"标记的发现均有第 2 层对抗性验证背书；其余为单层审查，置信度已在各表标注。
- **敏感信息**：本文件不包含完整密钥值。`git/.env` 的 DEEPSEEK_API_KEY 需用户手动 rotate。
