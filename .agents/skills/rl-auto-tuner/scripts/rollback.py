"""Restore an original or recorded-best snapshot to a new file, preserving the project."""
from pathlib import Path
from common import digest, emit, parser, read_json


def restore(experiment,destination,best=False):
    experiment=Path(experiment); destination=Path(destination)
    if best:
        record=read_json(experiment/'best.json'); source=Path(record['config']); expected=record['config_sha256']
    else:
        record=read_json(experiment/'manifest.json'); source=experiment/'original.toml'; expected=record['original_sha256']
    if digest(source)!=expected: raise ValueError('Snapshot hash mismatch')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Never overwrite an existing configuration, even after resolving symlinks.
    with destination.open('xb') as f: f.write(source.read_bytes())
    return {'restored':str(destination.resolve()),'source':str(source.resolve()),'sha256':digest(destination)}


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('experiment'); p.add_argument('destination'); p.add_argument('--best',action='store_true')
    a=p.parse_args(); emit(restore(a.experiment,a.destination,a.best),a.output)
