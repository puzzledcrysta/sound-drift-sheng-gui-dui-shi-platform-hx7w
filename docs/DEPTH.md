# 声轨对时台业务与测试登记

- 规模：中型
- 使用者：口述历史音频整理员
- 核心规则：按音频样本计数和标准时钟锚点做分段映射，检测时钟回退和漂移超界。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 录音来源 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 锚点字段 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 时码异常 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 双锚校时 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 制作勾稽 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 片段批次 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 校时复核 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 剪辑交接 | 主备轨校时后生成交接清单，最少换声、主轨优先、空档标注并按取用时长对账 | `POST /api/handover` | `app/modules/handover/planner.py` | `tests/test_handover.py`、`tests/test_handover_api.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-09 | large index | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_large_index` |
| TRAP-108 | rewound | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_rewound` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。

## 剪辑交接（M8）

- 来源在通用声轨字段外增加 `轨道角色`（仅 `主轨`/`备轨`），外部账为三列 `声轨片段,轨道角色,外部取用(毫秒)`，样例见 `sample_data/handover.csv` 与 `handover_external.csv`。
- 校时复用 `domain/rule.py` 的 `calibrate`，与双锚校时共用同一时钟事实；漂移、回退、覆盖越界片段进隔离。
- 规划器 `planner.py` 先按所有片段校准起止切分基础区间，再以动态规划求全局最优，目标字典序为：**换声次数最少 → 主轨实际取用毫秒最多 → 确定性次序**。每个区间只留一路，两轨皆无的区间标 `空档` 并断开前后（不产生换声），相邻同来源切片再合并。
- 对账以每个片段**实际取用时长**（而非片段原始时长）与外部账逐笔全外连接；`confirmable` 仅在无隔离且无账差时为真。差异未核清前 `POST .../reviews` 的「确认」被 `HANDOVER_OPEN` 拒绝；空档、隔离、账差或退回均须填意见。
- 批次指纹 = `handover-1.0:sha256(来源):sha256(外部账)`，写入独立的 `handover_runs`/`handover_reviews` 表；同批重跑 `INSERT OR IGNORE` 不新增清单。
