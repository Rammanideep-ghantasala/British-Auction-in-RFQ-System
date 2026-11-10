import { useEffect, useState } from "react";
import { AuctionDetail } from "./components/AuctionDetail";
import { AuctionList } from "./components/AuctionList";
import { LoginPanel } from "./components/LoginPanel";
import { RfqCreateForm } from "./components/RfqCreateForm";
import { createAuction, getAuction, getMe, listAuctions, listSuppliers, login, submitBid } from "./api";

const sessionKey = "british-auction-session";
const defaultPage = { limit: 25, offset: 0, total: 0 };

function readStoredSession() {
  try {
    return JSON.parse(localStorage.getItem(sessionKey));
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(readStoredSession);
  const [auctions, setAuctions] = useState([]);
  const [selectedAuction, setSelectedAuction] = useState(null);
  const [auctionPage, setAuctionPage] = useState(defaultPage);
  const [suppliers, setSuppliers] = useState([]);
  const [mode, setMode] = useState("details");
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  const token = session?.token;
  const user = session?.user;
  const isBuyer = user?.role === "buyer";

  useEffect(() => {
    if (!token) {
      return;
    }

    bootstrapSession(token);
  }, [token]);

  async function bootstrapSession(activeToken) {
    setIsLoading(true);
    try {
      const currentUser = await getMe(activeToken);
      const nextSession = { token: activeToken, user: currentUser };
      setSession(nextSession);
      localStorage.setItem(sessionKey, JSON.stringify(nextSession));

      if (currentUser.role === "buyer") {
        setSuppliers(await listSuppliers(activeToken));
      } else {
        setSuppliers([]);
      }

      await refreshAuctions(undefined, activeToken);
    } catch (error) {
      handleLogout();
      setNotice({ type: "error", message: error.message });
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshAuctions(nextSelectedId, activeToken = token, pageOptions = {}) {
    if (!activeToken) {
      return;
    }

    const requestedPage = {
      limit: auctionPage.limit,
      offset: auctionPage.offset,
      ...pageOptions
    };

    setIsLoading(true);
    try {
      const page = await listAuctions(activeToken, requestedPage);
      const items = page.items || [];
      setAuctions(items);
      setAuctionPage({
        total: page.total || 0,
        limit: page.limit || requestedPage.limit,
        offset: page.offset || requestedPage.offset
      });

      const currentSelectionIsVisible = items.some((auction) => auction.id === selectedAuction?.id);
      const selectedId = nextSelectedId || (currentSelectionIsVisible ? selectedAuction?.id : items[0]?.id);
      if (selectedId) {
        const detail = await getAuction(selectedId, activeToken);
        setSelectedAuction(detail);
      } else {
        setSelectedAuction(null);
      }
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setIsLoading(false);
    }
  }

  async function handleLogin(email, password) {
    setIsLoading(true);
    setNotice(null);
    try {
      const auth = await login(email, password);
      const nextSession = { token: auth.access_token, user: auth.user };
      setSession(nextSession);
      localStorage.setItem(sessionKey, JSON.stringify(nextSession));
      setMode("details");
      setSelectedAuction(null);
      setNotice({ type: "success", message: `Signed in as ${auth.user.company_name}.` });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setIsLoading(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem(sessionKey);
    setSession(null);
    setAuctions([]);
    setAuctionPage(defaultPage);
    setSelectedAuction(null);
    setSuppliers([]);
    setMode("details");
  }

  async function handleSelect(id) {
    setMode("details");
    setNotice(null);
    try {
      setSelectedAuction(await getAuction(id, token));
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  }

  async function handleCreate(payload) {
    try {
      const created = await createAuction(payload, token);
      setMode("details");
      setNotice({ type: "success", message: `${created.reference_id} created.` });
      await refreshAuctions(created.id, token, { offset: 0 });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  }

  async function handleSubmitBid(payload) {
    if (!selectedAuction) {
      return;
    }

    try {
      const updated = await submitBid(selectedAuction.id, payload, token);
      setSelectedAuction(updated);
      setNotice({ type: "success", message: "Quote submitted." });
      await refreshAuctions(updated.id);
      return true;
    } catch (error) {
      setNotice({ type: "error", message: error.message });
      return false;
    }
  }

  async function handlePageChange(nextOffset) {
    setMode("details");
    setNotice(null);
    await refreshAuctions(undefined, token, { offset: Math.max(0, nextOffset) });
  }

  if (!session) {
    return (
      <>
        {notice && (
          <div className={`flash ${notice.type}`} role="status">
            <p>{notice.message}</p>
          </div>
        )}
        <LoginPanel onLogin={handleLogin} isLoading={isLoading} />
      </>
    );
  }

  return (
    <div className="app-root">
      <header className="topbar">
        <div className="brand-lockup" aria-label="British Auction RFQ System">
          <div className="brand-mark" aria-hidden="true">
            BA
          </div>
          <div>
            <p className="eyebrow">RFQ Console</p>
            <h1>British Auction RFQ System</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <div className="session-pill">
            <strong>{user.company_name}</strong>
            <span>{user.role}</span>
          </div>
          <button className="secondary-button" type="button" onClick={() => refreshAuctions()}>
            Refresh
          </button>
          <button className="secondary-button" type="button" onClick={handleLogout}>
            Sign Out
          </button>
          <span>{isLoading ? "Syncing" : "API connected"}</span>
        </div>
      </header>

      {notice && (
        <div className={`flash ${notice.type}`} role="status">
          <p>{notice.message}</p>
        </div>
      )}

      <main className="workspace">
        <AuctionList
          auctions={auctions}
          selectedId={selectedAuction?.id}
          canCreate={isBuyer}
          page={auctionPage}
          onSelect={handleSelect}
          onPageChange={handlePageChange}
          onCreate={() => {
            setMode("create");
            setNotice(null);
          }}
        />
        {mode === "create" && isBuyer ? (
          <RfqCreateForm suppliers={suppliers} onCancel={() => setMode("details")} onSubmit={handleCreate} />
        ) : (
          <AuctionDetail auction={selectedAuction} user={user} onSubmitBid={handleSubmitBid} />
        )}
      </main>
    </div>
  );
}
