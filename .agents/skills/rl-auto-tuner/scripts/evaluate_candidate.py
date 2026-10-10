"""Accept only matched independent task, pose and safety evidence."""
import itertools
from common import emit, finite, parser, policy, read_json

PROTOCOL_KEYS=('seeds','scenarios','seconds','num_envs','terrain','dt','settling_seconds','model_hash','control_hash')


def validate(report, rules):
    reasons=[]; protocol=report.get('protocol',{}); coverage=report.get('coverage',{})
    for key in ('seconds','num_envs','dt'):
        value=protocol.get(key)
        if not finite(value) or value<=0: reasons.append(f'invalid protocol {key}')
    settling=protocol.get('settling_seconds')
    if not finite(settling) or settling<0 or (finite(protocol.get('seconds')) and settling>=protocol['seconds']):
        reasons.append('invalid settling duration')
    for key in ('model_hash','control_hash','terrain'):
        if not isinstance(protocol.get(key),str) or not protocol[key]: reasons.append(f'invalid protocol {key}')
    if report.get('schema')!=1: reasons.append('unsupported evaluation schema')
    for key in PROTOCOL_KEYS:
        if protocol.get(key) in (None,[], ''): reasons.append(f'missing protocol {key}')
    seeds=protocol.get('seeds',[]); scenes=protocol.get('scenarios',[])
    valid_seeds=isinstance(seeds,list) and bool(seeds) and all(type(s) is int and s>=0 for s in seeds)
    valid_scenes=isinstance(scenes,list) and bool(scenes) and all(isinstance(s,str) and bool(s) for s in scenes)
    if valid_seeds: valid_seeds=len(seeds)==len(set(seeds))
    if valid_scenes: valid_scenes=len(scenes)==len(set(scenes))
    if not valid_seeds: reasons.append('invalid seeds')
    if not valid_scenes or not set(rules['required_scenarios']).issubset(scenes): reasons.append('required scenarios absent or invalid')
    if valid_seeds and valid_scenes:
        expected={tuple(x) for x in itertools.product(scenes,seeds)}
        supplied=coverage.get('scenario_seeds',[])
        valid_coverage=isinstance(supplied,list) and all(isinstance(x,list) and len(x)==2 and
            isinstance(x[0],str) and type(x[1]) is int for x in supplied)
        if not valid_coverage or set(map(tuple,supplied))!=expected or len(supplied)!=len(expected):
            reasons.append('missing scenario/seed coverage')
    for key,minimum in [('samples',rules['minimum_samples']),('episodes',rules['minimum_episodes'])]:
        value=coverage.get(key)
        if not finite(value) or value<minimum: reasons.append(f'insufficient {key}')
    for group in ('task','pose','safety'):
        for name,limit in rules[group+'_limits'].items():
            value=report.get(group,{}).get(name)
            if not finite(value) or value<0: reasons.append(f'unknown/invalid {group}.{name}')
            elif value>limit: reasons.append(f'{group}.{name} {value:g} exceeds {limit:g}')
    return reasons


def compare(baseline,candidate,rules=None):
    rules=rules or policy(); reasons=validate(candidate,rules)
    baseline_reasons=validate(baseline,rules)
    # Baseline may fail health thresholds; missing or invalid baseline is never comparable.
    reasons += ['baseline: '+r for r in baseline_reasons if ' exceeds ' not in r]
    if baseline.get('protocol')!=candidate.get('protocol'): reasons.append('evaluation protocol mismatch')
    for group in ('pose','safety'):
        for name,limit in rules[group+'_limits'].items():
            old=baseline.get(group,{}).get(name); new=candidate.get(group,{}).get(name)
            allowance=limit*rules['pose_regression_tolerance'] if group=='pose' else 0.
            if finite(old) and finite(new) and new>old+allowance: reasons.append(f'regression {group}.{name}')
    old=baseline.get('task',{}).get('velocity_error'); new=candidate.get('task',{}).get('velocity_error')
    if finite(old) and finite(new) and old-new<rules['minimum_improvement']:
        reasons.append('velocity improvement below required margin')
    oy=baseline.get('task',{}).get('yaw_error'); ny=candidate.get('task',{}).get('yaw_error')
    if finite(oy) and finite(ny) and ny>oy: reasons.append('yaw tracking regressed')
    return {'accepted':not reasons, 'reasons':reasons, 'baseline_health':baseline_reasons,
        'gates':{group:not any(group+'.' in r for r in reasons) for group in ('task','pose','safety')},
        'note':'Single aggregate comparison is not statistical proof; repeat paired seeds before real promotion.'}


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('baseline'); p.add_argument('candidate'); p.add_argument('--policy')
    a=p.parse_args(); emit(compare(read_json(a.baseline),read_json(a.candidate),policy(a.policy)),a.output)
