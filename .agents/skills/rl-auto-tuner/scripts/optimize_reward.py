"""Generate constrained numeric overlays, not executable generated code."""
import difflib
from pathlib import Path
import re
import tomllib
from common import digest, emit, finite, parser, policy


def propose(config,parameter,factor,reason,rules=None):
    rules=rules or policy(); config=Path(config); section,key=parameter.split('.',1)
    if parameter not in rules['bounds']: raise ValueError(f'Parameter not allowed: {parameter}')
    if not finite(factor) or factor<=0 or abs(factor-1)>rules['max_relative_change']:
        raise ValueError('Relative change exceeds policy')
    if not reason.strip(): raise ValueError('Reason required')
    text=config.read_text(); values=tomllib.loads(text); old=values.get(section,{}).get(key)
    if not finite(old) or old==0: raise ValueError('Existing nonzero finite numeric parameter required')
    new=old*factor
    if isinstance(old,int): new=round(new)
    lower,upper=rules['bounds'][parameter]
    if not lower<=new<=upper or new*old<=0 or new==old: raise ValueError('Candidate outside bounds, flips sign or unchanged')
    # Replace one simple scalar assignment inside exactly one section, preserve comments.
    lines=text.splitlines(keepends=True); active=False; matches=0
    for i,line in enumerate(lines):
        heading=re.match(r'^\s*\[([^\[\]]+)\]\s*(?:#.*)?$',line.strip())
        if heading: active=heading.group(1)==section
        if active:
            match=re.match(r'^(\s*'+re.escape(key)+r'\s*=\s*)([^#\n]+)(.*)$',line.rstrip('\n'))
            if match:
                lines[i]=match.group(1)+repr(new)+' '+match.group(3)+ ('\n' if line.endswith('\n') else '')
                matches+=1
    if matches!=1: raise ValueError('Expected one simple TOML scalar assignment')
    candidate=''.join(lines); parsed=tomllib.loads(candidate)
    if parsed[section][key]!=new: raise ValueError('Overlay verification failed')
    return {'schema':1,'group':'reward' if section=='weights' else 'curriculum',
        'source':str(config.resolve()),'source_sha256':digest(config),
        'changes':[{'parameter':parameter,'old':old,'new':new,'reason':reason}],
        'candidate_text':candidate,'diff':''.join(difflib.unified_diff(text.splitlines(True),candidate.splitlines(True),
            fromfile='original.toml',tofile='candidate.toml'))}


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('config'); p.add_argument('parameter'); p.add_argument('factor',type=float)
    p.add_argument('--reason',required=True); p.add_argument('--policy'); a=p.parse_args()
    emit(propose(a.config,a.parameter,a.factor,a.reason,policy(a.policy)),a.output)
