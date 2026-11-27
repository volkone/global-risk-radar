import unittest
from fat_sheep_screen import screen

def fixture():
    return dict(stock_id='TEST',as_of='2026-11-26',index='0050',membership_verified=True,industry_status='eligible',listing_date='2021-11-26',share_basis_verified=True,price=40,annual=[dict(year=y,eps=5,roe=8,dividend=3,available_date=f'{y+1}-05-01') for y in range(2021,2026)],quarters=[dict(year=(2024*4+3+i)//4,quarter=(2024*4+3+i)%4+1,eps=1.25,net_income=100,available_date='2026-11-20') for i in range(8)])
class TestScreen(unittest.TestCase):
    def test_grades(self):
        for p,g in [(40,'SSS='),(40.01,'SS='),(50,'SS='),(50.01,'S='),(60,'S='),(60.01,'A='),(75,'A=')]:
            with self.subTest(p=p):
                r=fixture();r['price']=p;self.assertEqual(screen(r).get('grade'),g)
    def test_decline(self):
        for n,s in [(80,'candidate'),(79.99,'R'),(101,'candidate')]:
            r=fixture()
            for q in r['quarters'][-4:]:q['net_income']=n
            self.assertEqual(screen(r)['status'],s)
    def test_rejections(self):
        for k,v,s in [('membership_verified',False,'NA'),('industry_status','excluded','X'),('listing_date','2021-11-27','X'),('price',75.01,'W'),('share_basis_verified',False,'NA')]:
            r=fixture();r[k]=v;self.assertEqual(screen(r)['status'],s)
    def test_quality(self):
        for k,v,s in [('eps',0,'X'),('roe',2.99,'X'),('dividend',0,'W'),('available_date','2027-01-01','NA')]:
            r=fixture();r['annual'][-1][k]=v;self.assertEqual(screen(r)['status'],s)
    def test_gaps(self):
        r=fixture();r['quarters'].pop();self.assertEqual(screen(r)['status'],'NA')
    def test_stale_annual(self):
        r=fixture()
        for a in r['annual']:a['year']-=5
        self.assertEqual(screen(r)['status'],'NA')
    def test_stale_quarters(self):
        r=fixture()
        for q in r['quarters']:q['year']-=5
        self.assertEqual(screen(r)['status'],'NA')
if __name__=='__main__':unittest.main(verbosity=2)
