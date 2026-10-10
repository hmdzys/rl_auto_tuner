"""Detect source evidence without importing robot code; audit URDF statically."""
import math
import ast
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from common import digest, emit, finite, parser, read_json

SKIP = {'.git', '.agents', '.codex', '.venv', 'node_modules', '__pycache__', 'logs', 'experiments', '.cache'}


def detect(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'Project directory not found: {root}')
    evidence = {'isaac_lab': [], 'legged_gym': [], 'rsl_rl': []}
    configs, entrypoints, urdfs = [], [], []
    count = 0
    truncated = False
    for parent, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (Path(parent)/d).is_symlink())
        for name in sorted(files):
            path = Path(parent)/name
            if path.is_symlink():
                continue
            count += 1
            if count > 12000:
                truncated = True
                break
            if path.suffix == '.urdf': urdfs.append(str(path))
            if path.suffix in {'.toml', '.yaml', '.yml'}: configs.append(str(path))
            if path.suffix != '.py' or path.stat().st_size > 500000:
                continue
            text = path.read_text(errors='replace')
            try:
                tree=ast.parse(text)
            except SyntaxError:
                continue
            imports=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Import): imports.extend(x.name for x in node.names)
                elif isinstance(node,ast.ImportFrom) and node.module: imports.append(node.module)
            for framework, modules in {
                'isaac_lab': ('isaaclab','isaaclab_rl','isaaclab_tasks'),
                'legged_gym': ('legged_gym',),
                'rsl_rl': ('rsl_rl','isaaclab_rl.rsl_rl')
            }.items():
                if any(x==m or x.startswith(m+'.') for x in imports for m in modules) and len(evidence[framework])<12:
                    evidence[framework].append(str(path))
            if '__main__' in text and ('train' in name or name == 'mdog_loco.py'):
                entrypoints.append(str(path))
        if truncated: break
    version = (root/'VERSION').read_text().strip() if (root/'VERSION').is_file() else None
    git = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'], capture_output=True, text=True)
    return {'root':str(root), 'frameworks':[k for k,v in evidence.items() if v],
        'evidence':evidence, 'version':version, 'commit':git.stdout.strip() if git.returncode == 0 else None,
        'configs':configs[:50], 'entrypoints':entrypoints[:30], 'urdfs':urdfs[:30],
        'scan_truncated':truncated, 'status':'detected' if any(evidence.values()) else 'unknown'}


def audit_urdf(path, joint_order=None, defaults=None):
    path = Path(path).resolve()
    errors, observations = [], []
    robot = ET.parse(path).getroot()
    joints = {}
    for joint in robot.findall('joint'):
        if joint.get('type') == 'fixed': continue
        name = joint.get('name')
        if name in joints: errors.append(f'duplicate joint {name}')
        limits = joint.find('limit')
        record = {}
        if limits is None:
            errors.append(f'missing limits: {name}')
        else:
            for key in ('lower','upper','effort','velocity'):
                if joint.get('type') == 'continuous' and key in ('lower','upper'): continue
                try:
                    value = float(limits.get(key, 'nan'))
                    if not math.isfinite(value): raise ValueError()
                    record[key] = value
                except ValueError: errors.append(f'invalid {key}: {name}')
            if 'lower' in record and 'upper' in record and record['lower'] >= record['upper']:
                errors.append(f'inverted limits: {name}')
            for key in ('effort','velocity'):
                if record.get(key,0) <= 0: errors.append(f'nonpositive {key}: {name}')
        axis = joint.find('axis')
        try:
            xyz = [float(v) for v in (axis.get('xyz','1 0 0') if axis is not None else '1 0 0').split()]
            if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz) or sum(v*v for v in xyz) == 0:
                raise ValueError()
            record['axis'] = xyz
        except ValueError: errors.append(f'invalid axis: {name}')
        joints[name] = record
    if not joints: errors.append('no actuated joints')
    if joint_order is not None:
        if len(joint_order) != len(set(joint_order)): errors.append('joint mapping has duplicates')
        if set(joint_order) != set(joints): errors.append('joint mapping differs from URDF joints')
    if defaults is not None:
        if set(defaults) != set(joints): errors.append('default pose does not cover all joints')
        for name, value in defaults.items():
            limit = joints.get(name,{})
            if not finite(value) or not limit.get('lower',-math.inf) <= value <= limit.get('upper',math.inf):
                errors.append(f'default pose outside limits: {name}')
    for link in robot.findall('link'):
        mass = link.find('inertial/mass')
        if mass is not None:
            try:
                value = float(mass.get('value','nan'))
                if not math.isfinite(value) or value <= 0: raise ValueError()
            except ValueError: errors.append(f'invalid mass: {link.get("name")}')
    for mesh in robot.findall('.//mesh'):
        filename = mesh.get('filename','')
        if filename.startswith('package://'):
            observations.append(f'package mesh requires resolver: {filename}')
        else:
            mesh_path = Path(filename.removeprefix('file://'))
            if not mesh_path.is_absolute(): mesh_path = path.parent/mesh_path
            if not mesh_path.exists(): observations.append(f'unresolved mesh: {filename}')
    unknown = ['axis direction and physical joint order', 'converted USD/MJCF equivalence',
        'PD gains and torque saturation', 'action scaling and control dt',
        'default pose FK and ground clearance', 'COM, collision geometry and contact/friction model']
    if joint_order is None: unknown.append('runtime joint order missing')
    if defaults is None: unknown.append('expanded runtime default joint pose missing')
    return {'status':'blocked' if errors else 'review_required','urdf':str(path),'sha256':digest(path),
        'joint_count':len(joints),'joints':joints,'errors':errors,'observations':observations,'unknown':unknown}


if __name__ == '__main__':
    p=parser(__doc__); p.add_argument('project',type=Path); p.add_argument('--urdf',type=Path)
    p.add_argument('--robot-manifest',type=Path)
    args=p.parse_args(); result=detect(args.project)
    if args.urdf:
        m=read_json(args.robot_manifest) if args.robot_manifest else {}
        result['model_audit']=audit_urdf(args.urdf,m.get('joint_order'),m.get('default_joint_positions'))
    emit(result,args.output)
