import csv,io,json,urllib.request,urllib.parse,datetime,pathlib,os,time
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"docs"/"data.json"
NOW=datetime.datetime.now(datetime.timezone.utc)
CATALOG=[
("hy","美國高收益債利差","信用","FRED","daily"),("ig","美國投資等級債利差","信用","FRED","daily"),("vix","VIX","信用","FRED","daily"),("us10y","美國10年期公債殖利率","信用","FRED","daily"),("nfci","芝加哥金融情勢指數","信用","FRED","weekly"),
("indices","S&P 500 / Nasdaq 100","美股","Yahoo Finance 非官方","daily"),("breadth","市場廣度與半導體相對強弱","美股","待授權","daily"),("prime","高盛 Prime Book AI 資金流","美股","高盛授權報告","weekly"),("supply","美股回購與IPO供給","美股","SEC/交易所","monthly"),
("capex","AI 巨頭資本支出指引","AI","公司季報","quarterly"),("fcf","AI 巨頭自由現金流","AI","公司季報","quarterly"),("eps","Nasdaq 100 EPS 預估修正","AI","需授權一致預估","weekly"),("airev","AI晶片與雲端營收","AI","公司財報","quarterly"),
("margin","台股融資餘額","台股","TWSE/TPEx","daily"),("maint","台股融資維持率","台股","待驗證","daily"),("inst","三大法人及期貨部位","台股","TWSE/TAIFEX","daily"),("taiex","台股回撤與成交量","台股","Yahoo Finance 非官方","daily"),("fx","美元兌新台幣與美元指數","匯率","Yahoo Finance 非官方","daily")]
FRED={"hy":"BAMLH0A0HYM2","ig":"BAMLC0A0CM","vix":"VIXCLS","us10y":"DGS10","nfci":"NFCI"}
YAHOO={"ndx":"%5ENDX","spx":"%5EGSPC","tw":"%5ETWII","twd":"TWD%3DX","sox":"%5ESOX","dxy":"DX-Y.NYB"}
def fetch(url):
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=16) as r:return r.read().decode()
def fred(series):
 # FRED original feed is preferred. A recent-date filter avoids downloading decades of CSV.
 since=(NOW-datetime.timedelta(days=130)).date().isoformat()
 primary="https://fred.stlouisfed.org/graph/fredgraph.csv?id="+series+"&cosd="+since
 errors=[]
 for attempt in range(2):
  try:
   req=urllib.request.Request(primary,headers={"User-Agent":"Mozilla/5.0","Accept":"text/csv"})
   with urllib.request.urlopen(req,timeout=9) as response:
    data=csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")))
   rows=[]
   for r in data:
    try:rows.append((r.get("DATE") or r.get("observation_date"),float(r[series])))
    except (ValueError,TypeError,KeyError):pass
   if rows:return rows,"FRED"
   raise ValueError("FRED CSV has no numeric observations")
  except Exception as exc:
   errors.append(type(exc).__name__)
   if attempt==0:time.sleep(1)
 # DBnomics mirrors FRED observations. It is a fallback, not an official real-time feed.
 try:
  url="https://api.db.nomics.world/v22/series/FRED/"+series+"?observations=1"
  j=json.loads(fetch(url))
  doc=j["series"]["docs"][0]
  rows=[]
  for date,value in zip(doc["period"],doc["value"]):
   try:rows.append((date,float(value)))
   except (TypeError,ValueError):pass
  rows=[(d,v) for d,v in rows if d>=since]
  if rows:return rows,"DBnomics (FRED mirror)"
  raise ValueError("DBnomics has no recent numeric observations")
 except Exception as exc:
  errors.append("DBnomics:"+type(exc).__name__)
  raise RuntimeError("; ".join(errors))
def yahoo(symbol):
 j=json.loads(fetch("https://query1.finance.yahoo.com/v8/finance/chart/"+symbol+"?range=1y&interval=1d"))["chart"]["result"][0]
 return [(datetime.datetime.fromtimestamp(t,datetime.timezone.utc).strftime("%Y-%m-%d"),float(v)) for t,v in zip(j["timestamp"],j["indicators"]["quote"][0]["close"]) if v is not None]
def entry(rows,url,unit=""):
 if not rows:raise ValueError("empty source")
 return {"status":"ok","value":round(rows[-1][1],3),"date":rows[-1][0],"unit":unit,"source_url":url,"history":[{"date":d,"value":round(v,3)} for d,v in rows[-90:]]}
def telegram(msg):
 token=os.getenv("TELEGRAM_BOT_TOKEN");chat=os.getenv("TELEGRAM_CHAT_ID")
 if not token or not chat:return False
 data=urllib.parse.urlencode({"chat_id":chat,"text":msg}).encode()
 req=urllib.request.Request("https://api.telegram.org/bot"+token+"/sendMessage",data=data,method="POST")
 with urllib.request.urlopen(req,timeout=12) as r:return r.status==200
def main():
 try:old=json.loads(OUT.read_text())
 except (FileNotFoundError,ValueError):old={}
 previous=old.get("active_alerts",{})
 metrics={k:{"name":n,"group":g,"source":s,"frequency":f,"status":"unavailable","reason":"尚未接入可靠來源"} for k,n,g,s,f in CATALOG}
 def fetch_one_fred(item):
  k,series=item
  rows,provider=fred(series)
  e=entry(rows,"https://fred.stlouisfed.org/series/"+series,"index" if k in ("nfci","vix") else "%")
  e["provider"]=provider
  if provider.startswith("DBnomics"):e["mirror_url"]="https://db.nomics.world/FRED/"+series
  if k=="hy" and len(rows)>20:e["change20bp"]=round((rows[-1][1]-rows[-21][1])*100,1)
  return k,e
 with ThreadPoolExecutor(max_workers=5) as pool:
  futures={pool.submit(fetch_one_fred,item):item[0] for item in FRED.items()}
  for future in as_completed(futures):
   k=futures[future]
   try:
    _,e=future.result()
    metrics[k].update(e)
    print("FRED",k,e["provider"],e["date"],e["value"],flush=True)
   except Exception as exc:
    metrics[k]["reason"]="來源錯誤："+str(exc)[:150]
    print("FRED",k,"unavailable",str(exc)[:150],flush=True)
 prices={}
 for k,s in YAHOO.items():
  try:prices[k]=yahoo(s)
  except Exception:pass
 if "ndx" in prices:
  a=prices["ndx"];high=max(v for _,v in a);e=entry(a,"https://finance.yahoo.com/quote/%5ENDX/","points")
  e["drawdown_pct"]=round(100*(high-a[-1][1])/high,2);e["reference"]="近一年最高收盤價"
  if "spx" in prices:e["spx"]=round(prices["spx"][-1][1],2)
  metrics["indices"].update(e)
 if "tw" in prices:
  a=prices["tw"];high=max(v for _,v in a);e=entry(a,"https://finance.yahoo.com/quote/%5ETWII/","points")
  e["drawdown_pct"]=round(100*(high-a[-1][1])/high,2);e["reference"]="近一年最高收盤價"
  metrics["taiex"].update(e)
 if "twd" in prices:
  metrics["fx"].update(entry(prices["twd"],"https://finance.yahoo.com/quote/TWD=X/","TWD per USD"))
  if "dxy" in prices:metrics["fx"]["dxy"]=round(prices["dxy"][-1][1],2)
 if "sox" in prices and "ndx" in prices:
  metrics["breadth"].update({"status":"partial","value":round(prices["sox"][-1][1]/prices["ndx"][-1][1],4),"date":min(prices["sox"][-1][0],prices["ndx"][-1][0]),"unit":"SOX/NDX","reason":"只有半導體相對強弱，市場廣度未取得","source_url":"https://finance.yahoo.com/quote/%5ESOX/"})
 alerts={}
 for prefix,k in [("hy","hy"),("vix","vix"),("ndx","indices"),("tw","taiex")]:
  if metrics[k]["status"]!="ok":alerts.update({key:v for key,v in previous.items() if key.startswith(prefix)})
 def rule(key,trigger,severity,message):
  if trigger:alerts[key]={"severity":severity,"message":message,"first_seen":previous.get(key,{}).get("first_seen",NOW.isoformat())}
 h=metrics["hy"];v=metrics["vix"];n=metrics["indices"];t=metrics["taiex"]
 if h["status"]=="ok":
  rule("hy4",h["value"]>=4,"warning","HY OAS ≥4%："+str(h["value"])+"%")
  if "change20bp" in h:rule("hy75",h["change20bp"]>=75,"warning","HY OAS 20交易日擴大 ≥75bp："+str(h["change20bp"])+"bp")
 if v["status"]=="ok":
  for threshold in (25,35):rule("vix"+str(threshold),v["value"]>=threshold,"critical" if threshold==35 else "warning","VIX ≥"+str(threshold)+"："+str(v["value"]))
 if n["status"]=="ok":
  for threshold in (10,20):rule("ndx"+str(threshold),n["drawdown_pct"]>=threshold,"critical" if threshold==20 else "warning","Nasdaq 100 近一年高點回撤 ≥"+str(threshold)+"%："+str(n["drawdown_pct"])+"%")
 if t["status"]=="ok":
  for threshold in (5,10,15,20,25):rule("tw"+str(threshold),t["drawdown_pct"]>=threshold,"critical" if threshold>=20 else "warning","台股近一年高點回撤 ≥"+str(threshold)+"%："+str(t["drawdown_pct"])+"%")
 pending=old.get("pending_notifications",[])
 for key,a in alerts.items():
  if key not in previous and not any(x["key"]==key for x in pending):pending.append({"key":key,"message":a["message"]})
 if pending:
  try:
   if telegram("全球金融風險雷達\n"+"\n".join("• "+p["message"] for p in pending)+"\n詳情請查看儀表板"):pending=[]
  except Exception as exc:print("Telegram delivery failed:",type(exc).__name__)
 payload={"updated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"metrics":metrics,"active_alerts":alerts,"pending_notifications":pending,"notes":["無資料不代表安全；免費端點可能延遲或停用","回撤基準：近一年最高收盤價，非個人45,211點加碼基準","18項已列示，但尚未全部完成資料串接"]}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2))
 print("Updated:",sum(m["status"]=="ok" for m in metrics.values()),"full metrics;",len(alerts),"active alerts")
if __name__=="__main__":main()
