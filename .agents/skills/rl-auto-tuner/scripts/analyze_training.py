"""Training trends are evidence, not a proof of policy convergence."""
from pathlib import Path
import statistics
import sys
from common import SKILL, emit, finite, parser
sys.path.insert(0,str(SKILL))
from adapters.rsl_rl import load_scalars, checkpoints


def analyze(path):
    result={'status':'ok','metrics':{},'warnings':[], 'convergence':'unknown'}
    try: data=load_scalars(path)
    except (RuntimeError, ValueError, KeyError) as exc:
        result.update(status='unavailable',error=str(exc)); return result
    for tag, points in data.items():
        if not isinstance(points,list) or not points:
            result['warnings'].append(f'empty metric: {tag}'); continue
        if any(not isinstance(p,list) or len(p)!=2 or not all(finite(v) for v in p) for p in points):
            result['warnings'].append(f'invalid/nonfinite metric: {tag}'); result['status']='invalid'; continue
        # Restarts can repeat steps; latest sample wins at each step.
        values=[v for _,v in sorted(dict((p[0],p[1]) for p in points).items())]
        n=max(1,len(values)//5); first=statistics.mean(values[:n]); last=statistics.mean(values[-n:])
        result['metrics'][tag]={'samples':len(values),'first_mean':first,'last_mean':last,
            'relative_change':(last-first)/max(abs(first),1e-9),
            'tail_cv':statistics.pstdev(values[-n:])/max(abs(last),1e-9)}
    reward=next((v for k,v in result['metrics'].items() if k in ('Train/mean_reward','train/mean_reward','mean_reward')),None)
    if reward and reward['samples'] >= 20:
        result['convergence']='plateau_candidate' if abs(reward['relative_change'])<0.05 and reward['tail_cv']<0.1 else 'changing'
    parts={k:abs(v['last_mean']) for k,v in result['metrics'].items() if k.startswith(('Episode_Reward/','Episode/rew_','Reward/'))}
    total=sum(parts.values())
    result['reward_contribution_shares']={k:v/total for k,v in parts.items()} if total else {}
    if any(v>0.8 for v in result['reward_contribution_shares'].values()):
        result['warnings'].append('one logged reward contribution exceeds 80%; verify logger normalization and policy behavior')
    if Path(path).is_dir(): result['checkpoints']=checkpoints(path)
    result['note']='Plateau and reward shares need fixed-scenario evaluation; logged components may already include weights.'
    return result


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('log',type=Path); a=p.parse_args(); emit(analyze(a.log),a.output)
