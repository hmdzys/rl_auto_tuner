"""Shared serialization and CLI boundaries. No simulator imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy(path=None):
    # JSON is a YAML subset; use stdlib rather than an implicit PyYAML dependency.
    return read_json(path or SKILL / 'config/tuning_policy.yaml')


def emit(value, output=None):
    if output:
        write_json(output, value)
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def parser(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument('--output', type=Path)
    return p
