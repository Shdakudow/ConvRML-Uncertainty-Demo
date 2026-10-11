"""Finite-candidate quantile selection with simultaneous image-level HB bounds.

No monotonicity assumption: every candidate has a simultaneous certificate.
Quantile grids must be fixed independently of the calibration/test labels.
"""
import numpy as np
from scripts.rcps_bounds import hb_pvalue

LOWER_GRID = np.array([.0001, .001, .005, .01, .015, .02, .025, .03,
                       .04, .05, .06, .075, .1, .15, .2, .3, .4, .49])
UPPER_GRID = 1-LOWER_GRID[::-1]

def upper_risk_bound(empirical_risk, n, delta):
    if not 0 <= empirical_risk <= 1 or n < 1 or not 0 < delta < 1:
        raise ValueError('Invalid risk confidence arguments')
    if empirical_risk == 1: return 1.
    lo, hi = float(empirical_risk), 1.-1e-12
    if hb_pvalue(empirical_risk, n, hi) >= delta: return 1.
    for _ in range(70):
        mid = (lo+hi)/2
        if hb_pvalue(empirical_risk, n, mid) < delta: hi = mid
        else: lo = mid
    return min(1., hi+1e-10)

def select_fixed_sequence(lower_losses, upper_losses, lower_means, upper_means,
                          lower_q=LOWER_GRID, upper_q=UPPER_GRID, alpha=.1, delta=.05):
    """Predeclared wide-to-narrow tests; stop each tail at its first failure.

    The chance of rejecting the first true null is <= delta/2 per tail,
    so no Bonferroni penalty over q is required. No model monotonicity claim.
    """
    lo,hi=np.asarray(lower_losses),np.asarray(upper_losses)
    if lo.ndim!=2 or hi.ndim!=2 or lo.shape[0]!=hi.shape[0] or lo.shape[1]!=len(lower_q) or hi.shape[1]!=len(upper_q):
        raise ValueError('Grid shape mismatch')
    if not np.all(np.diff(lower_q)>0) or not np.all(np.diff(upper_q)>0):raise ValueError('Grid must be sorted')
    if not all(np.isfinite(v).all() for v in [lo,hi,lower_means,upper_means]):raise ValueError('Nonfinite scores')
    if not 0<alpha<1 or not 0<delta<1 or np.any(lo<0) or np.any(hi<0) or np.any(lo>1) or np.any(hi>1):raise ValueError('Invalid risks')
    selections=[];traces=[]
    for losses,order in [(lo,range(len(lower_q))),(hi,range(len(upper_q)-1,-1,-1))]:
        selected=None;trace=[]
        for j in order:
            risk=float(losses[:,j].mean());pv=hb_pvalue(risk,len(losses),alpha/2)
            passed=pv<delta/2;trace.append(dict(index=j,risk=risk,pvalue=pv,passed=passed))
            if not passed:break
            selected=j
        if selected is None:raise ValueError('No quantile pair passes fixed-sequence certification')
        selections.append(selected);traces.append(trace)
    i,j=selections
    lu=upper_risk_bound(float(lo[:,i].mean()),len(lo),delta/2)
    uu=upper_risk_bound(float(hi[:,j].mean()),len(hi),delta/2)
    return dict(lower_q=float(lower_q[i]),upper_q=float(upper_q[j]),lower_index=i,upper_index=j,
        alpha=alpha,delta=delta,per_tail_delta=delta/2,n_images=len(lo),
        lower_risk_ucb=lu,upper_risk_ucb=uu,total_risk_ucb=lu+uu,
        calibration_width=float(upper_means[j]-lower_means[i]),calibration_coverage=float(1-lo[:,i].mean()-hi[:,j].mean()),
        traces=traces,ucb_interpretation='Pointwise UCB inversions are diagnostic only after fixed-sequence selection; the selection guarantee is at the predeclared alpha/2 per tail, not at the smaller numerical UCB values.',
        policy='Fixed-sequence HB tests in predeclared q order, broad to narrow. Stop at first failure per tail; choose last passing q. Alpha/2 and delta/2 per tail. No test selection.')

def select_pair(lower_losses, upper_losses, lower_means, upper_means,
                lower_q=LOWER_GRID, upper_q=UPPER_GRID, alpha=.1, delta=.05):
    lo, hi = np.asarray(lower_losses), np.asarray(upper_losses)
    if lo.ndim != 2 or hi.ndim != 2 or lo.shape[0] != hi.shape[0]:
        raise ValueError('Expected image-by-quantile losses')
    if lo.shape[1] != len(lower_q) or hi.shape[1] != len(upper_q):
        raise ValueError('Grid shape mismatch')
    if not all(np.isfinite(v).all() for v in [lo,hi,lower_means,upper_means]):
        raise ValueError('Nonfinite scores')
    if not 0 < alpha < 1 or not 0 < delta < 1 or np.any(lo<0) or np.any(hi<0) or np.any(lo>1) or np.any(hi>1):
        raise ValueError('Invalid risks')
    budget = delta/(len(lower_q)+len(upper_q))
    lower_ucb = np.array([upper_risk_bound(r,len(lo),budget) for r in lo.mean(0)])
    upper_ucb = np.array([upper_risk_bound(r,len(hi),budget) for r in hi.mean(0)])
    width = np.asarray(upper_means)[None,:]-np.asarray(lower_means)[:,None]
    certified = lower_ucb[:,None]+upper_ucb[None,:] <= alpha
    if not certified.any(): raise ValueError('No quantile pair passes the simultaneous risk bound')
    score = np.where(certified, width, np.inf)
    i,j = np.unravel_index(np.argmin(score),score.shape)
    return dict(lower_q=float(lower_q[i]),upper_q=float(upper_q[j]),lower_index=int(i),upper_index=int(j),
        alpha=alpha,delta=delta,per_candidate_delta=budget,n_images=len(lo),
        lower_risk_ucb=float(lower_ucb[i]),upper_risk_ucb=float(upper_ucb[j]),
        total_risk_ucb=float(lower_ucb[i]+upper_ucb[j]),calibration_width=float(width[i,j]),
        calibration_coverage=float(1-lo[:,i].mean()-hi[:,j].mean()),
        lower_ucb=lower_ucb.tolist(),upper_ucb=upper_ucb.tolist(),
        feasible_pairs=int(certified.sum()),candidate_pairs=int(certified.size),
        policy='Minimum calibration mean width among simultaneously HB-certified quantile pairs. Bonferroni across all endpoint candidates; total tail-risk UCB <= alpha. No fixed tail allocation or q-gap. No test selection.')
