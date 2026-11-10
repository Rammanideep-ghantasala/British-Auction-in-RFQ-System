import { dateTime, money, statusClass } from "../formatters";

export function AuctionList({ auctions, selectedId, canCreate, page, onSelect, onCreate, onPageChange }) {
  const limit = page?.limit || 25;
  const offset = page?.offset || 0;
  const total = page?.total || auctions.length;
  const firstItem = total === 0 ? 0 : offset + 1;
  const lastItem = Math.min(offset + auctions.length, total);
  const canGoBack = offset > 0;
  const canGoForward = offset + limit < total;

  return (
    <section className="auction-listing" aria-labelledby="auction-listing-title">
      <div className="section-toolbar">
        <div>
          <p className="eyebrow">Auction Listing</p>
          <h2 id="auction-listing-title">British Auctions</h2>
        </div>
        {canCreate && (
          <button className="primary-button" type="button" onClick={onCreate}>
            New RFQ
          </button>
        )}
      </div>

      {auctions.length === 0 ? (
        <div className="empty-state">
          <h2>No British Auctions</h2>
          <p>{canCreate ? "Create an RFQ to start receiving supplier quotes." : "No invited RFQs are available."}</p>
          {canCreate && (
            <button className="primary-button" type="button" onClick={onCreate}>
              New RFQ
            </button>
          )}
        </div>
      ) : (
        <div className="table-wrap">
          <table className="auction-table">
            <thead>
              <tr>
                <th>RFQ Name / ID</th>
                <th>Current Lowest Bid</th>
                <th>Current Bid Close Time</th>
                <th>Forced Close Time</th>
                <th>Auction Status</th>
              </tr>
            </thead>
            <tbody>
              {auctions.map((auction) => (
                <tr key={auction.id} className={auction.id === selectedId ? "selected" : ""}>
                  <td>
                    <button className="row-button" type="button" onClick={() => onSelect(auction.id)}>
                      <strong>{auction.reference_id}</strong>
                      <span>{auction.name}</span>
                    </button>
                  </td>
                  <td>{money(auction.current_lowest_bid)}</td>
                  <td>{dateTime(auction.close_at)}</td>
                  <td>{dateTime(auction.forced_close_at)}</td>
                  <td>
                    <span className={`status-badge ${statusClass(auction.status)}`}>{auction.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pagination-bar">
            <span>
              Showing {firstItem}-{lastItem} of {total}
            </span>
            <div>
              <button
                className="secondary-button"
                type="button"
                onClick={() => onPageChange(offset - limit)}
                disabled={!canGoBack}
              >
                Previous
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => onPageChange(offset + limit)}
                disabled={!canGoForward}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
