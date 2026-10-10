# 方法和开源来源

2026-10-10 核对官方仓库和许可；本 Skill 是独立实现，未复制第三方训练代码或依赖旧 Isaac Gym。第三方算法思想来源与接口参考如下，真正复用代码时需要按所用 commit 重新核对完整许可证及子模块/资产许可。

| 来源 | 采用/后续接口 | 许可核对 |
|---|---|---|
| [Eureka](https://github.com/eureka-research/Eureka) | 多候选、训练反馈、独立指标选优、保存实验；eureka/eureka.py | MIT |
| [DrEureka](https://github.com/eureka-research/DrEureka) | 域随机化及鲁棒性评估思想，第一版仅文档 | MIT |
| [legged_gym](https://github.com/leggedrobotics/legged_gym) | 姿态/接触/关节奖励参考，检测和显式适配 | BSD-3-Clause |
| [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | Reward/Curriculum Manager 及本机 mdog TOML 入口 | BSD-3-Clause，子组件/资产另审 |
| [RSL-RL](https://github.com/leggedrobotics/rsl_rl) | TensorBoard/标量日志和 checkpoint 索引 | BSD-3-Clause |
| [Text2Reward](https://github.com/xlang-ai/text2reward) | 文本到奖励源码扩展参考，未导入 | 未确认独立 LICENSE，不复用代码 |
| [Optuna](https://github.com/optuna/optuna) | 有界权重搜索扩展参考，第一版未安装 | MIT |

原 Eureka 生成奖励代码，启动 Isaac Gym 训练并汇总 TensorBoard/运行异常反馈；本 Skill 由桌面 Codex 阅读源码和报告、生成可审查候选，数值执行器不调用 OpenAI API，使用当前训练环境。候选原始总奖励不可跨奖励定义直接比较；以固定任务误差、姿态健康和安全条件选择。

第一版 reward/curriculum 数值 proposals 已实现；任意奖励函数生成、Optuna 搜索、DrEureka 随机化搜索和无人值守 Agent 循环是明确的后续扩展，不声称完成。

Skill 目录结构参考 [官方 Skills 文档](https://developers.openai.com/codex/skills/)。没有把外部训练完成钩子误当作桌面 Agent 唤醒接口。
