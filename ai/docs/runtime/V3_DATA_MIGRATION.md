# V3 持久化数据迁移

`scripts/migrate_runtime_data_v3.py` 是一次性离线迁移工具，不会在应用启动时执行。

迁移范围：

- `data/memory/memory.db`
  - `character_states.state_json`
  - `retrieval_audit.result_json`
  - `usage_events.context_json`
- `data/runtime/turns.db`
  - `turn_traces.detail_json`
- `data/memory/histories/hist_*.json` 原样归档到 `v2-archive`

结构化 JSON 中的 `tone` 和 `gesture` 键分别迁移为 `emotion` 和
`behavior`，自然语言字符串不做替换。迁移后的记录包含
`schemaVersion: 3`。`retrieval_audit.result_json` 的旧数组格式会升级为：

```json
{
  "schemaVersion": 3,
  "results": []
}
```

## 执行

先在应用停止前只读检查：

```powershell
python scripts/migrate_runtime_data_v3.py
```

确认 `validationErrors` 为空，停止 Electron 和所有服务后执行：

```powershell
python scripts/migrate_runtime_data_v3.py --apply
```

工具会先通过 SQLite Backup API 创建一致性快照，再在单个数据库事务内
修改原库并执行 `PRAGMA integrity_check`。备份及校验清单位于
`data/backups/v3-protocol/<UTC 时间>/`。再次执行是幂等操作。

## 2026-07-29 dry-run

- 待升级记录：583
- 待迁移旧字段键：622
- 待新增历史归档：0（已有归档与源文件校验一致）
- 校验错误：0

真实写入必须在桌面端和服务完全停止后执行，生成的数据库与备份属于
运行时用户数据，不进入 Git 提交。
