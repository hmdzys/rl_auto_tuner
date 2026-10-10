# 桌面 Codex / 本地训练接入

在仓库聊天中使用 `$rl-auto-tuner`；若本次聊天的技能列表尚未刷新，可直接要求“读取 .agents/skills/rl-auto-tuner/SKILL.md 执行”。Skill 仓库在训练源码外，所有 PROJECT/CONFIG/RUN 参数明确传入，不能用当前工作目录推断为 Isaac Lab。

下面命令从 Skill 仓库根目录运行；S 指向本 Skill，PY 指向训练项目原有 Python。所有命令保持显式，不安装/替换训练环境。

```bash
S="$PWD/.agents/skills/rl-auto-tuner"
PY=/path/to/IsaacLab/.venv/bin/python
python3 "$S/scripts/dry_run.py" --root "$PWD/reports/dry-run"
python3 "$S/scripts/detect_framework.py" /path/to/IsaacLab
```

本机自动流程优先读取 [mdog 自动迭代](mdog_automation.md) 和 `config/mdog_auto.json`，填写自己的 `mdog_gait` 入口并获得当前用户授权，参考8000环境/1000轮预算。下面是通用严格受控脚本接口，不是本机自动循环。

历史框架检查：Isaac Lab VERSION=3.0.0，源码 SHA 见 reports/local_detection.json。现有 mdog_loco.py 在 `/path/to/mdog_previous_outputs/`，支持 `train --name --from --config --iterations --num-envs --stage --headless`。从源码确认训练参数 training.seed 在 TOML 读取，旧评估器 cfg.seed 固定 42；多种子评估需要独立适配，不能凭文档宣称已支持。

## 通用受控流程：分析和候选

```bash
python3 "$S/scripts/tune.py" --project PROJECT --config CONFIG.toml \
  --logs RUN_DIR --evaluation SUMMARY.json --urdf ROBOT.urdf \
  --dry-run --output reports/analysis.json
python3 "$S/scripts/optimize_reward.py" CONFIG.toml weights.upright 1.2 \
  --reason '前置检查通过后，平地倾斜误差超过阈值，进行单参数对比' --output request_preview.json
```

完成模型检查后保存 audit.json；校准 policy.yaml，设 calibrated=true。request.json 格式为 `{"parameter":"weights.upright","factor":1.2,"reason":"..."}`。

```bash
python3 "$S/scripts/experiment_manager.py" create --root experiments \
  --config CONFIG.toml --request request.json --audit audit.json --policy policy.yaml
```

把输出实验目录记为 EXPERIMENT。用 adapters.isaac_lab.training_argv(...) 生成 argv.json，或手工写 JSON 参数数组（不写 shell 字符串）：

```text
["/absolute/venv/python", "/absolute/mdog_loco.py", "train",
 "--config", "/absolute/EXPERIMENT/candidate.toml", "--name", "EXPERIMENT_ID",
 "--from", "/absolute/baseline.pt", "--iterations", "100", "--num-envs", "512",
 "--stage", "flat", "--headless"]
```

```bash
python3 "$S/scripts/experiment_manager.py" prepare EXPERIMENT --argv-json argv.json --cwd PROJECT
python3 "$S/scripts/experiment_manager.py" run EXPERIMENT --dry-run
# 用户确认 diff、命令、预算后，使用 prepare 输出的 digest：
python3 "$S/scripts/experiment_manager.py" run EXPERIMENT --confirm REVIEWED_DIGEST
```

以同样训练起点/步数比较候选，warm-start 是否恢复 optimizer/iteration 状态写入元数据。候选会留下源码配置记录；真实使用前检查目标入口确实消耗副本参数。

## 评估与恢复

现有 `mdog_loco.py evaluate --checkpoint FILE --seconds 30 --num-envs 4 --vx 0.35 --vy 0 --wz 0` 会写 summary.json/measurements.csv，但当前数据缺项，只能用于诊断，不能完整晋级。先扩展评估采集器输出 data_contract.md 定义的原始状态与场景/种子覆盖，以及模型/控制器/配置/checkpoint 哈希，再输出配对报告：

```bash
python3 "$S/scripts/evaluate_candidate.py" baseline.json candidate.json --policy policy.yaml
python3 "$S/scripts/experiment_manager.py" evaluate EXPERIMENT --baseline baseline.json --candidate candidate.json
python3 "$S/scripts/rollback.py" EXPERIMENT restored-original.toml
python3 "$S/scripts/rollback.py" experiments restored-best.toml --best
```

## 完成钩子

实验执行器会在训练成功/失败/超时后写 queue 事件与 training_analysis.json。原有外部训练可在结束后调用：

```bash
python3 "$S/scripts/training_complete.py" --run LOG_DIR --queue experiments/queue --returncode EXIT_CODE
```

通用受控训练使用 experiment_manager 的绑定执行接口；本机自主候选由Codex按mdog自动迭代参考中的原生训练入口及独立manifest执行。完成钩子只登记结果，没有绕过审计的命令执行模式。原有训练脚本可在退出处理器里登记真实 RUN_DIR；使用一个目录一次训练，事件按目录去重。`--dry-run` 只显示登记对象、不写入队列。

钩子执行是即时本地反馈；它不能自动调用桌面 Codex 或代表用户授权。若需要 Agent 自动继续，可由用户创建当前聊天的 heartbeat Automation：读取queue未消费事件和跨调用state.json，按当前用户实际授权的模式分析、修改并训练；有活动作业时只监控，只有新结果、失败或需要用户行动时通知。其他项目仍按其已有授权模式执行。当前实现没有安装或创建定时任务。

## 其他框架

legged_gym：检测源码和 RSL-RL 日志；检查 cfg/reward aliases 后显式导出 TOML overlay，并将 overlay 接到原训练入口。训练/评估命令须由用户项目提供；第一版不自动改 Python 配置类或移植 Isaac Gym。未知框架仍可导出通用 scalars/pose/evaluation JSON，使用同一诊断与候选比较接口。
