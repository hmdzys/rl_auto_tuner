"""Read scalar exports or TensorBoard without loading checkpoint pickles."""
import csv
import json
from pathlib import Path


def load_scalars(path):
    path=Path(path)
    if path.is_file() and path.suffix == '.json':
        data=json.loads(path.read_text())
        return data.get('scalars',data)
    if path.is_file() and path.suffix == '.csv':
        result={}
        with path.open() as f:
            for row in csv.DictReader(f):
                result.setdefault(row['tag'],[]).append([int(row['step']),float(row['value'])])
        return result
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ImportError as e:
        raise RuntimeError('TensorBoard unavailable in this Python; use training venv Python or export tag,step,value CSV.') from e
    accumulator=EventAccumulator(str(path),size_guidance={'scalars':0}).Reload()
    return {tag:[[x.step,x.value] for x in accumulator.Scalars(tag)] for tag in accumulator.Tags()['scalars']}


def checkpoints(root):
    # Never torch.load an untrusted checkpoint just to inspect its metadata.
    return [{'path':str(p),'bytes':p.stat().st_size,'mtime':p.stat().st_mtime}
        for p in sorted(Path(root).glob('model_*.pt'))]
