"""Mapping reference for legged_gym; no automatic mutation of Python config classes."""
WEIGHT_ALIASES={'upright':'orientation','height':'base_height','rotation':'ang_vel_xy',
    'smooth':'action_rate','sliding':'feet_slip','joint_limits':'dof_pos_limits',
    'forward':'tracking_lin_vel','heading':'tracking_ang_vel'}


def requirements():
    return {'status':'explicit_integration_required','logger':'RSL-RL scalar export or TensorBoard',
        'pose_input':'references/data_contract.md rows schema',
        'config':'export reviewable TOML tuning overlay and wire into existing cfg before training',
        'warning':'feet_slip availability and sign/weight conventions vary; inspect actual reward implementation',
        'aliases':WEIGHT_ALIASES}
