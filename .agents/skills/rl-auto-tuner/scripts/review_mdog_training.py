"""Read-only mdog training preflight; CPU only, no simulator launch."""
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tomllib
import torch
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
SOURCE = args.source.resolve()
recommended = json.loads((SOURCE/'recommended_model.json').read_text())
checkpoint = Path(recommended['checkpoint'])
config = tomllib.loads(Path(recommended['config']).read_text())
default = tomllib.loads((SOURCE/'mdog_loco.toml').read_text())
saved = tomllib.loads((checkpoint.parent/'loco_input.toml').read_text())
state = torch.load(checkpoint, map_location='cpu', weights_only=False)
# Execute only the pure validator function, excluding framework imports and top-level code.
tree = ast.parse((SOURCE/'mdog_locomotion.py').read_text())
validator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_settings')
namespace = {'SETTINGS':config, 'STAGE':'flat', 'math':math}
exec(compile(ast.Module(body=[validator],type_ignores=[]), '<validator>', 'exec'), namespace)
namespace['validate_settings']()
spec = importlib.util.spec_from_file_location('review_rewards', SOURCE/'mdog_loco_math.py')
rewards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rewards)
air = torch.full((1,4),.2)
contact = torch.zeros((1,4),dtype=torch.bool)
moving = torch.ones(1,dtype=torch.bool)
clearance = rewards.clearance_score(torch.full((1,4),.08), contact, torch.ones(1,4), moving,.08,.02,air_time=air,max_air_time=.6).item()
probes = {
 'all_air_0_2s_clearance_weighted':clearance*config['weights']['clearance'],
 'all_air_0_2s_suspension_weighted':rewards.suspension_penalty(air,moving,.6).item()*config['gait']['suspension_weight'],
 'height_0_26m_weighted':(0.26-config['targets']['body_height'])**2*config['weights']['height'],
 'tilt_10deg_weighted':math.sin(math.radians(10))**2*config['weights']['upright'],
 'stationary_single_foot_hover_suspension':rewards.suspension_penalty(torch.tensor([[5.,0.,0.,0.]]),torch.tensor([False]),.6).item(),
}
assert probes['all_air_0_2s_clearance_weighted']>0
assert probes['all_air_0_2s_suspension_weighted']==0
assert probes['stationary_single_foot_hover_suspension']==0
assert tuple(state['actor_state_dict']['mlp.0.weight'].shape)==(512,270)
assert tuple(state['actor_state_dict']['mlp.6.weight'].shape)==(12,128)
events = EventAccumulator(str(checkpoint.parent),size_guidance={'scalars':0})
events.Reload()
reward_logs = {}
for tag in events.Tags()['scalars']:
 if tag.startswith('Episode_Reward/') or tag.startswith('Curriculum/'):
  points = events.Scalars(tag)[-30:]
  reward_logs[tag] = {'last_step':points[-1].step,'mean_last_30_logged_points':sum(p.value for p in points)/len(points)}
comparisons = [{k:v for k,v in item.items() if k in ('trial','case','mean_velocity_error_m_s','mean_body_height_m','body_tilt_rms_rad','no_support_fraction','feet','falls','seed','seconds','num_envs')} for item in json.loads((SOURCE/'comparison.json').read_text()) if item['trial'] in ('baseline','combined')]
hashes = {}
for name in ('mdog_loco.py','mdog_locomotion.py','mdog_loco_math.py','mdog_task.py','mdog_loco_evaluate.py'):
 path=SOURCE/name
 snapshot=checkpoint.parent/'source'/name
 hashes[name]={'current_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'snapshot_present':snapshot.is_file(),'matches_saved_source':path.read_bytes()==snapshot.read_bytes() if snapshot.is_file() else None}
result={'review_status':'review_required','simulation_started':False,'checkpoint':str(checkpoint),'config':recommended['config'],'validated_config':True,'default_config_differences':[{ 'section':s,'key':k,'default':default[s][k],'recommended':v} for s,items in config.items() for k,v in items.items() if default[s][k]!=v], 'saved_config_matches':config==saved,'source_hashes':hashes,'saved_iteration':state['iter'],'configured_learning_rate':config['training']['learning_rate'],'restored_optimizer_learning_rate':state['optimizer_state_dict']['param_groups'][0]['lr'],'reward_weights':config['weights'],'gait':config['gait'],'cpu_probes_weighted_before_dt':probes,'last_30_logged_reward_points':reward_logs,'existing_fixed_command_results':comparisons,'limits':['Existing single-seed flat-ground evaluation only; no new rollouts.','Force threshold contact proxy, not a calibrated flight safety criterion.','No full joint target/torque/saturation or action smoothness telemetry in evaluator.']}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:result[k] for k in ('review_status','validated_config','default_config_differences','saved_config_matches','restored_optimizer_learning_rate','cpu_probes_weighted_before_dt','source_hashes')},ensure_ascii=False,indent=2))
