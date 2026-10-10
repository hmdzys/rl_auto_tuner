# 奖励候选

第一版只做已存在的标量 TOML 权重调整。optimize_reward.propose 读配置和 policy.bounds，限制相对变化不超过 25%、禁止零值/翻符号、保留原文件，每个候选只改一个标量并记录原因。不同候选可以独立加强 upright 或 smooth，不能合并成一轮多类变化。

Codex 负责利用环境源码、任务说明与上一轮反馈提出假设，脚本负责约束和记录。分析 logged reward contribution 时确认是否已乘 weight、dt 或按 episode 归一化。总奖励变高不作为选择标准。

奖励源码扩展时先在只读报告给出函数签名、tensor shape、依赖状态和预期方向。用单独源码副本、diff、有限值/shape/梯度和运行时检查再请求受控训练；脚本不 exec/eval/导入任意生成代码。生成代码不是安全沙箱，应由 Codex 审查并在隔离环境中运行。Optuna 可后续加入作为 policy.bounds 内的搜索器，沿用独立评估门槛和预算；第一版没有 Optuna 依赖或搜索执行器。
