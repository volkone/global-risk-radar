"""Cross-check TAIFEX's unfiltered archive by month and smaller date partitions."""
import calendar
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.taifex.com.tw/cht/11/hisNews"
OUTPUT = ROOT / "docs/taifex_hisnews_coverage.json"
START, END = date(2023, 11, 11), date(2026, 10, 31)
CONTROLS = ("2024-07-24", "2024-10-02", "2024-10-31", "2026-07-10", "2026-10-23")
CLOSURE = re.compile("休市|停止交易|停止上班|颱風|交易日曆|交易日期|暫停交易")


def query(bounds):
    start, end = bounds
    dates = [d.strftime("%Y/%m/%d") for d in bounds]
    url = URL + "?" + urlencode(dict(isQuery="1", queryStartDate=dates[0],
                                    queryEndDate=dates[1], newsType="", queryKeyWord=""))
    result = {"start": str(start), "end": str(end), "url": url}
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as response:
            raw = response.read()
        result["sha256"] = hashlib.sha256(raw).hexdigest()
        document = html.fromstring(raw.decode("utf-8"))
        if not re.search(rb"var isQuery\s*=\s*'1'", raw):
            raise ValueError("search not applied")
        if [document.get_element_by_id(key).get("value") for key in ("queryStartDate", "queryEndDate")] != dates:
            raise ValueError("server echoed different dates")
        tables = document.xpath('//table[@class="table_c td-wrap"]')
        if len(tables) != 1:
            raise ValueError(f"expected one result table, got {len(tables)}")
        table = tables[0]
        # Restrict pagination detection to the results container, excluding site carousels.
        pagination = [a.text_content().strip() for a in table.getparent().xpath(".//a")
                      if re.fullmatch(r"下一頁|上一頁|末頁|下頁|Next|Previous|[0-9]+", a.text_content().strip(), re.I)]
        if pagination:
            raise ValueError(f"pagination controls present: {pagination}")
        rows = []
        for tr in table.xpath(".//tr"):
            cells = tr.xpath("./td")
            if not cells:
                continue
            if len(cells) == 1 and re.search("查無|無資料|沒有資料", cells[0].text_content().strip()):
                continue
            if len(cells) != 2:
                raise ValueError("unknown table row format")
            stamp = datetime.strptime(cells[0].text_content().strip(), "%Y/%m/%d").date()
            links = cells[1].xpath(".//a[@href]")
            if not start <= stamp <= end or len(links) != 1:
                raise ValueError("out-of-range date or missing notice link")
            link = links[0]
            rows.append((str(stamp), " ".join(link.text_content().split()), urljoin(URL, link.get("href"))))
        result.update(rows=rows, count=len(rows), pagination_controls=pagination)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["error"] = str(error)
    return result


def main():
    partitions = []
    for year in range(START.year, END.year + 1):
        for month in range(1, 13):
            first = max(START, date(year, month, 1))
            last = min(END, date(year, month, calendar.monthrange(year, month)[1]))
            if first <= last:
                middle = first + (last - first) // 2
                partitions.append([(first, last), (first, middle), (middle + timedelta(days=1), last)])
    with ThreadPoolExecutor(max_workers=5) as executor:
        spans = [span for group in partitions for span in group]
        results = list(executor.map(query, spans))
        retry_indices = [i for i, result in enumerate(results) if "error" in result]
        for i, result in zip(retry_indices, executor.map(query, (spans[i] for i in retry_indices))):
            result["first_attempt_error"] = results[i]["error"]
            results[i] = result
    groups, notices = [], []
    for i in range(0, len(results), 3):
        month, first, second = results[i:i + 3]
        matched = all("error" not in part for part in (month, first, second)) and (
            Counter(month["rows"]) == Counter(first["rows"] + second["rows"]))
        groups.append({"partitions": [{k: v for k, v in part.items() if k != "rows"}
                                      for part in (month, first, second)], "matched": matched})
        if "rows" in month:
            notices.extend(month["rows"])
    candidates = [row for row in notices if CLOSURE.search(row[1])]
    controls = {day: [row for row in candidates
                      if abs((date.fromisoformat(row[0])-date.fromisoformat(day)).days) <= 1
                      and "休市" in row[1]] for day in CONTROLS}
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "window": [str(START), str(END)],
        "scope": "Unfiltered public Chinese-language hisNews result table",
        "partitions": groups, "months_matched": sum(group["matched"] for group in groups),
        "months_total": len(groups), "notice_count": len(notices),
        "closure_positive_controls": controls, "closure_candidates": candidates,
        "monthly_response_manifest_sha256": hashlib.sha256(json.dumps([
            group["partitions"][0].get("sha256") for group in groups]).encode()).hexdigest(),
        "public_archive_coverage_verified": all(group["matched"] for group in groups) and all(controls.values()),
        "limitation": "Coverage refers to the public search interface. It cannot attest to records absent from the exchange archive."
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print({key: report[key] for key in ("months_matched", "notice_count", "public_archive_coverage_verified")})
    print({day: len(rows) for day, rows in controls.items()})
    for group in groups:
        if not group["matched"]:
            print(group)
    return 0 if report["public_archive_coverage_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
