"""End-to-end synthetic probe with no GPU, simulator or external writes."""
import copy
from pathlib import Path
import tempfile
from common import digest, emit, parser, policy, write_json
from analyze_training import analyze
from diagnose_pose import diagnose, from_rows
from evaluate_candidate import compare
from experiment_manager import create_experiment, prepare, run_experiment
from rollback import restore
from training_complete import enqueue


def run(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    # New isolated directory makes repeated dry-runs independent.
    work=Path(tempfile.mkdtemp(prefix='dry-',dir=root))
    config=work/'input.toml'; config.write_text('[weights]\nupright = -2.0\nheight = -8.0\nsmooth = -0.01\n[targets]\nbody_height = 0.33\n[commands]\ninitial_fraction = 0.35\n')
    logs=work/'scalars.json'; write_json(logs,{'scalars':{'Train/mean_reward':[[i,10+i*.01] for i in range(40)],
        'Episode_Reward/alive':[[i,1] for i in range(40)],'Episode_Reward/upright':[[i,-.1] for i in range(40)]}})
    baseline={'schema':1,'protocol':{'seeds':[42], 'scenarios':['stand','forward'],
        'seconds':30,'num_envs':4,'terrain':'flat','dt':.02,'settling_seconds':1,
        'model_hash':'synthetic-robot','control_hash':'synthetic-controller'},
        'task':{'velocity_error':.12,'yaw_error':.1},
        'pose':{'base_height_error':.01,'roll_pitch_error':.1,'joint_limit_violations':0,
            'joint_pose_deviation':.1,'foot_slip_ratio':.05,'gait_asymmetry':.1,'action_smoothness':.02},
        'safety':{'fall_rate':0,'torque_saturation_ratio':.01},
        'coverage':{'samples':1000,'episodes':12,'scenario_seeds':[['stand',42],['forward',42]]}}
    candidate=copy.deepcopy(baseline); candidate['task']['velocity_error']=.08
    bad=copy.deepcopy(candidate); bad['pose']['roll_pitch_error']=.4
    write_json(work/'baseline.json',baseline); write_json(work/'candidate.json',candidate)
    audit={'status':'review_required','reason':'synthetic dry-run does not constitute model audit'}
    experiment=create_experiment(work/'experiments',config,
        {'parameter':'weights.upright','factor':1.2,'reason':'synthetic tilt correction proposal'},audit)
    command=['python','mdog_loco.py','train','--config',str(experiment/'candidate.toml'),'--name',experiment.name,'--headless']
    prepared=prepare(experiment,command,work)
    execution=run_experiment(experiment,dry_run=True)
    rollback=restore(experiment,work/'restored.toml')
    event=enqueue(work/'queue',work,0)
    summary={'synthetic':True,'work':str(work),'framework':'fixture_only',
        'training':analyze(logs),'proposal_diff':(experiment/'candidate.diff').read_text(),
        'experiment':str(experiment),'prepared':prepared,'execution':execution,
        'healthy_improvement':compare(baseline,candidate),'pose_regression':compare(baseline,bad),
        'rollback_byte_identical':digest(config)==digest(work/'restored.toml'),'hook_event':str(event),
        'gpu_started':False,'promotion_performed':False}
    write_json(work/'dry_run_report.json',summary)
    return summary


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('--root',type=Path,default=Path('reports/dry-run'))
    a=p.parse_args(); emit(run(a.root),a.output)
