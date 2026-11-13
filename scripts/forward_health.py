"""Visible capture heartbeat and bounded same-day fallback; never backfills."""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]

def due(now):
    return now.date().isoformat()>='2026-11-13' and now.weekday()<5 and 20<=now.hour<=23

def health(now, latest, ledger, snapshot_exists):
    day=now.date().isoformat()
    last=latest.get('checked_at_utc') or latest.get('completed_at_utc')
    same_day=bool(last and dt.datetime.fromisoformat(last).astimezone(now.tzinfo).date()==now.date())
    state=('captured' if snapshot_exists else 'capture_incomplete' if due(now) and same_day
           else 'capture_due_no_current_attempt' if due(now) else 'outside_capture_window')
    return {'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'taipei_date':day,
            'status':state,'canonical_snapshot_present':snapshot_exists,'last_capture_check_utc':last,
            'capture_errors':latest.get('errors',{}) if same_day else {},
            'snapshots':ledger.get('prospective_immutable_snapshots',0),
            'predictions':ledger.get('research_predictions_total',0),
            'outcomes':ledger.get('research_outcome_files_total',0),
            'schedule_firing_verified':False,
            'note':'Capture evidence does not prove GitHub cron delivery. Missing dates cannot be backfilled as first-seen.'}

def read(path):
    return json.loads(path.read_text()) if path.exists() else {}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--capture-if-due',action='store_true');args=parser.parse_args()
    now=dt.datetime.now(ZoneInfo('Asia/Taipei'))
    if args.capture_if_due and due(now):
        subprocess.run([sys.executable,str(ROOT/'scripts/phase5_forward_capture.py'),'--mode','capture'],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/phase5_forward_ledger.py'),'--mode','record'],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_forward.py')],check=True)
    snap=ROOT/'storage/prospective/snapshots'/f'{now.date().isoformat()}.json'
    if snap.exists():
        from phase5_forward_ledger import verified_snapshot
        verified_snapshot(snap)
    report=health(now,read(ROOT/'docs/phase5_forward_capture_latest.json'),read(ROOT/'docs/phase5_forward_status.json'),snap.exists())
    (ROOT/'docs/forward_health.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('FORWARD_HEALTH',report['status'],report['snapshots'],report['capture_errors'])
if __name__=='__main__':main()
