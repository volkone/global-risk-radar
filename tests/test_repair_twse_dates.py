import json
import tempfile
import unittest
from pathlib import Path
from scripts.repair_twse_dates import repair

class RepairTests(unittest.TestCase):
    def test_wrong_date_rejected_without_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps({"records": [], "attempts": []}))
            def fake(url):
                return {"date": "115年11月11日", "fields": [], "data": [], "tables": []}
            self.assertEqual(repair(fetch=fake, path=path), [])
            saved = json.loads(path.read_text())
            self.assertEqual(saved["records"], [])
            self.assertEqual(len(saved["attempts"]), 2)
            self.assertTrue(all(a["status"] == "rejected" for a in saved["attempts"]))
