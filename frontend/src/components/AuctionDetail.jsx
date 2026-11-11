import { BidForm } from "./BidForm";
import { dateTime, money, statusClass } from "../formatters";

export function AuctionDetail({ auction, user, onSubmitBid, onHistoryChange = () => {} }) {
  if (!auction) {
    return (
      <section className="auction-detail">
        <div className="empty-state">
          <h2>Select an auction</h2>
          <p>Choose an RFQ from the listing to view bids and activity.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="auction-detail">
      <div className="detail-heading">
        <div>
          <p className="eyebrow">Auction Details</p>
          <h2>
            {auction.reference_id} - {auction.name}
          </h2>
        </div>
        <span className={`status-badge ${statusClass(auction.status)}`}>{auction.status}</span>
      </div>

      <div className="metric-grid" aria-label="Auction summary">
        <div>
          <span>Current Lowest Bid</span>
          <strong>{money(auction.current_lowest_bid)}</strong>
        </div>
        <div>
          <span>Current Bid Close</span>
          <strong>{dateTime(auction.close_at)}</strong>
        </div>
        <div>
          <span>Forced Close</span>
          <strong>{dateTime(auction.forced_close_at)}</strong>
        </div>
        <div>
          <span>Pickup / Service</span>
          <strong>{dateTime(auction.pickup_at)}</strong>
        </div>
      </div>

      <div className="detail-grid">
        <section className="plain-section">
          <div className="section-heading">
            <h3>Supplier Ranking</h3>
            <span>{auction.rankings.length} carriers</span>
          </div>
          <RankingsTable rankings={auction.rankings} user={user} />
        </section>

        <section className="plain-section">
          <div className="section-heading">
            <h3>Quote Submission</h3>
            <span>{auction.config.trigger_type}</span>
          </div>
          <BidForm key={auction.id} auction={auction} user={user} onSubmit={(payload) => onSubmitBid(auction.id, payload)} />
        </section>
      </div>

      <section className="plain-section lower-grid" aria-label="Bid history">
        <div className="section-heading"><h3>{user.role === "buyer" ? "All Submitted Bids" : "Your Bid History"}</h3><span>Sorted by total price</span></div>
        <BidHistory bids={auction.bids || []} />
        <HistoryPager label="bids" total={auction.bids_total ?? auction.bids?.length ?? 0} offset={auction.bids_offset || 0}
          limit={auction.history_limit || 25} onChange={(offset) => onHistoryChange({ bids_offset: offset })} />
      </section>
      <div className="detail-grid lower-grid">
        <section className="plain-section">
          <div className="section-heading">
            <h3>Auction Configuration</h3>
          </div>
          <dl className="config-list">
            <div>
              <dt>Trigger Window (X)</dt>
              <dd>{auction.config.trigger_window_minutes} minutes</dd>
            </div>
            <div>
              <dt>Extension Duration (Y)</dt>
              <dd>{auction.config.extension_minutes} minutes</dd>
            </div>
            <div>
              <dt>Extension Trigger</dt>
              <dd>{auction.config.trigger_type}</dd>
            </div>
            <div>
              <dt>Original Bid Close</dt>
              <dd>{dateTime(auction.original_close_at)}</dd>
            </div>
          </dl>
        </section>

        <section className="plain-section">
          <div className="section-heading">
            <h3>Activity Log</h3>
            <span>{auction.activity_log.length} events</span>
          </div>
          <ActivityLog activity={auction.activity_log} />
          <HistoryPager label="activity" total={auction.activity_total ?? auction.activity_log.length} offset={auction.activity_offset || 0}
            limit={auction.history_limit || 25} onChange={(offset) => onHistoryChange({ activity_offset: offset })} />
        </section>
      </div>
    </section>
  );
}

function RankingsTable({ rankings, user }) {
  if (rankings.length === 0) {
    return <p className="muted">No quotes submitted.</p>;
  }

  return (
    <div className="table-wrap compact">
      <table className="quote-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Carrier</th>
            <th>Freight</th>
            <th>Origin</th>
            <th>Destination</th>
            <th>Total</th>
            <th>Transit</th>
            <th>Validity</th>
          </tr>
        </thead>
        <tbody>
          {rankings.map((quote) => (
            <tr key={quote.rank}>
              <td>
                <strong>{quote.rank}</strong>
              </td>
              <td>{quote.carrier_name}</td>
              <td>{user.role === "supplier" && quote.is_own_quote === false ? "Hidden" : money(quote.freight_charges)}</td>
              <td>{user.role === "supplier" && quote.is_own_quote === false ? "Hidden" : money(quote.origin_charges)}</td>
              <td>{user.role === "supplier" && quote.is_own_quote === false ? "Hidden" : money(quote.destination_charges)}</td>
              <td>
                <strong>{money(quote.total)}</strong>
              </td>
              <td>{quote.transit_time}</td>
              <td>{quote.validity}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BidHistory({ bids }) {
  if (!bids.length) return <p className="muted">No submitted bids.</p>;
  return <div className="table-wrap compact"><table className="quote-table">
    <thead><tr>{["Carrier", "Freight", "Origin", "Destination", "Total", "Transit", "Validity", "Submitted"].map((label) => <th key={label}>{label}</th>)}</tr></thead>
    <tbody>{bids.map((bid) => <tr key={bid.id}>
      <td>{bid.carrier_name}</td><td>{money(bid.freight_charges)}</td><td>{money(bid.origin_charges)}</td>
      <td>{money(bid.destination_charges)}</td><td>{money(bid.total)}</td><td>{bid.transit_time}</td>
      <td>{bid.validity}</td><td>{dateTime(bid.submitted_at)}</td>
    </tr>)}</tbody>
  </table></div>;
}

function HistoryPager({ label, total, offset, limit, onChange }) {
  if (total <= limit && offset === 0) return null;
  return <div className="pagination-bar" aria-label={`${label} pagination`}>
    <span>{total ? offset + 1 : 0}-{Math.min(offset + limit, total)} of {total}</span>
    <div><button className="secondary-button" type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous {label}</button>
      <button className="secondary-button" type="button" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next {label}</button></div>
  </div>;
}

function ActivityLog({ activity }) {
  if (activity.length === 0) {
    return <p className="muted">No activity yet.</p>;
  }

  return (
    <ol className="activity-log">
      {activity.map((entry) => (
        <li key={entry.id}>
          <time>{dateTime(entry.at)}</time>
          <span className="log-type">{entry.type}</span>
          <p>{entry.message}</p>
        </li>
      ))}
    </ol>
  );
}
