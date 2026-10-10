# 课程调节

保持旧新评估场景固定。训练课程改变不应改变评估课程，否则比较没有意义。

1. 难度刚升高且跌倒/姿态退化：退回旧训练难度验证，优先生成 commands.initial_fraction ×0.8 或 ramp_iterations ×1.2 的单参数实验。
2. 简单场景门槛稳定通过但难场景失败：增加训练覆盖，仍用相同配对种子复测。
3. 同一轮不同时修改奖励、课程、控制器、资产和 PPO。控制器或模型问题回到前置检查，不纳入默认自动调参白名单。

optimize_curriculum.py 只接受 policy.bounds 中 commands/randomization 的标量；地形数组和域随机化范围第一版需要显式扩展适配器。训练中途文件修改通常不会重读，必须通过下一次启动的 candidate.toml 生效。记录 warm-start checkpoint、迭代数和状态恢复机制，不能把续训优势当作奖励优化因果证据。
