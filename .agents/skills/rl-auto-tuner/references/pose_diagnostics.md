# 姿态前置诊断

数据流程：资产/控制器审计 → 固定场景状态指标 → 根因假设 → 单类参数候选 → paired evaluation。

| 症状 | 先检查 | 排除结构问题后的候选 |
|---|---|---|
| 低机身/站不直 | 地面相对高度、FK、默认角、执行器限力 | height 权重 |
| 前后/左右倾斜 | COM/惯量、接触分布、斜坡参考系 | upright、rotation |
| 外八/交叉/不对称 | 关节正负、joint order、限位、足轨迹 | stand_still 或特定步态约束 |
| 抖动/跳跃 | PD、dt、action scale、扭矩饱和、足端腾空 | smooth、stepping 等 |
| 足端打滑 | 摩擦、传感器、参考系、接触阈值 | sliding |
| 难度升级后跌倒 | 先固定旧难度复测，检查速度/扰动/地形进度 | initial_fraction/ramp_iterations |

脚本只给“待验证”原因，不仅凭一项高误差断言奖励错误。不对称可能在转向/坡地合理；当前占空比差只是诊断代理，不能等同于完整对角步态协调。

完整模型审计 JSON（用于严格执行器及最佳策略晋级）：`status:passed`、`reviewed_by`、`checks` 中 joint_mapping、default_pose_fk、controller、action_scale_dt、com_inertia、collision_contacts、converted_asset_equivalence 全 true，`evidence` 保存这些检查涉及的路径和 sha256。见 ../config/robot_audit.template.json；实际文件内容变化使审计失效。URDF 静态检查只能发现零轴、限位、默认角、映射集合、质量和 mesh 路径问题；不能证明 USD 实际控制顺序或运动学正确。通用严格执行器要求完整审计。已获持续授权的本机mdog流程允许静态可运行且无已证实模型故障时先执行有界探针、校准和修正训练，获取缺失动态证据；完整审计和独立评估仍是最佳策略晋级前提，见 mdog_automation.md。不得把未知签成passed。

视频：使用固定相机、时长、指令和同步时间戳，检查腹部擦地、拖脚与腿间干涉。视觉证据作为报告附件，交叉验证状态数据；第一版不自动处理视频文件。
