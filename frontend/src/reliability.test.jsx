import {cleanup,render,screen,act,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach,describe,it,expect,vi} from 'vitest';
import App from './App';
import {BidForm} from './components/BidForm';
import {AuctionDetail} from './components/AuctionDetail';
import * as api from './api';
vi.mock('./api',()=>({logout:vi.fn().mockResolvedValue(null),getMe:vi.fn(),listAuctions:vi.fn(),listSuppliers:vi.fn(),getAuction:vi.fn(),login:vi.fn(),createAuction:vi.fn(),submitBid:vi.fn()}));
const u={id:'u1',role:'supplier',company_name:'Review carrier'};
afterEach(()=>{cleanup();localStorage.clear();vi.resetAllMocks();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();});

it('switching RFQs clears the previous quote draft',async()=>{
 const r=render(<BidForm auction={{id:'a',status:'Active'}} user={u} onSubmit={vi.fn()}/>);
 await userEvent.type(screen.getByLabelText(/Freight Charges/),'999');
 r.rerender(<BidForm auction={{id:'b',status:'Active'}} user={u} onSubmit={vi.fn()}/>);
 expect(screen.getByLabelText(/Freight Charges/).value).toBe('');
});

it('a bootstrap request finishing after sign out cannot restore the session',async()=>{
 let finish;
 api.getMe.mockImplementation(()=>new Promise(r=>{finish=r;}));
 api.listAuctions.mockResolvedValue({items:[],total:0,limit:25,offset:0});
 localStorage.setItem('british-auction-session',JSON.stringify({token:'local-test-token',user:u}));
 render(<App/>);
 await userEvent.click(screen.getByRole('button',{name:'Sign Out'}));
 expect(screen.getByRole('heading',{name:'Sign in to continue'})).toBeTruthy();
 await act(async()=>{finish(u);});
 expect(screen.queryByRole('heading',{name:'Sign in to continue'})).toBeTruthy();
 expect(localStorage.getItem('british-auction-session')).toBeNull();
});

it('malformed stored session recovers to login without crashing',()=>{
 localStorage.setItem('british-auction-session',JSON.stringify({token:'x'}));
 expect(()=>render(<App/>)).not.toThrow();
});

it('buyer can see prior supplier bids rather than only current rankings',()=>{
 const quote={id:'old-bid',carrier_name:'Review carrier',freight_charges:'1234.56',origin_charges:'0',destination_charges:'0',transit_time:'2 days',validity:'7 days',submitted_at:'2026-11-10T10:00:00Z',total:'1234.56'};
 render(<AuctionDetail user={{...u,role:'buyer'}} onSubmitBid={vi.fn()} auction={{id:'a',name:'RFQ',reference_id:'A',status:'Active',config:{trigger_type:'bid-received',trigger_window_minutes:10,extension_minutes:5},rankings:[{...quote,id:'new-bid',freight_charges:'1000',total:'1000',rank:'L1'}],bids:[{...quote,id:'new-bid',freight_charges:'1000',total:'1000'},quote],activity_log:[],current_lowest_bid:'1000'}}/>);
 expect(screen.queryAllByText(/1,234\.56/).length).toBeTruthy();
});

it('validation error objects become readable messages',async()=>{
 const realApi=await vi.importActual('./api');
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:[{type:'decimal_max_digits',loc:['body','freight_charges'],msg:'Decimal input should have no more than 12 digits in total'}]}),{status:422,headers:{'Content-Type':'application/json'}})));
 await expect(realApi.submitBid('a',{},'local-test-token')).rejects.toThrow('no more than 12 digits');
});

function auction(id) {
 return {id,reference_id:id.toUpperCase(),name:`Auction ${id.toUpperCase()}`,status:'Active',current_lowest_bid:null,
  close_at:'2026-11-12T12:00:00Z',forced_close_at:'2026-11-12T13:00:00Z',pickup_at:'2026-11-13T12:00:00Z',
  config:{trigger_type:'bid-received',trigger_window_minutes:10,extension_minutes:5},rankings:[],bids:[],activity_log:[],bids_total:0,activity_total:0,history_limit:25};
}
function signedIn() {
 localStorage.setItem('british-auction-session',JSON.stringify({token:'test-token',user:u}));
 api.getMe.mockResolvedValue(u);
 api.listAuctions.mockResolvedValue({items:[auction('a'),auction('b')],limit:25,offset:0,total:2});
}

it('a slow response from an old selection cannot replace the current RFQ',async()=>{
 signedIn(); let finishB;
 api.getAuction.mockImplementation((id)=> id==='b' ? new Promise(resolve=>{finishB=resolve;}) : Promise.resolve(auction('a')));
 render(<App/>);
 await screen.findByRole('heading',{name:'A - Auction A'});
 await userEvent.click(screen.getByRole('button',{name:'B Auction B'}));
 await userEvent.click(screen.getByRole('button',{name:'A Auction A'}));
 await screen.findByRole('heading',{name:'A - Auction A'});
 await act(async()=>finishB(auction('b')));
 expect(screen.getByRole('heading',{name:'A - Auction A'})).toBeTruthy();
});

it('switching RFQs through App clears the previous draft',async()=>{
 signedIn(); api.getAuction.mockImplementation(id=>Promise.resolve(auction(id)));
 render(<App/>);
 await screen.findByRole('heading',{name:'A - Auction A'});
 await userEvent.type(screen.getByLabelText(/Freight Charges/),'999');
 await userEvent.click(screen.getByRole('button',{name:'B Auction B'}));
 await screen.findByRole('heading',{name:'B - Auction B'});
 expect(screen.getByLabelText(/Freight Charges/).value).toBe('');
});

it('refreshes a visible auction and stops polling after logout',async()=>{
 signedIn(); api.getAuction.mockResolvedValue(auction('a')); api.logout.mockResolvedValue(null);
 vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
 vi.useFakeTimers();
 await act(async()=>{render(<App/>);});
 expect(screen.getByRole('heading',{name:'A - Auction A'})).toBeTruthy();
 const before=api.listAuctions.mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000);});
 expect(api.listAuctions.mock.calls.length).toBe(before+1);
 await act(async()=>{screen.getByRole('button',{name:'Sign Out'}).click();});
 const signedOut=api.listAuctions.mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(30000);});
 expect(api.listAuctions.mock.calls.length).toBe(signedOut);
});
