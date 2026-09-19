"""UTC intervals, cell-first aggregation and separate space/time completeness."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import calendar
import numpy as np
from .spatial import weighted_summary


def date(value):
    if isinstance(value,datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z","+00:00")).replace(tzinfo=timezone.utc)


def next_month(d):
    return d.replace(year=d.year+1,month=1,day=1) if d.month==12 else d.replace(month=d.month+1,day=1)


def interval_end(start, cadence):
    d=date(start)
    if cadence=="daily": return d+timedelta(days=1)
    if cadence=="dekadal":
        if d.day not in (1,11,21): raise ValueError("Invalid dekadal start")
        return d.replace(day=d.day+10) if d.day<21 else next_month(d)
    if cadence=="16day": return min(d+timedelta(days=16),d.replace(year=d.year+1,month=1,day=1))
    if cadence=="monthly": return next_month(d)
    raise ValueError("Unknown native interval")


def expected_count(start,end,cadence):
    cursor=date(start).replace(month=1,day=1,hour=0,minute=0,second=0,microsecond=0)
    n=0
    while cursor<date(end):
        finish=interval_end(cursor,cadence)
        n+= int(finish>date(start))
        cursor=finish
    return n


def aggregate_month(values, starts, ends, weights, aoi_area, start, end, method,
                    minimum_temporal=.9, minimum_spatial=.9):
    """Values are decoded, QA-masked observations. Missing is NaN, never zero."""
    start,end=date(start),date(end)
    starts,ends=list(map(date,starts)),list(map(date,ends))
    if len(starts)!=len(set(starts)) or len(starts)!=len(values):
        raise ValueError("Duplicate timestamps or mismatched native observations")
    order=sorted(zip(starts,ends),key=lambda p:p[0])
    if any(b<=a for a,b in order) or any(order[i][1]>order[i+1][0] for i in range(len(order)-1)):
        raise ValueError("Overlapping or invalid observation intervals")
    overlap=np.array([max(0,(min(b,end)-max(a,start)).total_seconds())/86400 for a,b in zip(starts,ends)])
    duration=np.array([(b-a).total_seconds()/86400 for a,b in zip(starts,ends)])
    shape=(-1,)+(1,)*(values.ndim-1)
    valid=np.isfinite(values) & (weights>0)
    covered=np.sum(valid*overlap.reshape(shape),axis=0)
    days=(end-start).total_seconds()/86400
    completeness=covered/days
    if method=="sum_amount":
        factors=np.divide(overlap,duration,out=np.zeros_like(overlap),where=duration>0)
    elif method in {"integrate_rate","duration_mean"}: factors=overlap
    else: raise ValueError("Unknown temporal aggregation")
    aggregated=np.sum(np.where(valid,values,0)*factors.reshape(shape),axis=0)
    if method=="duration_mean":
        aggregated=np.divide(aggregated,covered,out=np.full_like(aggregated,np.nan),where=covered>0)
    accepted=(completeness>=minimum_temporal-1e-10)&(covered>0)&(weights>0)
    aggregated[~accepted]=np.nan
    spatial=float(weights[accepted].sum()/aoi_area)
    temporal=float(np.sum(weights*completeness)/aoi_area)
    summary=weighted_summary(aggregated,weights)
    value=summary["mean"] if spatial>=minimum_spatial else None
    partial=bool(np.any(accepted & (completeness<1-1e-10)))
    flag="INSUFFICIENT_COVERAGE" if value is None else "PARTIAL_TOTAL" if partial and method!="duration_mean" else "PARTIAL_PERIOD" if partial else "OK"
    count=int(np.sum(np.any(valid.reshape(len(values),-1),axis=1)&(overlap>0)))
    return aggregated,dict(value=value,spatial_coverage_percentage=spatial*100,
        temporal_coverage_percentage=temporal*100,observation_count=count,quality_flag=flag,
        covered_days_area_weighted=temporal*days,expected_days=days)


def assert_unique_rows(rows):
    fields=("layer_id","variable","interval_start","interval_end","spatial_statistic",
            "temporal_aggregation","depth","management_code","climate_scenario")
    keys=[tuple(r.get(k) for k in fields) for r in rows]
    if len(keys)!=len(set(keys)): raise ValueError("Duplicate time-series keys")
