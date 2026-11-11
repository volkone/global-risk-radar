import unittest
from scripts.import_taifex import parse_rows

def row(**overrides):
    d = {"日期": "2026/10/06", "商品名稱": "臺股期貨", "身份別": "外資",
         "未平倉多方口數": "9,000", "未平倉空方口數": "100,000",
         "未平倉多空淨額口數": "-91,000"}
    d.update(overrides)
    return d

class TaifexImportTests(unittest.TestCase):
    def test_tx_foreign_oi(self):
        r = parse_rows([row()])[0]
        self.assertEqual(r["date"], "2026-10-06")
        self.assertEqual(r["value"], -91000)
        self.assertEqual(r["unit"], "contracts")
    def test_excludes_other_products(self):
        self.assertEqual(parse_rows([row(商品名稱="小型臺指期貨")]), [])
    def test_rejects_inconsistent_oi(self):
        with self.assertRaises(ValueError):
            parse_rows([row(未平倉多空淨額口數="-90000")])
    def test_rejects_unknown_schema(self):
        with self.assertRaises(ValueError):
            parse_rows([{"date": "2026/10/06"}])
    def test_rejects_duplicate_dates(self):
        with self.assertRaises(ValueError):
            parse_rows([row(), row()])
