# Refactor Freeze Toolchain

这套工具只负责：

- 生成 phase baseline 快照
- 生成 phase candidate 快照
- 按白名单归一化后输出 `diff_report.json`
- 在未批准 diff 或缺失 snapshot 时触发 stopline

## 目录

```text
artifacts/refactor_freeze/
  baselines/<phase>/
  candidates/<phase>/
  diffs/<phase>/
```

## 支持的 snapshot 类型

- `provider_selection`
- `runtime_decision`
- `shadow_promotion`
- `shadow_admission`
- `downstream_gate`
- `replay_artifact_schema`
- `shadow_schema`
- `health_decision`

## 用法

生成 baseline：

```bash
python -m scripts.refactor_freeze.generate_baseline --phase phase_01
```

生成 candidate：

```bash
python -m scripts.refactor_freeze.generate_candidate --phase phase_01
```

只生成部分 snapshot：

```bash
python -m scripts.refactor_freeze.generate_baseline --phase phase_01 --snapshot-type runtime_decision --snapshot-type health_decision
```

生成 diff 报告：

```bash
python -m scripts.refactor_freeze.diff_snapshots --phase phase_01
```

带审批文件生成 diff 报告：

```bash
python -m scripts.refactor_freeze.diff_snapshots --phase phase_01 --approval-file approvals.json
```

## approval_file 格式

工具不会自行创建 `approval_ref`。如需继续带 diff 的 phase，必须显式提供：

```json
{
  "approvals": [
    {
      "snapshot_type": "runtime_decision",
      "case_id": "strong_bullish__aix__create",
      "field": "$.decision",
      "approval_ref": "RFC-001"
    }
  ]
}
```

## stopline 触发条件

- baseline snapshot 缺失
- candidate snapshot 缺失
- diff 非空且没有批准
- 使用白名单之外的归一化
