# 数据接口（schema 1）

所有数字必须有限且指标非负，角度 rad，长度 m，速度 m/s，dt 和时长 s。

## 日志

JSON `{"scalars":{"Train/mean_reward":[[0,1.0],[1,1.1]],"Episode_Reward/upright":[[0,-0.2]]}}`。
CSV 列 `tag,step,value`。TensorBoard 目录由 adapters/rsl_rl.py 读取；缺少依赖报告 unavailable，不静默伪造曲线。重复 step 取最后记录，分项占比按日志中的实际贡献计算，不把不同归一化方式混为原始奖励。20 个样本以上的平稳趋势仅标记 plateau_candidate；评估行为才能判断是否已学会任务。

## 逐帧状态

JSON `{"rows":[...]}` 或 CSV（数组字段为 JSON 字符串）。每行：

- `time_s`, `env`, `episode`：控制时间、并行环境和重置编号。每个环境/episode 严格按时间排序，重置使用新 episode，不能跨重置算动作差。
- `base_height_m`, `ground_height_m`：世界机身高度和机身下方地面高度；差值得到相对地面高度。
- `roll_rad`, `pitch_rad`：定义的参考系下姿态误差；坡地输入地形目标相对误差，不能用全局直立误差替代。
- `command_speed_m_s`：指令速度模；静止关节姿态指标仅在小于 0.05 时计算。
- `joint_positions`, `default_joint_positions`, `joint_lower`, `joint_upper`：同一显式 joint order，rad。
- `contacts`, `foot_speed_m_s`：固定 FL,FR,RL,RR 顺序，触地 0/1；足速度需要明确参考系和传感器阈值。
- `actions`：控制归一化动作向量。smoothness 是每步均方变化，不是时间导数，评估必须有相同 dt。

`diagnose_pose.from_rows(rows,target_height)` 输出七类 pose 指标。`fall_rate` 由完整 episode 计数或统计窗口提供，不能由过滤后的有效帧/秒数代替。`torque_saturation_ratio` 来自饱和关节样本/全部关节样本。跌倒事件与超时重置分开统计。

缺项是 null/unknown。原 mdog_loco summary 只有 height/slip 等部分信息；适配器读取旁边 measurements.csv 计算可用项。mean height bias 与 mean absolute error、mean slip speed 与 slip ratio 是不同量，不能互换。

## 评估报告

格式示例见`../config/evaluation.template.json`。必须包含：

- `schema:1`
- `protocol`: seeds、scenarios、seconds、num_envs、terrain、dt、settling_seconds、model_hash、control_hash；追加 commands、地形参数、随机化、观测噪声、checkpoint 起点等。旧新 protocol 必须完全一致。
- `task`: velocity_error、yaw_error，均为独立固定指令误差。
- `pose`: base_height_error（平均绝对误差）、roll_pitch_error（联合 RMS）、joint_limit_violations（越界关节样本比例）、joint_pose_deviation（静止平均绝对关节偏差）、foot_slip_ratio（触地样本速度 >0.1m/s 比例）、gait_asymmetry（左右触地占空比差）、action_smoothness（每步均方动作变化）。
- `safety`: fall_rate（跌倒 episode/总 episode）、torque_saturation_ratio。
- `coverage`: samples、episodes、scenario_seeds（每个场景/种子的完整笛卡尔积）。建议保留每个 rollout 结果，防止均值掩盖特定种子失败。
- 晋级额外需要 baseline 的 `config`、`config_sha256`，以及两份报告的 `checkpoint`、`checkpoint_sha256` 和 candidate 的 `config_sha256`，由可信本地评估器生成并与实验配置绑定。

默认场景 stand、forward 为最小样例，应补侧移、转向、粗糙地形及固定扰动；至少多个配对种子并给出方差。示例阈值须按任务校准，示例报告不是训练结果。
