import { useEffect, useRef, useState } from "react";
import { AuctionDetail } from "./components/AuctionDetail";
import { AuctionList } from "./components/AuctionList";
import { LoginPanel } from "./components/LoginPanel";
import { RfqCreateForm } from "./components/RfqCreateForm";
import * as api from "./api";

const sessionKey = "british-auction-session";
const defaultPage = { limit: 25, offset: 0, total: 0 };
const defaultHistory = { history_limit: 25, bids_offset: 0, activity_offset: 0 };
function saveSession(session) {
  try { session ? localStorage.setItem(sessionKey, JSON.stringify(session)) : localStorage.removeItem(sessionKey); } catch { /* Storage can be unavailable in private browser modes. */ }
}
function readStoredSession() {
  try {
    const value = JSON.parse(localStorage.getItem(sessionKey));
    if (typeof value?.token === "string" && value.token && typeof value?.user?.company_name === "string" && ["buyer", "supplier"].includes(value.user.role)) return value;
  } catch { /* Invalid stored state is treated as signed out. */ }
  saveSession(null);
  return null;
}

export default function App() {
  const [session, setSession] = useState(readStoredSession);
  const [auctions, setAuctions] = useState([]);
  const [selectedAuction, setSelectedAuction] = useState(null);
  const [auctionPage, setAuctionPage] = useState(defaultPage);
  const [suppliers, setSuppliers] = useState([]);
  const [mode, setMode] = useState("details");
  const [isLoading, setIsLoading] = useState(false);
  const [connection, setConnection] = useState("Checking connection");
  const [notice, setNotice] = useState(null);
  const generation = useRef(0);
  const requests = useRef(new Set());
  const sessionRef = useRef(session);
  const selection = useRef(null);
  const viewVersion = useRef(0);
  const detailSequence = useRef(0);
  const pageRef = useRef(defaultPage);
  const historyRef = useRef(defaultHistory);
  const refreshing = useRef(null);
  const refreshSequence = useRef(0);
  const creating = useRef(false);
  const bidding = useRef(new Set());
  const refreshRef = useRef(null);
  const token = session?.token;
  const user = session?.user;

  function valid(epoch) { return generation.current === epoch; }
  async function call(fn) {
    const controller = new AbortController();
    requests.current.add(controller);
    try { return await fn({ signal: controller.signal }); }
    finally { requests.current.delete(controller); }
  }
  function clearSession() {
    generation.current += 1;
    viewVersion.current += 1;
    for (const request of requests.current) request.abort();
    sessionRef.current = null;
    selection.current = null;
    pageRef.current = defaultPage;
    historyRef.current = defaultHistory;
    saveSession(null); setSession(null); setAuctions([]); setSelectedAuction(null);
    setAuctionPage(defaultPage); setSuppliers([]); setMode("details"); setIsLoading(false);
  }
  function handleError(error, epoch) {
    if (!valid(epoch) || error.name === "AbortError") return;
    if (error.status === 401) clearSession();
    setNotice({ type: "error", message: error.message || "Could not connect. Please retry." });
    setConnection("Connection problem");
  }
  async function handleLogout() {
    const oldToken = sessionRef.current?.token;
    clearSession();
    const epoch = generation.current;
    setNotice(null);
    if (oldToken) {
      try { await api.logout(oldToken); }
      catch (error) {
        if (valid(epoch) && error.status !== 401) setNotice({ type: "error", message: "Signed out on this device. Server session revocation could not be confirmed." });
      }
    }
  }

  async function loadDetail(id, activeToken, epoch, version) {
    const detailId = ++detailSequence.current;
    const detail = await call((options) => api.getAuction(id, activeToken, historyRef.current, options));
    if (valid(epoch) && version === viewVersion.current && detailId === detailSequence.current && selection.current === id) setSelectedAuction(detail);
  }
  async function refreshAuctions(force = false) {
    const activeToken = sessionRef.current?.token;
    if (!activeToken || (refreshing.current === generation.current && !force)) return;
    const epoch = generation.current;
    const requestId = ++refreshSequence.current;
    const version = viewVersion.current;
    refreshing.current = epoch;
    setIsLoading(true);
    try {
      const page = await call((options) => api.listAuctions(activeToken, pageRef.current, options));
      if (!valid(epoch) || version !== viewVersion.current || requestId !== refreshSequence.current) return;
      const items = page.items || [];
      setAuctions(items); setAuctionPage(page); pageRef.current = page;
      if (!items.some((a) => a.id === selection.current)) {
        selection.current = items[0]?.id || null;
        historyRef.current = defaultHistory;
      }
      if (selection.current) await loadDetail(selection.current, activeToken, epoch, version);
      else setSelectedAuction(null);
      if (valid(epoch)) setConnection("Connected · refreshes every 15 seconds");
    } catch (error) { handleError(error, epoch); }
    finally { if (requestId === refreshSequence.current) { refreshing.current = null; if (valid(epoch)) setIsLoading(false); } }
  }
  refreshRef.current = refreshAuctions;

  useEffect(() => {
    if (!token) return;
    const epoch = ++generation.current;
    let cancelled = false;
    setIsLoading(true);
    (async () => {
      try {
        const currentUser = await call((options) => api.getMe(token, options));
        if (cancelled || !valid(epoch)) return;
        const next = { token, user: currentUser };
        sessionRef.current = next; setSession(next); saveSession(next);
        const available = currentUser.role === "buyer" ? await call((options) => api.listSuppliers(token, options)) : [];
        if (cancelled || !valid(epoch)) return;
        setSuppliers(available);
        await refreshRef.current();
      } catch (error) { handleError(error, epoch); }
      finally { if (valid(epoch)) setIsLoading(false); }
    })();
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") refreshRef.current();
    }, 15000);
    return () => {
      cancelled = true; clearInterval(timer);
      generation.current += 1;
      for (const request of requests.current) request.abort();
    };
  }, [token]);

  async function handleLogin(email, password) {
    const epoch = generation.current;
    setIsLoading(true); setNotice(null);
    try {
      const auth = await call((options) => api.login(email, password, options));
      if (!valid(epoch)) return;
      const next = { token: auth.access_token, user: auth.user };
      sessionRef.current = next; saveSession(next); setSession(next);
      setMode("details"); setNotice({ type: "success", message: `Signed in as ${auth.user.company_name}.` });
    } catch (error) { handleError(error, epoch); }
    finally { if (valid(epoch)) setIsLoading(false); }
  }
  async function handleSelect(id) {
    const epoch = generation.current;
    const version = ++viewVersion.current;
    selection.current = id; historyRef.current = defaultHistory;
    setMode("details"); setNotice(null); setSelectedAuction(null);
    try { await loadDetail(id, sessionRef.current.token, epoch, version); }
    catch (error) { if (version === viewVersion.current) handleError(error, epoch); }
  }
  async function handleHistory(params) {
    const epoch = generation.current;
    const version = ++viewVersion.current;
    historyRef.current = { ...historyRef.current, ...params };
    try { await loadDetail(selection.current, sessionRef.current.token, epoch, version); }
    catch (error) { if (version === viewVersion.current) handleError(error, epoch); }
  }
  async function handleCreate(payload) {
    if (creating.current) return false;
    creating.current = true;
    const epoch = generation.current;
    try {
      const created = await call((options) => api.createAuction(payload, sessionRef.current.token, options));
      if (!valid(epoch)) return false;
      ++viewVersion.current; selection.current = created.id; historyRef.current = defaultHistory;
      pageRef.current = { ...defaultPage }; setMode("details"); setSelectedAuction(created);
      setNotice({ type: "success", message: `${created.reference_id} created.` });
      await refreshAuctions(true);
      return true;
    } catch (error) { handleError(error, epoch); return false; }
    finally { creating.current = false; }
  }
  async function handleSubmitBid(id, payload) {
    if (bidding.current.has(id)) return false;
    bidding.current.add(id);
    const epoch = generation.current;
    const version = ++viewVersion.current;
    try {
      const updated = await call((options) => api.submitBid(id, payload, sessionRef.current.token, options));
      if (!valid(epoch)) return false;
      if (selection.current === id && version === viewVersion.current) {
        historyRef.current = defaultHistory; setSelectedAuction(updated);
        setNotice({ type: "success", message: "Quote submitted." });
      }
      await refreshAuctions(true);
      return true;
    } catch (error) { if (selection.current === id) handleError(error, epoch); return false; }
    finally { bidding.current.delete(id); }
  }
  async function handlePageChange(offset) {
    ++viewVersion.current; pageRef.current = { ...pageRef.current, offset: Math.max(0, offset) };
    selection.current = null; historyRef.current = defaultHistory;
    setSelectedAuction(null); setMode("details");
    await refreshAuctions(true);
  }

  const flash = notice && <div className={`flash ${notice.type}`} role="status"><p>{notice.message}</p></div>;
  if (!session) return <>{flash}<LoginPanel onLogin={handleLogin} isLoading={isLoading} /></>;
  return (
    <div className="app-root">
      <header className="topbar">
        <div className="brand-lockup" aria-label="British Auction RFQ System">
          <div className="brand-mark" aria-hidden="true">BA</div>
          <div><p className="eyebrow">RFQ Console</p><h1>British Auction RFQ System</h1></div>
        </div>
        <div className="topbar-actions">
          <div className="session-pill"><strong>{user.company_name}</strong><span>{user.role}</span></div>
          <button className="secondary-button" type="button" onClick={() => refreshAuctions(true)} disabled={isLoading}>Refresh</button>
          <button className="secondary-button" type="button" onClick={handleLogout}>Sign Out</button>
          <span role="status">{isLoading ? "Syncing" : connection}</span>
        </div>
      </header>
      {flash}
      <main className="workspace">
        <AuctionList auctions={auctions} selectedId={selection.current} canCreate={user.role === "buyer"} page={auctionPage}
          onSelect={handleSelect} onPageChange={handlePageChange} onCreate={() => { setMode("create"); setNotice(null); }} />
        {mode === "create" && user.role === "buyer" ?
          <RfqCreateForm suppliers={suppliers} onCancel={() => setMode("details")} onSubmit={handleCreate} /> :
          <AuctionDetail auction={selectedAuction} user={user} onSubmitBid={handleSubmitBid} onHistoryChange={handleHistory} />}
      </main>
    </div>
  );
}
