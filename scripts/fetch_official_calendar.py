"""Retrieve historical TWSE holiday tables by ROC queryYear, fail closed on bad data."""
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "storage" / "official_calendar"
BASE = "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule"

def fetch_year(year):
    url = BASE + "?" + urllib.parse.urlencode({"response":"json","queryYear":year})
    req = urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as f:
        obj=json.load(f)
    if isinstance(obj,list):
        rows=obj
    elif isinstance(obj,dict):
        rows=obj.get("data")
    else:
        rows=None
    if not isinstance(rows,list) or len(rows)<5:
        raise ValueError(f"{year}: no official holiday rows; URL={url}")
    fields=obj.get("fields",[]) if isinstance(obj,dict) else []
    normalized=[]
    for row in rows:
        if isinstance(row,dict):
            date=str(row.get("Date",row.get("日期",""))).strip()
            name=str(row.get("Name",row.get("名稱",""))).strip()
            desc=str(row.get("Description",row.get("說明",""))).strip()
        elif isinstance(row,list) and fields:
            mapped=dict(zip(fields,row))
            date=str(mapped.get("日期",mapped.get("Date",""))).strip()
            name=str(mapped.get("名稱",mapped.get("Name",""))).strip()
            desc=str(mapped.get("說明",mapped.get("Description",""))).strip()
        else:
            raise ValueError(f"{year}: unknown official row format")
        date=date.replace("/","-")
        try:
            if len(date)==7 and date.isdigit():
                day=dt.date(int(date[:3])+1911,int(date[3:5]),int(date[5:]))
            elif len(date)==10 and date[4]=="-":
                day=dt.date.fromisoformat(date)
            else:
                raise ValueError(date)
        except ValueError as e:
            raise ValueError(f"{year}: bad date {date}") from e
        if day.year!=year:
            raise ValueError(f"{year}: server returned different year {day}")
        normalized.append({"Date":f"{year-1911:03d}{day.month:02d}{day.day:02d}","Name":name,"Description":desc})
    if len({x["Date"] for x in normalized})!=len(normalized):
        raise ValueError(f"{year}: duplicate dates")
    return url,normalized

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest={}
    for year in range(2023,2027):
        url,rows=fetch_year(year)
        (OUT/f"{year}.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        manifest[str(year)]={"source_url":url,"rows":len(rows)}
        print(year,len(rows),url)
    (OUT/"source_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
