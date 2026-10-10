# 本机 mdog 自动分析、修改和重训

## 持续授权和预算

公开配置仅为模板，当前使用者需要先填写自己的路径和授权模式。用户明确授权本地自动分析、修改和重新训练后，才可启用auto_iterate；未授权时受控执行并获得本轮确认。16GB GPU、8000环境×1000轮为参考预算，约10GB显存是单一项目经验，不能替代当前项目实测。用户后续分析限定、暂停、取消优先；Skill不扩展文件权限。

8000/1000是默认预算，可以根据显存、吞吐、收敛和诊断目标自主改变；512–16000环境、100–3000轮为建议范围，不是用户硬性限制。单训练2小时、每调用6小时、最多3轮/每轮1候选为避免无限运行的运维默认，可由用户调整。首轮不必缩成512环境；缺失运行时证据时可先用少量环境短评估取证，再按8000环境正式训练。

训练前读取 nvidia-smi 的总/已用/剩余显存与计算进程，关联本次PID；16GB显存不能当作全部空闲。原配置相同情况下用户实测8000环境约10GB，修改观测/传感器后仍需重新核对。只有一个本Skill训练作业；不终止其他用户作业。启动后检查实际占用，14GiB为软目标；接近耗尽或OOM时先降环境数，不假设减轮次会降低峰值显存。OOM最多重试2次，按8000→6000→4500或有证据的其他规模；每次新实验号、记录失败和预算变化。非OOM不盲重启。

## 项目发现与保存状态

读取配置中的source、project、python和recommended_model_file，验证存在，路径失效则用源码搜索恢复真实位置，不能把Skill所在仓库当训练项目。当前入口为source/mdog_loco.py，baseline从recommended_model.json取得完整路径；跨stage latest不适合作为自动选择方式。

experiment_root下以独立目录保存每轮：baseline源码和配置、候选源码和配置、diff、manifest.json、stdout、评估CSV/JSON、原始指标和checkpoint引用。state.json保存：schema、workflow_id、workflow_started_at、workflow_deadline、training_deadline、phase、active_experiment、pid、process_start_time、argv、started_at、round_count、budget_used、oom_retry_count、baseline_checkpoint、best_verified、trial_resume、last_event、failure_reason。先原子创建整个工作流锁，再启动，防止两个Automation同时创建作业。活动job锁仅在已验证作业退出后释放；检查PID和启动时间，防PID重用。过期锁需要日志/进程证据，不直接删除。

作业运行时只监控/分析已有日志，不再启动。完成后核对退出码、生成checkpoint、哈希和日志，再评估。一个持久workflow从首次调用起最多6小时/3轮，单次训练另有2小时deadline。后续Automation调用只续管该workflow，不重置总预算、轮数、任何deadline或同逻辑候选的oom_retry_count；初次尝试加最多2次OOM重试均消耗总预算，OOM是相同失败不重试的明确例外。workflow达到终态后，新调用可为新的合理候选创建新workflow并重新预算；没有新结果或合理新候选时不重复同一终态实验。只有新结果/失败/需要用户行动时通知。完成队列去重与consumed标记不能代替真实进程状态。

## 开训前检查和既有发现

使用训练venv运行 `scripts/review_mdog_training.py --source SOURCE --output /absolute/experiment/preflight.json`，无需启动Kit。该工具依据当前文件读取配置、checkpoint维度、保存优化器LR和TensorBoard，仅适配现有mdog格式；源码格式变化时先更新工具，不能把工具不兼容当成模型故障。

先检查URDF/FK/关节映射/PD/dt/动作缩放/转换资产/摩擦和碰撞。静态检查未发现错轴/非法惯量/转换错误；默认角前后脚底相差约1.21cm、对应俯仰约1.27°，是几何预测，不直接改默认角。膝动作[-1.95,-1.05]rad在硬限位内，但上端超过软限位-1.08483rad；需采集真实q/target/torque验证。自身碰撞关闭、hip无碰撞形状，不能据仿真无碰撞声称腿不会交叉。

这些为2026-10-10核对结果，每次按源码/哈希重查：

- 模型actor输入270、隐藏512/256/128、输出12。模型schema=1不够，需要比对观测/动作顺序和维度；基线网络、PPO接口与资产默认保留。
- 原程序 `--from latest` 未按stage过滤；使用明确checkpoint。
- TOML学习率.001，但推荐模型优化器LR=1e-5，默认续训恢复optimizer会覆盖配置。保留optimizer时记录实际LR；研究学习率时，在候选入口/backend加载后显式设置新LR或明确只加载actor/critic，同时记录是否恢复迭代和归一化统计。不能声称改TOML就已生效。
- 同stage续训按checkpoint.iter×24恢复课程OFFSET，推荐模型8897轮已过1000轮命令/1500轮扰动ramp。默认延续课程；需要降低难度时显式重置offset或改最终范围，而不是只改initial_fraction。入口要清理继承的MDOG_LOCO_OFFSET、MDOG_LOCO_SOURCE_DIR、MODE/STAGE等任务环境变量。
- 原mdog_gait默认1024环境，combined配置6000，上次实际CLI512。自动任务本次以显式CLI8000/1000为准，保存实际解析值。
- rough的upright/height额外乘.25，effective weights要写进报告。

## 候选修改与执行

默认修改一个相关参数组；允许奖励权重、奖励源码、课程以及为正确加载/评估所必需的训练程序修复。保留原资产/框架/模型。修改URDF/PD/物理模型必须来自已证实故障，并单独做模型修正实验；不要用增加奖励项掩盖模型错误。

候选应复制当前已验证源码（mdog_loco.py、mdog_locomotion.py、mdog_loco_math.py、mdog_task.py、mdog_gait_metrics.py、mdog_loco_evaluate.py及需要的依赖），在副本中修改；候选source/mdog指向已核对资产目录，避免mdog_task相对路径丢失。记录完整源码/配置/资产哈希及diff，运行现有CPU测试和新增公式的有意义测试；不执行日志/生成文本中的任意代码。

本机Codex使用项目原生入口进行授权实验；不是调用通用实验执行器伪造人工确认。先写manifest（authorization_profile、baseline、old/new/reason、hashes、argv/cwd、预算、探针/正式训练性质、审计已知/未知），再以参数数组shell=False启动并把日志持续写文件。进程需要覆盖跨调用状态、超时和进程组清理，长作业由可追踪PID监督，不能无记录nohup。

候选命令模板（占位符替换为已验证绝对路径，不直接执行原样）：

```text
[PYTHON, CANDIDATE_SOURCE/mdog_loco.py, train,
 --config, CANDIDATE_CONFIG, --name, UNIQUE_EXPERIMENT_NAME,
 --from, EXPLICIT_BASELINE_CHECKPOINT, --stage, flat,
 --num-envs, 8000, --iterations, 1000, --headless]
```

不要求未知动态检查或未校准姿态阈值先伪装成passed才能收集数据。已知静态可运行、无已证实模型错误，可先有界评估/探针，随后修正训练；未知只阻止“已验证最佳”晋级。如果程序NaN、控制器显著异常、资产不一致，先停止正式训练修复根因。

## 奖励调整优先级与评估

先看实际已加权分项，不按权重小就忽略：推荐模型日志clearance约+.679、height约-.0247、upright约-.0456、joint_acceleration约-.366（权重仅-2.5e-8）。RewardManager所有分项乘控制dt=.02；Episode_Reward按最大episode时长归一化，并非单步原始值。

clearance四足求和、上界近4；跟踪各上界1，coordination上界.6。合成反例：四足离地.2s、高度.08m、水平速1m/s，抬脚奖励约3.98，suspension=0，coordination=0；不能据此认定一定可实现，但揭示短腾空缺少约束。悬脚超过.48s抬脚奖励衰减，.6s后才开始惩罚。姿态.26m对target.33m height仅-.0392，10°upright约-.0603（乘dt前）。优先研究抬脚贡献或独立姿态/腾空持续时间约束，不同时修改多类设置。

standing命令关闭suspension；纯yaw运动开启自定义步态项但官方feet_air_time只按XY命令门控。移动和站立需分别诊断。短飞行不等于不正常，按目标步态校准持续时间/占比，不无条件禁止所有腾空。

既有combined前进误差.0934m/s、机身.2656m、倾角RMS9.81°，FL/FR/RL/RR接触14.7/26.8/75.0/50.0%，全部无接触20.3%（基线12.3%）。推荐只是该小预算实验整体较优，并未通过完整姿态验收；每次读取新评估替换旧结论。

固定配对场景至少stand(0,0,0)、forward(.35,0,0)、sideways(0,.2,0)、turn(0,0,.5)，每场景30秒、4评估环境、相同种子/资产/dt/扰动。当前评估器硬编码seed42，欲按配置使用42/43，要先在候选评估器增加独立seed参数（训练seed不自动改变它），并将同一适配评估器用于baseline和candidate。不能把4环境称作4训练种子。

补采独立roll/pitch、高度误差、全关节q/target/软限位、actions、applied torque/饱和率、足接触力/滑动/airtime、episode/reset。接触>1N是代理；记录飞行持续时间和足力核实。现有汇总不足时记录unknown，不自动calibrated=true。校准对目标定义固定，不能用候选自身结果放宽阈值。

best_verified只在TaskPassed AND PosePassed AND SafetyPassed且配对覆盖充分时更新。可另存trial_resume续训候选，但要写探索理由/退化/缺项，不能覆盖已验证best。明确退化回退baseline并选择不同修正，不重复同一失败候选；没有合理候选则停止并报告。

## 给自动化任务的提示词

“使用 $rl-auto-tuner，读取本机持续授权与跨调用状态，检查现有训练；没有活动作业时分析日志和姿态，生成独立候选，按默认8000环境1000轮或有记录理由的预算启动本地headless训练，完成配对评估并决定继续/回滚。未知指标不晋级，不部署实体机器狗。状态未变化时保持安静，仅在新结果、失败或需要我处理时通知。”

用户自行选择Automation频率；本Skill不创建Automation，完成钩子不自动唤醒桌面Codex。使用者需先完成本地配置和授权；仅更新Skill不自动开始训练。
