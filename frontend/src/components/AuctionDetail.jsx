import { BidForm } from "./BidForm";
import { dateTime, money, statusClass } from "../formatters";

export function AuctionDetail({ auction, user, onSubmitBid }) {
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
          <RankingsTable rankings={auction.rankings} />
        </section>

        <section className="plain-section">
          <div className="section-heading">
            <h3>Quote Submission</h3>
            <span>{auction.config.trigger_type}</span>
          </div>
          <BidForm auction={auction} user={user} onSubmit={onSubmitBid} />
        </section>
      </div>

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
        </section>
      </div>
    </section>
  );
}

function RankingsTable({ rankings }) {
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
            <tr key={`${quote.carrier_name}-${quote.submitted_at}`}>
              <td>
                <strong>{quote.rank}</strong>
              </td>
              <td>{quote.carrier_name}</td>
              <td>{money(quote.freight_charges)}</td>
              <td>{money(quote.origin_charges)}</td>
              <td>{money(quote.destination_charges)}</td>
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
