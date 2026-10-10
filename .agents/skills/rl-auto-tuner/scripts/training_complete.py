"""Training completion hook: analyze locally and enqueue feedback, without a desktop API."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from common import emit, parser, write_json
from analyze_training import analyze


def enqueue(queue,run,returncode):
    run=Path(run).resolve(); queue=Path(queue); queue.mkdir(parents=True,exist_ok=True)
    identifier=hashlib.sha256(str(run).encode()).hexdigest()[:24]
    event=queue/(identifier+'.json')
    if event.exists(): return event
    report=analyze(run)
    write_json(run/'training_analysis.json',report)
    data={'schema':1,'id':identifier,'run':str(run),'returncode':returncode,
        'status':'ready_for_review' if returncode==0 else 'failed','consumed':False,
        'analysis':str(run/'training_analysis.json'),'created_at':datetime.now(timezone.utc).isoformat(),
        'next_action':'Codex reads report and pose evidence; controlled mode proposes a diff and awaits training confirmation.'}
    # Exclusive create makes duplicate callback events harmless.
    import json
    try:
        with event.open('x') as f: json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False)
    except FileExistsError: pass
    return event


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('--queue',required=True,type=Path); p.add_argument('--run',required=True,type=Path)
    p.add_argument('--returncode',required=True,type=int); p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if not a.run.is_dir(): p.error('--run must be an existing completed run directory')
    if a.dry_run: emit({'status':'dry_run','run':str(a.run),'queue':str(a.queue)},a.output)
    else: emit({'event':str(enqueue(a.queue,a.run,a.returncode))},a.output)
