import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from dataclasses import dataclass
from decimal import Decimal
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from app.services.auction import BidCandidate,evaluate_bid,current_rankings

@dataclass
class Auction:
 start_at:datetime=datetime(2026,11,10,9,tzinfo=timezone.utc)
 close_at:datetime=datetime(2026,11,10,10,tzinfo=timezone.utc)
 forced_close_at:datetime=datetime(2026,11,10,10,3,tzinfo=timezone.utc)
 trigger_window_minutes:int=10
 extension_minutes:int=5
 trigger_type:str='bid-received'

def quote(name,time,price='100'):
 return BidCandidate(name,Decimal(price),Decimal('0'),Decimal('0'),'2 days','7 days',time)

@pytest.mark.parametrize('trigger',['bid-received','any-rank-change','l1-rank-change'])
@pytest.mark.parametrize('offset_seconds',[-3601,-3600,-601,-600,-1,0,180])
def test_exact_boundaries_and_forced_cap(trigger,offset_seconds):
 a=Auction(trigger_type=trigger)
 now=a.close_at+timedelta(seconds=offset_seconds)
 result=evaluate_bid(a,[],quote('A',now))
 active=a.start_at<=now<a.close_at
 assert bool(result.errors) != active
 if active:
  assert a.close_at<=result.extension.next_close_at<=a.forced_close_at
  expected=offset_seconds>=-600 and trigger!='l1-rank-change'
  assert result.extension.applied==expected

def test_any_rank_change_and_stable_rebid():
 a=Auction(trigger_type='any-rank-change')
 old=[quote('A',a.start_at,'100'),quote('B',a.start_at+timedelta(minutes=1),'120')]
 now=a.close_at-timedelta(seconds=1)
 assert not evaluate_bid(a,old,quote('B',now,'110')).extension.applied
 assert evaluate_bid(a,old,quote('B',now,'90')).extension.applied

def test_price_tie_uses_earliest_bid():
 a=Auction()
 ranks=current_rankings([quote('B',a.start_at+timedelta(minutes=1)),quote('A',a.start_at)])
 assert [r.carrier_name for r in ranks]==['A','B']

def test_identical_names_prices_and_times_have_stable_id_tiebreak():
 a=Auction()
 one=BidCandidate('Same name',Decimal('100'),Decimal('0'),Decimal('0'),'2 days','7 days',a.start_at,supplier_user_id='supplier-a')
 two=BidCandidate('Same name',Decimal('100'),Decimal('0'),Decimal('0'),'2 days','7 days',a.start_at,supplier_user_id='supplier-b')
 assert [r.carrier_key for r in current_rankings([two,one])]==['supplier-a','supplier-b']
