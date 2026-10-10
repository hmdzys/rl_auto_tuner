"""Compute pose measurements; absence is unknown, never healthy."""
import csv
import json
import math
from pathlib import Path
import statistics
from common import emit, finite, parser, policy, read_json

POSE_KEYS=('base_height_error','roll_pitch_error','joint_limit_violations','joint_pose_deviation',
    'foot_slip_ratio','gait_asymmetry','action_smoothness')


def vector(row,key):
    value=row.get(key)
    if isinstance(value,str):
        try: value=json.loads(value)
        except (ValueError,TypeError): return None
    return value if isinstance(value,list) and value and all(finite(x) for x in value) else None


def number(row,key):
    value=row.get(key)
    if isinstance(value,str):
        try: value=float(value)
        except ValueError: return None
    return value if finite(value) else None


def from_rows(rows,target_height,slip_threshold=0.1):
    if not finite(target_height) or target_height<=0: raise ValueError('target height must be positive and terrain-relative')
    samples={k:[] for k in POSE_KEYS}; previous={}; duties=[[],[],[],[]]
    slip_count=contact_count=0; action_expected=0; stream_complete=True; row_times={}
    for row in rows:
        h=number(row,'base_height_m'); g=number(row,'ground_height_m')
        if h is not None and g is not None: samples['base_height_error'].append(abs(h-g-target_height))
        roll=number(row,'roll_rad'); pitch=number(row,'pitch_rad')
        if roll is not None and pitch is not None:
            samples['roll_pitch_error'].append(roll*roll+pitch*pitch)
        q=vector(row,'joint_positions'); lo=vector(row,'joint_lower'); hi=vector(row,'joint_upper')
        if q and lo and hi and len(q)==len(lo)==len(hi) and all(l<u for l,u in zip(lo,hi)):
            samples['joint_limit_violations'].append(sum(x<l or x>u for x,l,u in zip(q,lo,hi))/len(q))
        default=vector(row,'default_joint_positions'); command=number(row,'command_speed_m_s')
        if q and default and len(q)==len(default) and command is not None and abs(command)<0.05:
            samples['joint_pose_deviation'].append(sum(abs(a-b) for a,b in zip(q,default))/len(q))
        contacts=vector(row,'contacts'); speeds=vector(row,'foot_speed_m_s')
        if contacts and speeds and len(contacts)==len(speeds)==4 and all(c in (0,1) for c in contacts) and all(v>=0 for v in speeds):
            for j,(c,v) in enumerate(zip(contacts,speeds)):
                duties[j].append(c)
                contact_count+=int(c); slip_count+=int(c and v>slip_threshold)
        actions=vector(row,'actions'); t=number(row,'time_s')
        env=str(row.get('env',0)); episode=str(row.get('episode',0)); key=(env,episode)
        old_time=row_times.get(key)
        if old_time is not None:
            action_expected+=1
            if t is None or t<=old_time: stream_complete=False
        if actions is None or t is None: stream_complete=False
        if t is not None: row_times[key]=t
        if actions and t is not None:
            old=previous.get(key)
            if old and t>old[0] and len(actions)==len(old[1]):
                samples['action_smoothness'].append(sum((a-b)**2 for a,b in zip(actions,old[1]))/len(actions))
            previous[key]=(t,actions)
    metrics={k:None for k in POSE_KEYS}
    for k,values in samples.items():
        # Partial streams cannot certify health. Standing uses only stationary rows.
        expected=len(rows) if k not in ('joint_pose_deviation','action_smoothness') else (
            sum(number(r,'command_speed_m_s') is not None and abs(number(r,'command_speed_m_s'))<0.05 for r in rows)
            if k=='joint_pose_deviation' else action_expected)
        if values and len(values)==expected:
            metrics[k]=statistics.mean(values)
    if not stream_complete: metrics['action_smoothness']=None
    if metrics['roll_pitch_error'] is not None: metrics['roll_pitch_error']=math.sqrt(metrics['roll_pitch_error'])
    if contact_count and len(duties[0])==len(rows): metrics['foot_slip_ratio']=slip_count/contact_count
    if duties[0] and len(duties[0])==len(rows):
        duty=[statistics.mean(v) for v in duties]
        metrics['gait_asymmetry']=max(abs(duty[0]-duty[1]),abs(duty[2]-duty[3]))
    return {'metrics':metrics,'samples':len(rows),'missing':[k for k,v in metrics.items() if v is None],
        'definitions':{'gait_asymmetry':'left/right front and rear contact duty difference; validate turn/terrain suitability',
            'action_smoothness':'mean squared action change per control step; compare equal dt only',
            'foot_slip_ratio':f'fraction of contact foot samples with speed > {slip_threshold} m/s'}}


def diagnose(metrics, audit=None, limits=None):
    limits=limits or policy()['pose_limits']; findings=[]
    audit=audit or {'status':'unknown'}
    if audit.get('status')!='passed':
        findings.append({'category':'model_or_controller','confidence':'requires_inspection',
            'reason':'Model/control/contact preflight is not passed; do not compensate with rewards.'})
    mapping={'base_height_error':('weights.height','inspect standing FK, terrain height and gains'),
        'roll_pitch_error':('weights.upright','inspect COM, contacts, slope-relative target'),
        'joint_limit_violations':('weights.joint_limits','inspect limits, joint sign/order and action scale'),
        'joint_pose_deviation':('weights.stand_still','inspect default angles and zero-command behavior'),
        'foot_slip_ratio':('weights.sliding','inspect friction and contact sensors'),
        'gait_asymmetry':(None,'inspect mapping, contact sequence and command/terrain asymmetry'),
        'action_smoothness':('weights.smooth','inspect PD gains, dt and torque saturation')}
    for key,(parameter,inspection) in mapping.items():
        v=metrics.get(key)
        if not finite(v):
            findings.append({'metric':key,'status':'unknown','reason':'missing or invalid measurement'})
        elif v>limits[key]:
            findings.append({'metric':key,'status':'failed','value':v,'limit':limits[key],
                'category':'reward_or_curriculum_hypothesis' if audit.get('status')=='passed' else 'unresolved',
                'inspect_first':inspection,'candidate_parameter':parameter if audit.get('status')=='passed' else None})
    failed=any(f.get('status')=='failed' for f in findings)
    unknown=any(f.get('status')=='unknown' for f in findings)
    return {'status':'failed' if failed else ('unknown' if unknown else 'passed'),
        'preflight':audit.get('status'), 'findings':findings,
        'note':'These metrics localize symptoms; they do not prove a causal reward/controller/model fault.'}


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('data',type=Path); p.add_argument('--target-height',type=float,default=.33)
    p.add_argument('--audit',type=Path); a=p.parse_args()
    if a.data.suffix=='.csv':
        with a.data.open() as f: result=from_rows(list(csv.DictReader(f)),a.target_height)
    else:
        data=read_json(a.data); result=from_rows(data['rows'],a.target_height) if 'rows' in data else {'metrics':data.get('pose',data)}
    result['diagnosis']=diagnose(result['metrics'],read_json(a.audit) if a.audit else None)
    emit(result,a.output)
