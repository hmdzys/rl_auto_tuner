"""Desktop-friendly analysis/proposal entrypoint; never starts training."""
from pathlib import Path
import sys
from common import SKILL, digest, emit, parser, policy, read_json, write_json
from analyze_training import analyze
from detect_framework import detect, audit_urdf
from diagnose_pose import diagnose
from experiment_manager import create_experiment, audit_valid
sys.path.insert(0,str(SKILL))
from adapters.isaac_lab import mdog_summary


def inspect(project,config=None,logs=None,evaluation=None,audit=None,urdf=None,rules=None):
    rules=rules or policy()
    report={'schema':1,'framework':detect(project),'training':analyze(logs) if logs else {'status':'not_supplied'},
        'audit':audit or {'status':'unknown'},'evaluation':None,'diagnosis':None,'suggestions':[]}
    if urdf: report['urdf_static_audit']=audit_urdf(urdf)
    if evaluation:
        data=read_json(evaluation)
        target=.33
        if config:
            import tomllib
            target=tomllib.loads(Path(config).read_text()).get('targets',{}).get('body_height',target)
        if 'mean_velocity_error_m_s' in data:
            import tomllib
            checkpoint=Path(data.get('checkpoint') or '/nonexistent/checkpoint')
            saved_config=checkpoint.parent/'loco_input.toml'
            if saved_config.is_file():
                target=tomllib.loads(saved_config.read_text()).get('targets',{}).get('body_height',target)
                report['evaluation_config']={'path':str(saved_config),'sha256':digest(saved_config),
                    'target_height':target,'source':'checkpoint_snapshot'}
                report['input_config_matches_evaluation']=bool(config and digest(config)==digest(saved_config))
            else:
                report['evaluation_config']={'target_height':target,'source':'unverified_current_or_default'}
                report['input_config_matches_evaluation']=False
            data=mdog_summary(data,Path(evaluation).parent/'measurements.csv',target)
        report['evaluation']=data
        report['diagnosis']=diagnose(data.get('pose',{}),report['audit'],rules['pose_limits'])
        preflight=audit_valid(report['audit']) and report.get('input_config_matches_evaluation',True)
        for finding in report['diagnosis']['findings']:
            key=finding.get('candidate_parameter')
            if finding.get('status')=='failed' and key in rules['bounds'] and preflight:
                report['suggestions'].append({'parameter':key,'factor':1.2,
                    'reason':f"{finding['metric']}={finding['value']:.5g} exceeds {finding['limit']}; preflight passed; strengthen penalty in an isolated experiment"})
    report['training_allowed']=False
    report['note']='This entrypoint only reads and proposes. Missing data blocks automatic training/promotion; inspect hypotheses before changing reward.'
    return report


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('--project',required=True); p.add_argument('--config'); p.add_argument('--logs')
    p.add_argument('--evaluation'); p.add_argument('--audit'); p.add_argument('--urdf'); p.add_argument('--policy')
    p.add_argument('--experiment-root'); p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(); rules=policy(a.policy); audit=read_json(a.audit) if a.audit else None
    report=inspect(a.project,a.config,a.logs,a.evaluation,audit,a.urdf,rules)
    if a.experiment_root:
        if not a.config: p.error('--config required for candidates')
        if not audit_valid(audit or {}):
            report['candidate_status']='blocked_by_model_controller_preflight'
        elif rules['mode']=='analysis': report['candidate_status']='analysis_only'
        else:
            report['experiments']=[str(create_experiment(a.experiment_root,a.config,r,audit,rules))
                for r in report['suggestions'][:rules['max_candidates']]]
    report['dry_run']=a.dry_run
    emit(report,a.output)
