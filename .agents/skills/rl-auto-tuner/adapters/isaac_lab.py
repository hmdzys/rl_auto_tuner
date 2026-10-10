"""Adapter for inspected mdog_loco summaries. Native training remains in its own venv."""
import csv
from pathlib import Path
import statistics


def mdog_summary(summary,csv_path=None,target_height=.33):
    # Old summaries lack episode counts, roll/pitch, action and torque telemetry.
    from diagnose_pose import POSE_KEYS, from_rows
    from common import finite
    pose={k:None for k in POSE_KEYS}; proxies={}
    if finite(summary.get('mean_body_height_m')):
        proxies['mean_height_bias_m']=abs(summary['mean_body_height_m']-target_height)
    if csv_path and Path(csv_path).is_file():
        with Path(csv_path).open() as f: rows=list(csv.DictReader(f))
        adapted=[]
        for r in rows:
            item=dict(r)
            # body_height_m in this inspected evaluator is already ground-relative.
            item['base_height_m']=float(r['body_height_m']); item['ground_height_m']=0.
            contacts=[]; speeds=[]
            for leg in ('FL','FR','RL','RR'):
                c=r.get(leg+'_foot_contact'); v=r.get(leg+'_foot_slip_m_s')
                if c is not None and v is not None: contacts.append(float(c)); speeds.append(float(v))
            if len(contacts)==4: item.update(contacts=contacts,foot_speed_m_s=speeds)
            adapted.append(item)
        pose.update(from_rows(adapted,target_height)['metrics'])
    else:
        # Mean height bias is not mean absolute height error, so keep it a proxy.
        feet=summary.get('feet',{})
        slip=[f.get('mean_contact_slip_m_s') for f in feet.values()]
        if slip and all(finite(v) for v in slip): proxies['unweighted_mean_contact_slip_m_s']=statistics.mean(slip)
    return {'schema':1,'checkpoint':summary.get('checkpoint'),
        'protocol':{'seeds':[summary.get('seed')], 'scenarios':['forward'],
            'seconds':summary.get('seconds'),'num_envs':summary.get('num_envs'),
            'terrain':summary.get('stage'),'commands':{'vx':summary.get('command_m_s'),
                'vy':summary.get('side_command_m_s'),'wz':summary.get('yaw_rad_s')},
            'pushes':summary.get('pushes'),'terrain_levels':summary.get('terrain_levels'),
            'terrain_types':summary.get('terrain_types')},
        'task':{'velocity_error':summary.get('mean_velocity_error_m_s'),
            'yaw_error':summary.get('mean_yaw_error_rad_s')},'pose':pose,
        'safety':{'fall_rate':None,'torque_saturation_ratio':None},
        'coverage':{'samples':summary.get('samples_after_settling',0),'episodes':None,'scenario_seeds':[['forward',summary.get('seed')]]},
        'proxies':proxies,'falls_count':summary.get('falls'),
        'limitations':['old evaluator lacks stand coverage, rollout/episode denominator, roll/pitch, joint/action/torque streams',
            'existing contact speed is a world-horizontal slip proxy, needs terrain-relative calibration on slopes']}


def training_argv(python,entrypoint,config,name,checkpoint='scratch',iterations=100,num_envs=512,stage='flat'):
    return [str(python),str(entrypoint),'train','--config',str(config),'--name',name,
        '--from',str(checkpoint),'--iterations',str(iterations),'--num-envs',str(num_envs),'--stage',stage,'--headless']
