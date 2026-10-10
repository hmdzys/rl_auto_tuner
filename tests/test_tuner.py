import copy
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(os.environ.get('RL_TUNER_SKILL', ROOT / '.agents/skills/rl-auto-tuner'))
sys.path.insert(0, str(SKILL / 'scripts'))


def healthy():
    return {'schema': 1, 'protocol': {'seeds': [42], 'scenarios': ['stand', 'forward'],
        'seconds': 30, 'num_envs': 4, 'terrain': 'flat', 'dt': 0.02,
        'settling_seconds': 1, 'model_hash': 'robot-a', 'control_hash': 'control-a'},
        'task': {'velocity_error': 0.08, 'yaw_error': 0.08},
        'pose': {'base_height_error': 0.01, 'roll_pitch_error': 0.05,
            'joint_limit_violations': 0, 'joint_pose_deviation': 0.1,
            'foot_slip_ratio': 0.02, 'gait_asymmetry': 0.08, 'action_smoothness': 0.02},
        'safety': {'fall_rate': 0, 'torque_saturation_ratio': 0.01},
        'coverage': {'samples': 1000, 'episodes': 12, 'scenario_seeds': [['stand',42],['forward',42]]}}


class TunerTests(unittest.TestCase):
    def test_missing_pose_never_passes(self):
        from evaluate_candidate import compare
        a = healthy(); b = healthy(); b['pose'].pop('action_smoothness')
        self.assertFalse(compare(a,b)['accepted'])

    def test_pose_regression_rejects_better_tracking(self):
        from evaluate_candidate import compare
        a = healthy(); b = healthy(); b['task']['velocity_error'] = 0.01
        b['pose']['roll_pitch_error'] = 0.3
        self.assertFalse(compare(a,b)['accepted'])

    def test_protocol_mismatch_rejected(self):
        from evaluate_candidate import compare
        a = healthy(); b = healthy(); b['protocol']['seeds'] = [43]
        self.assertFalse(compare(a,b)['accepted'])

    def test_valid_improvement_accepted(self):
        from evaluate_candidate import compare
        a = healthy(); b = healthy(); b['task']['velocity_error'] = 0.04
        self.assertTrue(compare(a,b)['accepted'])

    def test_nonfinite_not_accepted(self):
        from evaluate_candidate import compare
        b = healthy(); b['pose']['base_height_error'] = float('nan')
        self.assertFalse(compare(healthy(), b)['accepted'])

    def test_coverage_is_required(self):
        from evaluate_candidate import compare
        b = healthy(); b['coverage']['scenario_seeds'] = [['stand',42]]
        self.assertFalse(compare(healthy(),b)['accepted'])

    def test_pose_csv_uses_terrain_height_contacts_and_env_boundaries(self):
        from diagnose_pose import from_rows
        rows=[]
        for t in range(4):
            for env in range(2):
                rows.append({'env':env,'time_s':t*0.02,'base_height_m':1.33,
                    'ground_height_m':1.,'roll_rad':0.,'pitch_rad':0.,'command_speed_m_s':0.,
                    'joint_positions':[0.1], 'default_joint_positions':[0.],
                    'joint_lower':[-1.], 'joint_upper':[1.], 'actions':[float(env)],
                    'contacts':[1,1,1,1],'foot_speed_m_s':[0.2,0,0,0]})
        result=from_rows(rows,0.33)
        self.assertAlmostEqual(result['metrics']['base_height_error'],0.)
        self.assertAlmostEqual(result['metrics']['foot_slip_ratio'],0.25)
        self.assertAlmostEqual(result['metrics']['action_smoothness'],0.)

    def test_detect_empty_not_isaac_by_name(self):
        from detect_framework import detect
        with tempfile.TemporaryDirectory(prefix='IsaacLab-') as tmp:
            self.assertEqual(detect(Path(tmp))['frameworks'],[])

    def test_candidate_preserves_sign_and_source(self):
        from optimize_reward import propose
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.toml'; p.write_text('[weights]\nupright = -2.0\n')
            r=propose(p,'weights.upright',1.2,'tilt exceeds limit')
            self.assertAlmostEqual(r['changes'][0]['new'],-2.4)
            self.assertEqual(p.read_text(),'[weights]\nupright = -2.0\n')

    def test_unbounded_parameter_blocked(self):
        from optimize_reward import propose
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.toml'; p.write_text('[control]\nstiffness=40\n')
            with self.assertRaises(ValueError): propose(p,'control.stiffness',1.2,'bad')

    def test_preflight_blocks_joint_mapping_errors(self):
        from detect_framework import audit_urdf
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'r.urdf'; p.write_text('<robot name="r"><joint name="j" type="revolute"><limit lower="-1" upper="1" effort="10" velocity="20"/><axis xyz="0 0 0"/></joint></robot>')
            a=audit_urdf(p,['missing'],{'j':0.})
            self.assertEqual(a['status'],'blocked')

    def test_unconfirmed_run_and_dry_run_have_no_execution(self):
        from experiment_manager import execute
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'marker'
            argv=[sys.executable,'-c',f'open({str(marker)!r},"w").write("ran")']
            with self.assertRaises(PermissionError): execute(argv,Path(tmp),False,False,2)
            self.assertEqual(execute(argv,Path(tmp),False,True,2)['status'],'dry_run')
            self.assertFalse(marker.exists())

    def test_hook_records_failure_and_deduplicates(self):
        from training_complete import enqueue
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp); (r/'stdout.log').write_text('error')
            a=enqueue(r/'queue',r,3)
            b=enqueue(r/'queue',r,3)
            self.assertEqual(a,b)
            self.assertEqual(json.loads(a.read_text())['status'],'failed')
            self.assertEqual(len(list((r/'queue').glob('*.json'))),1)

    def test_experiment_rollback_restores_snapshot(self):
        from experiment_manager import create_experiment
        from rollback import restore
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.toml'; p.write_text('[weights]\nupright=-2.0\n')
            e=create_experiment(Path(tmp)/'experiments',p,{'parameter':'weights.upright','factor':1.2,'reason':'tilt'}, {'status':'passed'})
            out=Path(tmp)/'restored.toml'; restore(e,out)
            self.assertEqual(out.read_bytes(),p.read_bytes())

class BoundaryTests(unittest.TestCase):
    def test_invalid_protocol_numbers_rejected(self):
        from evaluate_candidate import compare
        a=healthy(); b=healthy(); b['task']['velocity_error']=.04
        for x in (a,b): x['protocol']['dt']=-0.02
        self.assertFalse(compare(a,b)['accepted'])

    def test_partial_action_stream_is_unknown(self):
        from diagnose_pose import from_rows
        rows=[{'time_s':0.,'actions':[0.]},{'time_s':.02}, {'time_s':.04,'actions':[0.]}]
        self.assertIsNone(from_rows(rows,.33)['metrics']['action_smoothness'])

    def test_array_wrong_order_and_negative_speed_unknown(self):
        from diagnose_pose import from_rows
        rows=[{'time_s':0.,'contacts':[1,1,1,1],'foot_speed_m_s':[-1.,0.,0.,0.]}]
        self.assertIsNone(from_rows(rows,.33)['metrics']['foot_slip_ratio'])

    def test_real_execution_timeout_and_exit_recorded(self):
        from experiment_manager import execute
        with tempfile.TemporaryDirectory() as tmp:
            r=execute([sys.executable,'-c','raise SystemExit(7)'],Path(tmp),True,False,2)
            self.assertEqual(r['status'],'failed'); self.assertEqual(r['returncode'],7)
            r=execute([sys.executable,'-c','import time; time.sleep(10)'],Path(tmp),True,False,.05)
            self.assertEqual(r['status'],'timeout')

    def test_scalars_nonfinite_invalid_not_converged(self):
        from analyze_training import analyze
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log.json'; p.write_text(json.dumps({'scalars':{'Train/mean_reward':[[0,float('nan')]]}}))
            r=analyze(p); self.assertEqual(r['status'],'invalid'); self.assertEqual(r['convergence'],'unknown')

    def test_curriculum_overlay_and_analysis_mode(self):
        from optimize_curriculum import propose_curriculum
        from experiment_manager import create_experiment
        from common import policy
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.toml'; p.write_text('[commands]\ninitial_fraction=0.35\n')
            r=propose_curriculum(p,'commands.initial_fraction',.8,'reduce speed difficulty')
            self.assertAlmostEqual(r['changes'][0]['new'],.28)
            rules=policy(); rules['mode']='analysis'
            with self.assertRaises(PermissionError):
                create_experiment(Path(tmp)/'e',p,{'parameter':'commands.initial_fraction','factor':.8,'reason':'difficulty'}, {}, rules)

    def test_tampered_candidate_cannot_execute(self):
        from experiment_manager import create_experiment,prepare,run_experiment
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.toml'; p.write_text('[weights]\nupright=-2.0\n')
            e=create_experiment(Path(tmp)/'e',p,{'parameter':'weights.upright','factor':1.2,'reason':'tilt'}, {})
            prepare(e,[sys.executable,'train.py','--config',str(e/'candidate.toml')],tmp)
            (e/'candidate.toml').write_text('[weights]\nupright=-8.0\n')
            with self.assertRaises(ValueError): run_experiment(e,dry_run=True)

    def test_dry_run_end_to_end(self):
        from dry_run import run
        with tempfile.TemporaryDirectory() as tmp:
            r=run(tmp)
            self.assertFalse(r['gpu_started']); self.assertFalse(r['execution']['spawned'])
            self.assertTrue(r['rollback_byte_identical'])
            self.assertTrue(r['healthy_improvement']['accepted']); self.assertFalse(r['pose_regression']['accepted'])

class PromotionTests(unittest.TestCase):
    def make_completed(self,tmp):
        from common import digest,policy,write_json,read_json
        from experiment_manager import AUDIT_CHECKS,create_experiment,prepare
        p=Path(tmp)/'input.toml'; p.write_text('[weights]\nupright=-2.0\n')
        audit={'status':'passed','reviewed_by':'test operator','checks':{k:True for k in AUDIT_CHECKS},
            'evidence':[{'path':str(p),'sha256':digest(p)}]}
        rules=policy(); rules['calibrated']=True
        e=create_experiment(Path(tmp)/'e',p,{'parameter':'weights.upright','factor':1.2,'reason':'tilt'},audit,rules)
        prepare(e,[sys.executable,'train.py','--config',str(e/'candidate.toml')],tmp)
        m=read_json(e/'manifest.json'); m['status']='completed'; write_json(e/'manifest.json',m)
        cp=e/'model.pt'; cp.write_bytes(b'fixture checkpoint')
        b=healthy(); b.update(checkpoint=str(cp),checkpoint_sha256=digest(cp),config=str(p),config_sha256=digest(p))
        c=healthy(); c['task']['velocity_error']=.04
        c.update(checkpoint=str(cp),checkpoint_sha256=digest(cp),config_sha256=digest(e/'candidate.toml'))
        return e,b,c

    def test_promotion_rechecks_config_snapshot(self):
        from experiment_manager import record_evaluation
        with tempfile.TemporaryDirectory() as tmp:
            e,b,c=self.make_completed(tmp)
            (e/'candidate.toml').write_text('[weights]\nupright=-9.0\n')
            self.assertFalse(record_evaluation(e,b,c)['accepted'])
            self.assertFalse((e.parent/'best.json').exists())

    def test_existing_best_not_replaced_by_worse_candidate(self):
        from experiment_manager import record_evaluation
        from common import write_json
        with tempfile.TemporaryDirectory() as tmp:
            e,b,c=self.make_completed(tmp)
            best=copy.deepcopy(c); best['task']['velocity_error']=.02
            best_dir=Path(tmp)/'best'; best_dir.mkdir()
            write_json(best_dir/'candidate_evaluation.json',best)
            write_json(e.parent/'best.json',{'experiment':str(best_dir)})
            self.assertFalse(record_evaluation(e,b,c)['accepted'])

class HookBoundaryTests(unittest.TestCase):
    def test_hook_cannot_launch_unbound_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'marker'
            p=subprocess.run([sys.executable,str(SKILL/'scripts/training_complete.py'),
                '--queue',str(Path(tmp)/'q'),'--run',str(Path(tmp)/'run'),'--confirm-training',
                '--',sys.executable,'-c',f'open({str(marker)!r},"w").write("x")'],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertFalse(marker.exists())

    def test_promotion_requires_original_baseline_binding(self):
        from experiment_manager import record_evaluation
        with tempfile.TemporaryDirectory() as tmp:
            e,b,c=PromotionTests().make_completed(tmp)
            b['checkpoint_sha256']='stale'
            self.assertFalse(record_evaluation(e,b,c)['accepted'])

class LifecycleTests(unittest.TestCase):
    def test_confirmed_simulated_training_evaluation_and_best(self):
        from common import digest,policy,read_json
        from experiment_manager import AUDIT_CHECKS,create_experiment,prepare,run_experiment,record_evaluation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/'input.toml';p.write_text('[weights]\nupright=-2.0\n')
            audit={'status':'passed','reviewed_by':'fixture operator','checks':{k:True for k in AUDIT_CHECKS},
                'evidence':[{'path':str(p),'sha256':digest(p)}]}
            rules=policy();rules['calibrated']=True
            e=create_experiment(root/'experiments',p,{'parameter':'weights.upright','factor':1.2,'reason':'tilt'},audit,rules)
            cp=e/'model.pt'; program=root/'simulate_train.py'
            program.write_text('from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_bytes(b"cpu fixture checkpoint")\n')
            r=prepare(e,[sys.executable,str(program),str(e/'candidate.toml'),str(cp)],root)
            with self.assertRaises(PermissionError):run_experiment(e)
            self.assertEqual(run_experiment(e,r['approval_digest'])['status'],'completed')
            with self.assertRaises(ValueError):run_experiment(e,r['approval_digest'])
            b=healthy(); b.update(checkpoint=str(cp),checkpoint_sha256=digest(cp),config=str(p),config_sha256=digest(p))
            c=healthy(); c['task']['velocity_error']=.04
            c.update(checkpoint=str(cp),checkpoint_sha256=digest(cp),config_sha256=digest(e/'candidate.toml'))
            result=record_evaluation(e,b,c)
            self.assertTrue(result['accepted'],result['reasons'])
            self.assertEqual(read_json(e.parent/'best.json')['checkpoint'],str(cp))
            self.assertTrue((e/'training_analysis.json').is_file())

    def test_malformed_protocol_rejected_without_crash(self):
        from evaluate_candidate import compare
        b=healthy();c=healthy();c['task']['velocity_error']=.04
        c['protocol']['seeds']=[{}]
        self.assertFalse(compare(b,c)['accepted'])

class ConfigBindingTests(unittest.TestCase):
    def test_unrelated_baseline_config_rejected(self):
        from common import digest
        from experiment_manager import record_evaluation
        with tempfile.TemporaryDirectory() as tmp:
            e,b,c=PromotionTests().make_completed(tmp)
            other=Path(tmp)/'other.toml';other.write_text('[weights]\nupright=-8.0\n')
            b.update(config=str(other),config_sha256=digest(other))
            self.assertFalse(record_evaluation(e,b,c)['accepted'])

    def test_mdog_height_uses_checkpoint_config_snapshot(self):
        from tune import inspect
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cp=root/'model.pt';cp.write_bytes(b'fixture')
            (root/'loco_input.toml').write_text('[targets]\nbody_height=0.30\n')
            config=root/'current.toml';config.write_text('[targets]\nbody_height=0.33\n')
            evaluation=root/'summary.json';evaluation.write_text(json.dumps({'checkpoint':str(cp),
                'mean_velocity_error_m_s':.1,'mean_body_height_m':.27,'feet':{}}))
            report=inspect(root,config,evaluation=evaluation)
            self.assertAlmostEqual(report['evaluation']['proxies']['mean_height_bias_m'],.03)

class DetectionEvidenceTests(unittest.TestCase):
    def test_documentation_strings_are_not_framework_evidence(self):
        from detect_framework import detect
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'readme.py').write_text('example = "from isaaclab.envs import ManagerBasedRLEnv"\n')
            self.assertEqual(detect(tmp)['frameworks'],[])
            (Path(tmp)/'task.py').write_text('from isaaclab.envs import ManagerBasedRLEnv\nfrom isaaclab_rl.rsl_rl import RslRlPpoAlgorithmCfg\n')
            self.assertEqual(set(detect(tmp)['frameworks']),{'isaac_lab','rsl_rl'})

if __name__ == '__main__': unittest.main()
