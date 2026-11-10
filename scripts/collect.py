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
# Fixed monthly-friendly request ceiling; all HTTP requests, including fallbacks and alerts, are counted.
MAX_REQUESTS=int(os.getenv("MAX_REQUESTS_PER_RUN","25"))
MAX_RETRIES=0
STATS={"requests":0,"success":0,"failure":0,"by_host":{},"errors":[],"skipped":[]}
def fetch(url,timeout=9):
 host=urllib.parse.urlparse(url).hostname or "unknown"
 last=None
 for attempt in range(MAX_RETRIES+1):
  if STATS["requests"]>=MAX_REQUESTS:raise RuntimeError("request_budget_exceeded")
  STATS["requests"]+=1
  STATS["by_host"][host]=STATS["by_host"].get(host,0)+1
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/csv,*/*"})
   with urllib.request.urlopen(req,timeout=timeout) as r:body=r.read().decode("utf-8-sig")
   STATS["success"]+=1
   return body
  except Exception as exc:
   STATS["failure"]+=1
   last=exc
   STATS["errors"].append(host+":"+type(exc).__name__)
   if attempt<MAX_RETRIES:time.sleep(0.5)
 raise last
def due(old,key,hours):
 oldmetric=old.get("metrics",{}).get(key,{})
 stamp=oldmetric.get("checked_at")
 if not stamp:return True
 try:return (NOW-datetime.datetime.fromisoformat(stamp)).total_seconds()>=hours*3600
 except (TypeError,ValueError):return True
def cached(metrics,old,key):
 oldmetric=old.get("metrics",{}).get(key)
 if oldmetric and oldmetric.get("status") in ("ok","partial"):
  metrics[key]=dict(oldmetric)
  metrics[key]["cache_status"]="cached"
  return True
 return False
def fred(series):
 since=(NOW-datetime.timedelta(days=130)).date().isoformat()
 key=os.getenv("FRED_API_KEY","").strip()
 if not key:raise RuntimeError("FRED_API_KEY_missing")
 params=urllib.parse.urlencode({"series_id":series,"api_key":key,"file_type":"json","observation_start":since})
 url="https://api.stlouisfed.org/fred/series/observations?"+params
 # Never log the full request URL: it contains the private API key.
 raw=fetch(url,timeout=12)
 obj=json.loads(raw)
 if "error_code" in obj:raise RuntimeError("FRED_API_error_"+str(obj["error_code"]))
 rows=[]
 for item in obj.get("observations",[]):
  try:rows.append((item["date"],float(item["value"])))
  except (ValueError,TypeError,KeyError):pass
 if not rows:raise ValueError("FRED_empty_observations")
 return rows,"FRED official API"
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

# Taiwan official public-data endpoints; field mappings are validated before publishing values.
TW_ENDPOINTS={
 "margin":"https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
 "cash_inst":"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json",
 "tw_price":"https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK",
 "futures":"https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate",
}
def num(value):
 if value is None:return None
 try:return float(str(value).replace(",","").replace("%","").strip())
 except (ValueError,TypeError):return None
def pick(row,*names):
 for name in names:
  if name in row and row[name] not in (None,"","--","-"):return row[name]
 return None
def date_of(row):
 raw=str(pick(row,"Date","date","日期","交易日期","日期(交易日)") or "")
 if len(raw)==8 and raw.isdigit():return raw[:4]+"-"+raw[4:6]+"-"+raw[6:]
 if "/" in raw:
  p=raw.split("/")
  if len(p)==3 and all(v.isdigit() for v in p):
   year=int(p[0]);return f"{year+1911 if year<1911 else year:04d}-{int(p[1]):02d}-{int(p[2]):02d}"
 return raw[:10] if len(raw)>=10 else ""
def official_rows(url):
 obj=json.loads(fetch(url,timeout=12))
 if isinstance(obj,list):return obj
 if isinstance(obj,dict):
  for field in ("data","Data","records"):
   if isinstance(obj.get(field),list):
    rows=obj[field]
    if obj.get("fields") and all(isinstance(x,list) for x in rows):return [dict(zip(obj["fields"],x)) for x in rows]
    if all(isinstance(x,list) and len(x)==4 for x in rows):return [dict(zip(("單位名稱","買進金額","賣出金額","買賣差額"),x)) for x in rows]
    return rows
 raise ValueError("unexpected_official_schema")
def taiwan(metrics,old):
 # At most four official calls per 24h; preserve previously verified snapshots on failure.
 for kind,url in TW_ENDPOINTS.items():
  key="margin" if kind=="margin" else ("taiex" if kind=="tw_price" else "inst")
  stamp=old.get("source_checks",{}).get("tw_"+kind)
  if stamp:
   try:
    if (NOW-datetime.datetime.fromisoformat(stamp)).total_seconds()<86400:continue
   except ValueError:pass
   continue
  try:
   rows=official_rows(url)
   if not rows:raise ValueError("empty_official_data")
   record={"checked_at":NOW.isoformat(),"source_url":url,"records":len(rows),"sample_fields":list(rows[0])[:30]}
   if kind=="margin":
    # MI_MARGN may contain both market totals and per-security records.
    totals=[r for r in rows if any("合計" in str(v) or "總計" in str(v) for v in r.values())]
    for r in totals:
     value=num(pick(r,"融資今日餘額","融資餘額","MarginPurchaseTodayBalance","融資餘額(仟元)"))
     if value is not None:
      record.update({"status":"ok","value":value,"date":date_of(r),"unit":"來源原始單位","provider":"TWSE","reason":"請核對官方欄位單位"})
      break
    if record.get("status")!="ok":
     balances=[num(pick(r,"融資今日餘額")) for r in rows]
     balances=[v for v in balances if v is not None]
     if len(balances)>100:
      record.update({"status":"partial","value":sum(balances),"date":date_of(rows[0]),"unit":"股（上市個股融資餘額合計）","provider":"TWSE","reason":"僅上市個股融資股數合計，非融資金額；不含上櫃"})
    if record.get("status")!="ok":
     balances=[num(pick(r,"融資今日餘額")) for r in rows]
     balances=[v for v in balances if v is not None]
     if len(balances)>100:record.update({"status":"partial","value":sum(balances),"unit":"股（上市個股融資餘額合計）","provider":"TWSE","reason":"融資股數，不是融資金額；不含上櫃"})
   elif kind=="cash_inst":
    record["categories"]=[]
    for r in rows:
     name=pick(r,"單位名稱","名稱","Name")
     net=num(pick(r,"買賣差額","買賣超金額","買賣超","Difference"))
     if name is not None and net is not None:record["categories"].append({"name":name,"net":net})
    if record["categories"]:
     record.update({"status":"partial","date":date_of(rows[0]),"provider":"TWSE","reason":"已取得法人分項；需確認原始金額單位"})
   elif kind=="tw_price":
    r=rows[-1]
    value=num(pick(r,"TAIEX","TradeIndex","發行量加權股價指數","加權指數"))
    volume=num(pick(r,"TradeVolume","成交股數"))
    amount=num(pick(r,"TradeValue","成交金額"))
    if value is not None:
     record.update({"status":"ok","value":value,"date":date_of(r),"unit":"points","provider":"TWSE"})
     if volume is not None:record["volume_shares"]=volume
     if amount is not None:record["turnover_twd"]=amount
   elif kind=="futures":
    candidates=[r for r in rows if str(pick(r,"ContractCode","商品名稱","契約") or "") in ("臺股期貨","台股期貨","TX") and "外資" in str(pick(r,"Item","身份別","交易人類別") or "")]
    for r in candidates:
     net=num(pick(r,"OpenInterest(Net)","未平倉口數(淨額)","未平倉淨額"))
     if net is not None:
      record.update({"status":"partial","foreign_tx_net_oi":net,"date":date_of(r),"unit":"口","provider":"TAIFEX","reason":"外資臺股期貨淨未平倉"})
      break
   metrics.setdefault(key,{}).setdefault("official_sources",{})[kind]=record
   if kind=="margin" and record.get("status") in ("ok","partial"):metrics["margin"].update({k:v for k,v in record.items() if k!="sample_fields"})
   if kind=="tw_price" and record.get("status")=="ok":
    # Keep Yahoo one-year drawdown until official historical prices are available.
    metrics["taiex"]["official_close"]=record["value"]
    if "volume_shares" in record:metrics["taiex"]["official_volume_shares"]=record["volume_shares"]
    if "turnover_twd" in record:metrics["taiex"]["official_turnover_twd"]=record["turnover_twd"]
    if "volume_shares" in record:metrics["taiex"]["official_volume_shares"]=record["volume_shares"]
    if "turnover_twd" in record:metrics["taiex"]["official_turnover_twd"]=record["turnover_twd"]
    metrics["taiex"]["official_close_date"]=record["date"]
   if kind in ("cash_inst","futures") and record.get("status") in ("ok","partial"):
    metrics["inst"]["status"]="partial"
    if kind=="cash_inst":metrics["inst"]["cash_categories"]=record.get("categories",[])
    if kind=="futures":metrics["inst"]["foreign_tx_net_oi"]=record.get("foreign_tx_net_oi");metrics["inst"]["date"]=record.get("date")
    if kind=="futures":metrics["inst"]["value"]=record.get("foreign_tx_net_oi");metrics["inst"]["unit"]="口（期貨外資淨未平倉，待契約確認）";metrics["inst"]["date"]=record.get("date")
    if kind=="cash_inst":metrics["inst"]["cash_categories"]=record.get("categories",[])
    metrics["inst"]["reason"]="官方現貨與期貨分項資料；勿將不同單位直接相加"
   if record.get("status") in ("ok","partial"):old.setdefault("source_checks",{})["tw_"+kind]=NOW.isoformat()
   print("Taiwan",kind,record.get("status","schema_pending"),record.get("date",""),flush=True)
  except Exception as exc:
   metrics.setdefault(key,{}).setdefault("official_sources",{})[kind]={"status":"unavailable","reason":type(exc).__name__,"source_url":url}
   print("Taiwan",kind,"unavailable",type(exc).__name__,flush=True)

def main():
 try:old=json.loads(OUT.read_text())
 except (FileNotFoundError,ValueError):old={}
 previous=old.get("active_alerts",{})
 previous_failures=old.get("source_failure_streaks",{})
 metrics={k:{"name":n,"group":g,"source":s,"frequency":f,"status":"unavailable","reason":"尚未接入可靠來源"} for k,n,g,s,f in CATALOG}
 def fetch_one_fred(item):
  k,series=item
  rows,provider=fred(series)
  e=entry(rows,"https://fred.stlouisfed.org/series/"+series,"index" if k in ("nfci","vix") else "%")
  e["provider"]=provider
  e["checked_at"]=NOW.isoformat()
  if provider.startswith("DBnomics"):e["mirror_url"]="https://db.nomics.world/FRED/"+series
  if k=="hy" and len(rows)>20:e["change20bp"]=round((rows[-1][1]-rows[-21][1])*100,1)
  return k,e
 with ThreadPoolExecutor(max_workers=5) as pool:
  futures={pool.submit(fetch_one_fred,item):item[0] for item in FRED.items() if (old.get("metrics",{}).get(item[0],{}).get("provider")!="FRED official API" or due(old,item[0],168 if item[0]=="nfci" else 24))}
  for k in FRED:
   if old.get("metrics",{}).get(k,{}).get("provider")=="FRED official API" and not due(old,k,168 if k=="nfci" else 24):
    if not cached(metrics,old,k):
     metrics[k].update({field:value for field,value in old.get("metrics",{}).get(k,{}).items() if field not in ("name","group","source","frequency")})
  for future in as_completed(futures):
   k=futures[future]
   try:
    _,e=future.result()
    metrics[k].update(e)
    print("FRED",k,e["provider"],e["date"],e["value"],flush=True)
   except Exception as exc:
    if not cached(metrics,old,k):metrics[k]["reason"]="來源錯誤："+str(exc)[:150]
    metrics[k]["last_error"]=str(exc)[:150]
    metrics[k]["checked_at"]=NOW.isoformat()
    print("FRED",k,"unavailable",str(exc)[:150],flush=True)
 taiwan(metrics,old)
 prices={}
 for k,s in YAHOO.items():
  try:prices[k]=yahoo(s)
  except Exception:pass
 if "ndx" in prices:
  a=prices["ndx"];high=max(v for _,v in a);e=entry(a,"https://finance.yahoo.com/quote/%5ENDX/","points")
  e["drawdown_pct"]=round(100*(high-a[-1][1])/high,2);e["reference"]="近一年最高收盤價"
  if "spx" in prices:e["spx"]=round(prices["spx"][-1][1],2)
  e["checked_at"]=NOW.isoformat()
  metrics["indices"].update(e)
 if "tw" in prices:
  a=prices["tw"];high=max(v for _,v in a);e=entry(a,"https://finance.yahoo.com/quote/%5ETWII/","points")
  e["drawdown_pct"]=round(100*(high-a[-1][1])/high,2);e["reference"]="近一年最高收盤價"
  e["checked_at"]=NOW.isoformat()
  metrics["taiex"].update(e)
 if "twd" in prices:
  metrics["fx"].update(entry(prices["twd"],"https://finance.yahoo.com/quote/TWD=X/","TWD per USD"))
  metrics["fx"]["checked_at"]=NOW.isoformat()
  if "dxy" in prices:metrics["fx"]["dxy"]=round(prices["dxy"][-1][1],2)
 if "sox" in prices and "ndx" in prices:
  metrics["breadth"].update({"status":"partial","value":round(prices["sox"][-1][1]/prices["ndx"][-1][1],4),"date":min(prices["sox"][-1][0],prices["ndx"][-1][0]),"unit":"SOX/NDX","reason":"只有半導體相對強弱，市場廣度未取得","source_url":"https://finance.yahoo.com/quote/%5ESOX/"})
 for key in ("indices","taiex","fx","breadth"):
  if metrics[key]["status"]=="unavailable" and cached(metrics,old,key):metrics[key]["cache_status"]="stale"
 alerts={}
 for prefix,k in [("hy","hy"),("vix","vix"),("ndx","indices"),("tw","taiex")]:
  if metrics[k]["status"]!="ok" or metrics[k].get("cache_status")=="stale" or metrics[k].get("last_error"):alerts.update({key:v for key,v in previous.items() if key.startswith(prefix)})
 def rule(key,trigger,severity,message):
  if trigger:alerts[key]={"severity":severity,"message":message,"first_seen":previous.get(key,{}).get("first_seen",NOW.isoformat())}
 h=metrics["hy"];v=metrics["vix"];n=metrics["indices"];t=metrics["taiex"]
 if h["status"]=="ok" and not h.get("last_error") and h.get("cache_status")!="stale":
  rule("hy4",h["value"]>=4,"warning","HY OAS ≥4%："+str(h["value"])+"%")
  if "change20bp" in h:rule("hy75",h["change20bp"]>=75,"warning","HY OAS 20交易日擴大 ≥75bp："+str(h["change20bp"])+"bp")
 if v["status"]=="ok" and not v.get("last_error") and v.get("cache_status")!="stale":
  for threshold in (25,35):rule("vix"+str(threshold),v["value"]>=threshold,"critical" if threshold==35 else "warning","VIX ≥"+str(threshold)+"："+str(v["value"]))
 if n["status"]=="ok" and n.get("cache_status")!="stale":
  for threshold in (10,20):rule("ndx"+str(threshold),n["drawdown_pct"]>=threshold,"critical" if threshold==20 else "warning","Nasdaq 100 近一年高點回撤 ≥"+str(threshold)+"%："+str(n["drawdown_pct"])+"%")
 if t["status"]=="ok" and t.get("cache_status")!="stale":
  for threshold in (5,10,15,20,25):rule("tw"+str(threshold),t["drawdown_pct"]>=threshold,"critical" if threshold>=20 else "warning","台股近一年高點回撤 ≥"+str(threshold)+"%："+str(t["drawdown_pct"])+"%")
 pending=old.get("pending_notifications",[])
 for key,a in alerts.items():
  if key not in previous and not any(x["key"]==key for x in pending):pending.append({"key":key,"message":a["message"]})
 # Monitor source health without repeatedly creating the same incident.
 streaks={}
 for key in list(FRED)+["indices","taiex","fx"]:
  m=metrics[key]
  failed=(m["status"]=="unavailable" or m.get("cache_status")=="stale" or bool(m.get("last_error")))
  streaks[key]=(previous_failures.get(key,0)+1) if failed else 0
  if streaks[key]>=3 and previous_failures.get(key,0)<3:
   pending.append({"key":"health_"+key,"message":"資料來源連續失敗3次："+key})
 if STATS["requests"]>=MAX_REQUESTS and old.get("request_stats",{}).get("requests",0)<MAX_REQUESTS:
  pending.append({"key":"health_budget","message":"API請求達單次上限："+str(MAX_REQUESTS)})
 if pending:
  try:
   if telegram("全球金融風險雷達\n"+"\n".join("• "+p["message"] for p in pending)+"\n詳情請查看儀表板"):pending=[]
  except Exception as exc:print("Telegram delivery failed:",type(exc).__name__)
 payload={"source_checks":old.get("source_checks",{}),"updated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"request_stats":STATS,"source_failure_streaks":streaks,"metrics":metrics,"active_alerts":alerts,"pending_notifications":pending,"notes":["無資料不代表安全；免費端點可能延遲或停用","回撤基準：近一年最高收盤價，非個人45,211點加碼基準","18項已列示，但尚未全部完成資料串接"]}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2))
 print("Updated:",sum(m["status"]=="ok" for m in metrics.values()),"full metrics;",len(alerts),"active alerts; requests",STATS["requests"],"failures",STATS["failure"])
if __name__=="__main__":main()
