# rl_auto_tuner

供桌面 Codex 使用的机器狗强化学习自动调优 Skill。参考 Eureka 的“候选奖励—训练—反馈”思路，分析训练日志和姿态，在独立副本中修改奖励/课程、重新训练，并以任务、姿态和安全指标做配对评估与回滚。

## 使用

将 `.agents/skills/rl-auto-tuner/` 放入项目的同名目录，在 Codex 中调用 `$rl-auto-tuner`。也可明确要求读取该目录的 `SKILL.md`。

- [Skill 入口](.agents/skills/rl-auto-tuner/SKILL.md)
- [本机自动迭代说明](.agents/skills/rl-auto-tuner/references/mdog_automation.md)
- [通用受控执行接口](.agents/skills/rl-auto-tuner/references/local_integration.md)
- [数据契约](.agents/skills/rl-auto-tuner/references/data_contract.md)
- [方法来源与第三方许可证](.agents/skills/rl-auto-tuner/references/eureka_method.md)

公开配置默认受控模式，不包含持续授权或真实机器路径。`config/mdog_auto.json` 是待填写的模板：参考16GB GPU、8000环境×1000轮、headless，可根据实际显存和反馈调整。每位使用者必须填写自己的路径并明确授权自动训练，不能将模板当作授权。

自动迭代由 Codex 按 Skill 指令执行，不是独立无人值守搜索服务。用户自行创建 Codex Automation；训练完成钩子登记队列，不能自行唤醒桌面 Agent。已有作业时监控，不重复启动。缺失姿态/安全指标阻止晋级最佳模型，允许授权范围内先做有界取证。实体机器狗部署不在自动授权范围。

## 功能

- 框架检测：Isaac Lab、legged_gym、RSL-RL，未知框架保持未知。
- TensorBoard/CSV/JSON 日志分析，URDF 静态审查与姿态诊断。
- 有界数值候选、配置快照、哈希绑定、训练超时、完成队列与回滚。
- 本机训练核对：有效奖励贡献、optimizer 学习率恢复、课程进度、checkpoint 结构与源码快照。
- Codex 在独立源码副本中修改奖励公式；Optuna/DrEureka 自动搜索尚未接入。

## 验证

通用工具需要 Python 3.11+，基础测试不依赖 GPU 或仿真器：

```bash
python3 -m unittest discover -s tests -v
python3 .agents/skills/rl-auto-tuner/scripts/dry_run.py --root /tmp/rl-auto-tuner-dry-run
```

TensorBoard/模型审查需要已有训练环境中的 torch 和 tensorboard；不要为运行基础测试安装整个 Isaac Lab。`review_mdog_training.py` 是当前作者项目的适配器，需要先核对配置路径和现有文件格式。

```bash
/path/to/training/venv/bin/python .agents/skills/rl-auto-tuner/scripts/review_mdog_training.py \
  --source /path/to/mdog_gait --output /tmp/mdog-preflight.json
```

当前31项工具CPU测试通过；dry-run使用合成数据。CPU测试通过不能证明动态步态或真实硬件安全。仓库不包含训练checkpoint、日志、实验状态和机器专用报告。
