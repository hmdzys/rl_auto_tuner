"""Generate one bounded curriculum adjustment using the same transaction format."""
from common import emit, parser, policy
from optimize_reward import propose


def propose_curriculum(config,parameter,factor,reason,rules=None):
    if not parameter.startswith(('commands.','randomization.')): raise ValueError('Expected curriculum parameter')
    return propose(config,parameter,factor,reason,rules)


if __name__=='__main__':
    p=parser(__doc__); p.add_argument('config'); p.add_argument('parameter'); p.add_argument('factor',type=float)
    p.add_argument('--reason',required=True); p.add_argument('--policy'); a=p.parse_args()
    emit(propose_curriculum(a.config,a.parameter,a.factor,a.reason,policy(a.policy)),a.output)
