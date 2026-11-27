"""Fat sheep P0 research screening. No network, deployment or trading side effects.
Input JSON: list of normalized records, each with as_of, membership_verified,
index, industry_status (eligible/excluded/review), listing_date, price,
annual (five consecutive fiscal years with eps, roe in percent, dividend,
available_date), quarters (eight consecutive quarters oldest first with year,
quarter, eps, net_income, available_date). Per-share values must be adjusted
to current share basis. Dividend refers to fiscal year. Dates ISO YYYY-MM-DD.
"""
import json, sys, math
from datetime import date, timedelta
from statistics import mean

def screen(r):
    def result(status, reason, **kw):
        return dict(stock_id=r.get("stock_id"), status=status, reason=reason, **kw)
    def num(v):
        return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    try:
        d=date.fromisoformat(r["as_of"])
        if r.get("index") not in ("0050","0051") or r.get("membership_verified") is not True:
            return result("NA","membership_unverified")
        if r.get("industry_status")=="excluded": return result("X","industry_or_KY")
        if r.get("industry_status")!="eligible": return result("NA","industry_review")
        listed=date.fromisoformat(r["listing_date"])
        if (d.year-listed.year, d.month,d.day)<(5,listed.month,listed.day):
            return result("X","listing_under_five_years")
        a=r["annual"]; q=r["quarters"]; p=r["price"]
        if r.get("share_basis_verified") is not True: return result("NA","share_basis_unverified")
        if len(a)!=5 or len(q)!=8 or not num(p) or p<=0: return result("NA","incomplete_data")
        years=[x["year"] for x in a]
        if years!=list(range(years[0],years[0]+5)) or years[-1]>=d.year:
            return result("NA","annual_period_gap")
        periods=[x["year"]*4+x["quarter"] for x in q]
        if any(x["quarter"] not in (1,2,3,4) for x in q) or periods!=list(range(periods[0],periods[0]+8)):
            return result("NA","quarter_period_gap")
        # Conservative freshness gate for calendar-year issuers; not publication evidence.
        last_annual = d.year - (1 if (d.month,d.day)>=(5,1) else 2)
        if years[-1] < last_annual:
            return result("NA","stale_annual")
        def quarter_end(y,k):
            return date(y, (3,6,9,12)[k-1], (31,30,30,31)[k-1])
        eligible = [y*4+k for y in range(d.year-2,d.year+1) for k in range(1,5)
                    if quarter_end(y,k)+timedelta(days=90 if k==4 else 45)<=d]
        if periods[-1]<max(eligible):
            return result("NA","stale_quarters")
        if any(quarter_end(x["year"],x["quarter"])>d for x in q):
            return result("NA","future_period")
        if any(date.fromisoformat(x["available_date"])<date(x["year"],12,31) for x in a) or any(date.fromisoformat(x["available_date"])<quarter_end(x["year"],x["quarter"]) for x in q):
            return result("NA","invalid_available_date")
        if any(date.fromisoformat(x["available_date"])>d for x in a+q):
            return result("NA","future_information")
        if not all(num(x[k]) for x in a for k in ("eps","roe","dividend")) or not all(num(x[k]) for x in q for k in ("eps","net_income")):
            return result("NA","invalid_financial_values")
        if any(x["dividend"]<0 for x in a): return result("NA","invalid_dividend")
        if min(x["eps"] for x in a)<=0 or min(x["roe"] for x in a)<3 or mean(x["roe"] for x in a)<8:
            return result("X","historical_quality")
        eps=sum(x["eps"] for x in q[-4:]); prev=sum(x["net_income"] for x in q[:4]); now=sum(x["net_income"] for x in q[-4:])
        if prev<=0: return result("NA","nonpositive_comparison_base")
        growth=(now-prev)/prev
        if eps<=0 or now<=0: return result("X","current_loss")
        pe=p/eps; y1=a[-1]["dividend"]/p; y5=mean(x["dividend"] for x in a)/p
        cap=min(15*eps,a[-1]["dividend"]/.04,mean(x["dividend"] for x in a)/.04)
        metrics=dict(pe=pe,yield_latest=y1,yield_five=y5,growth=growth,normal_pe=p/mean(x["eps"] for x in a),qualified_price=cap)
        if growth<-.2: return result("R","earnings_decline",**metrics)
        if pe>15 or y1<.04 or y5<.04: return result("W","valuation_or_yield",**metrics)
        grade=next(g for limit,g in [(8,"SSS"),(10,"SS"),(12,"S"),(15,"A")] if pe<=limit)
        return result("candidate","P0_pass_disaster_not_certified",grade=grade+("+" if growth>0 else "-" if growth<0 else "="),**metrics)
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):
        return result("NA","missing_or_invalid_input")

if __name__=="__main__":
    records=json.load(sys.stdin)
    print(json.dumps([screen(r) for r in records],ensure_ascii=False,indent=2,allow_nan=False))
