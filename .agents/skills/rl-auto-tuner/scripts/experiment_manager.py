"""Immutable candidate snapshots, bounded execution and best-policy references."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid
from common import digest, emit, finite, parser, policy, read_json, write_json
from optimize_reward import propose

AUDIT_CHECKS=('joint_mapping','default_pose_fk','controller','action_scale_dt','com_inertia',
    'collision_contacts','converted_asset_equivalence')


def audit_valid(audit):
    if audit.get('status')!='passed' or not audit.get('reviewed_by'):
        return False
    if not all(audit.get('checks',{}).get(k) is True for k in AUDIT_CHECKS): return False
    evidence=audit.get('evidence',[])
    if not evidence: return False
    return all(Path(e.get('path','')).is_file() and digest(e['path'])==e.get('sha256') for e in evidence)


def create_experiment(root,config,request,audit,rules=None):
    rules=rules or policy()
    if rules['mode']=='analysis': raise PermissionError('analysis mode cannot create executable candidates')
    candidate=propose(config,request['parameter'],request['factor'],request['reason'],rules)
    identifier=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    directory=Path(root).resolve()/identifier; directory.mkdir(parents=True,exist_ok=False)
    original=directory/'original.toml'; original.write_bytes(Path(config).read_bytes())
    updated=directory/'candidate.toml'; updated.write_text(candidate.pop('candidate_text'))
    (directory/'candidate.diff').write_text(candidate.pop('diff'))
    write_json(directory/'manifest.json',{'schema':1,'id':identifier,'status':'proposed',
        'candidate':candidate,'candidate_sha256':digest(updated),'original_sha256':digest(original),
        'audit':audit,'policy':rules,'command':None,'approval_digest':None,'evaluation':None,
        'training':None,'created_at':datetime.now(timezone.utc).isoformat()})
    return directory


def approval_digest(manifest):
    covered={k:manifest.get(k) for k in ('candidate_sha256','command','cwd','audit','policy')}
    return hashlib.sha256(json.dumps(covered,sort_keys=True,allow_nan=False).encode()).hexdigest()


def prepare(directory,argv,cwd):
    directory=Path(directory); manifest=read_json(directory/'manifest.json')
    if manifest['status'] not in ('proposed','prepared'): raise ValueError('Experiment is not preparable')
    if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv):
        raise ValueError('Nonempty argv list required')
    if str((directory/'candidate.toml').resolve()) not in argv:
        raise ValueError('Training command must consume the candidate snapshot')
    cwd=Path(cwd).resolve()
    if not cwd.is_dir(): raise ValueError('Working directory missing')
    manifest.update(command=argv,cwd=str(cwd),status='prepared')
    manifest['approval_digest']=approval_digest(manifest)
    write_json(directory/'manifest.json',manifest)
    return {'approval_digest':manifest['approval_digest'],'argv':argv,'cwd':str(cwd),
        'diff':(directory/'candidate.diff').read_text(),'preflight_valid':audit_valid(manifest['audit'])}


def execute(argv,cwd,confirmed=False,dry_run=False,timeout=1800,log_path=None):
    if not isinstance(argv,list) or not argv or not all(isinstance(x,str) for x in argv): raise ValueError('argv list required')
    if not finite(timeout) or not 0<timeout<=86400: raise ValueError('timeout must be 0 < seconds <= 86400')
    if dry_run: return {'status':'dry_run','argv':argv,'cwd':str(cwd),'spawned':False}
    if not confirmed: raise PermissionError('Human confirmation required before training')
    # shell=False and process group cleanup; stdout streams directly to file.
    with Path(log_path or Path(cwd)/'stdout.log').open('w') as log:
        child=subprocess.Popen(argv,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=child.wait(timeout=timeout)
            return {'status':'completed' if code==0 else 'failed','returncode':code,'spawned':True}
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            os.killpg(child.pid,signal.SIGTERM)
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL); child.wait()
            return {'status':'timeout' if isinstance(exc,subprocess.TimeoutExpired) else 'interrupted',
                'returncode':child.returncode,'spawned':True}


def run_experiment(directory,token=None,dry_run=False):
    directory=Path(directory); manifest=read_json(directory/'manifest.json')
    if manifest['status']!='prepared': raise ValueError('Experiment must be prepared; completed/failed runs cannot rerun')
    if digest(directory/'candidate.toml')!=manifest['candidate_sha256']: raise ValueError('Candidate changed since proposal')
    if digest(directory/'original.toml')!=manifest['original_sha256']: raise ValueError('Original snapshot modified')
    expected=approval_digest(manifest)
    if expected!=manifest['approval_digest']: raise ValueError('Command/audit/policy changed since preparation')
    if not dry_run:
        if manifest['policy']['mode'] not in ('controlled','auto_iterate'): raise PermissionError('Mode cannot train')
        if token!=expected: raise PermissionError('Confirm the exact reviewed approval digest')
        if not audit_valid(manifest['audit']): raise PermissionError('Complete model/controller audit required')
        if not manifest['policy'].get('calibrated',False): raise PermissionError('Calibrate evaluation policy before training')
    if dry_run:
        return execute(manifest['command'],manifest['cwd'],False,True,manifest['policy']['timeout_seconds'])
    # Exclusive execution prevents concurrent processes from launching the same candidate twice.
    lock=directory/'execution.lock'
    with lock.open('x') as f: f.write(expected)
    manifest['status']='running'; write_json(directory/'manifest.json',manifest)
    try:
        result=execute(manifest['command'],manifest['cwd'],True,False,
            manifest['policy']['timeout_seconds'],directory/'stdout.log')
    except Exception as exc:
        manifest['status']='failed'; manifest['training']={'status':'failed','error':str(exc)}
        write_json(directory/'manifest.json',manifest); raise
    manifest['training']=result; manifest['status']=result['status']
    write_json(directory/'manifest.json',manifest)
    from training_complete import enqueue
    event=enqueue(directory.parent/'queue',directory,result.get('returncode',1))
    result['completion_event']=str(event)
    return result


def artifact_valid(report,kind):
    path=Path(report.get(kind,'')); expected=report.get(kind+'_sha256')
    return path.is_file() and digest(path)==expected


def record_evaluation(directory,baseline,candidate):
    from evaluate_candidate import compare
    directory=Path(directory); manifest=read_json(directory/'manifest.json')
    result=compare(baseline,candidate,manifest['policy'])
    if not artifact_valid(baseline,'checkpoint') or not artifact_valid(baseline,'config'):
        result['reasons'].append('baseline checkpoint/config binding invalid')
    if baseline.get('config_sha256')!=manifest['original_sha256']:
        result['reasons'].append('baseline config differs from original experiment snapshot')
    if digest(directory/'original.toml')!=manifest['original_sha256']:
        result['reasons'].append('original snapshot changed')
    if not manifest.get('approval_digest') or approval_digest(manifest)!=manifest['approval_digest']:
        result['reasons'].append('approval binding changed or missing')
    if digest(directory/'candidate.toml')!=manifest['candidate_sha256']:
        result['reasons'].append('candidate snapshot changed after training')
    best_file=directory.parent/'best.json'
    if best_file.is_file():
        best_record=read_json(best_file)
        best_report=read_json(Path(best_record['experiment'])/'candidate_evaluation.json')
        if not artifact_valid(best_record,'checkpoint') or not artifact_valid(best_record,'config'):
            result['reasons'].append('current best artifact binding invalid')
        best_comparison=compare(best_report,candidate,manifest['policy'])
        if not best_comparison['accepted']:
            result['reasons'] += ['current best: '+r for r in best_comparison['reasons']]
    if manifest['status']!='completed': result['reasons'].append('training has not completed successfully')
    if not audit_valid(manifest['audit']): result['reasons'].append('model/controller audit incomplete or stale')
    if not manifest['policy'].get('calibrated',False): result['reasons'].append('example thresholds are not calibrated')
    cp=Path(candidate.get('checkpoint',''))
    if not cp.is_file(): result['reasons'].append('candidate checkpoint missing')
    if candidate.get('config_sha256')!=manifest['candidate_sha256']: result['reasons'].append('evaluation config hash mismatch')
    if cp.is_file() and candidate.get('checkpoint_sha256')!=digest(cp): result['reasons'].append('checkpoint hash mismatch')
    result['accepted']=not result['reasons']
    write_json(directory/'baseline_evaluation.json',baseline); write_json(directory/'candidate_evaluation.json',candidate)
    manifest['evaluation']=result; manifest['status']='accepted' if result['accepted'] else 'rejected'
    write_json(directory/'manifest.json',manifest)
    if result['accepted']:
        write_json(directory.parent/'best.json',{'experiment':str(directory.resolve()),'checkpoint':str(cp.resolve()),
            'checkpoint_sha256':digest(cp),'config':str((directory/'candidate.toml').resolve()),
            'config_sha256':manifest['candidate_sha256'],'evaluation':result})
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('create'); c.add_argument('--root',required=True); c.add_argument('--config',required=True)
    c.add_argument('--request',required=True); c.add_argument('--audit',required=True); c.add_argument('--policy')
    r=sub.add_parser('prepare'); r.add_argument('experiment'); r.add_argument('--argv-json',required=True); r.add_argument('--cwd',required=True)
    r=sub.add_parser('run'); r.add_argument('experiment'); r.add_argument('--confirm'); r.add_argument('--dry-run',action='store_true')
    r=sub.add_parser('evaluate'); r.add_argument('experiment'); r.add_argument('--baseline',required=True); r.add_argument('--candidate',required=True)
    a=p.parse_args()
    if a.action=='create': emit({'experiment':str(create_experiment(a.root,a.config,read_json(a.request),read_json(a.audit),policy(a.policy)))})
    elif a.action=='prepare': emit(prepare(a.experiment,read_json(a.argv_json),a.cwd))
    elif a.action=='run': emit(run_experiment(a.experiment,a.confirm,a.dry_run))
    else: emit(record_evaluation(a.experiment,read_json(a.baseline),read_json(a.candidate)))
