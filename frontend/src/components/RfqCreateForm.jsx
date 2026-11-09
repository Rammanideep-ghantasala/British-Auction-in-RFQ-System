import { addMinutes, fromDateTimeLocal, toDateTimeLocal } from "../formatters";

export function RfqCreateForm({ suppliers, onCancel, onSubmit }) {
  const now = new Date();

  function handleSubmit(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);

    onSubmit({
      name: data.get("name"),
      reference_id: data.get("reference_id"),
      british_auction_enabled: data.get("british_auction_enabled") === "on",
      start_at: fromDateTimeLocal(data.get("start_at")),
      close_at: fromDateTimeLocal(data.get("close_at")),
      forced_close_at: fromDateTimeLocal(data.get("forced_close_at")),
      pickup_at: fromDateTimeLocal(data.get("pickup_at")),
      supplier_ids: data.getAll("supplier_ids"),
      config: {
        trigger_window_minutes: Number(data.get("trigger_window_minutes")),
        extension_minutes: Number(data.get("extension_minutes")),
        trigger_type: data.get("trigger_type")
      }
    });
  }

  return (
    <section className="auction-detail">
      <div className="detail-heading">
        <div>
          <p className="eyebrow">RFQ Creation</p>
          <h2>New British Auction RFQ</h2>
        </div>
      </div>

      <form className="stacked-form create-form" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            RFQ Name
            <input name="name" required />
          </label>
          <label>
            Reference ID
            <input name="reference_id" defaultValue={`RFQ-BA-${Math.floor(1000 + Math.random() * 9000)}`} required />
          </label>
          <label>
            Bid Start Date & Time
            <input name="start_at" type="datetime-local" defaultValue={toDateTimeLocal(now)} required />
          </label>
          <label>
            Bid Close Date & Time
            <input name="close_at" type="datetime-local" defaultValue={toDateTimeLocal(addMinutes(now, 30))} required />
          </label>
          <label>
            Forced Bid Close Date & Time
            <input name="forced_close_at" type="datetime-local" defaultValue={toDateTimeLocal(addMinutes(now, 90))} required />
          </label>
          <label>
            Pickup / Service Date
            <input name="pickup_at" type="datetime-local" defaultValue={toDateTimeLocal(addMinutes(now, 24 * 60))} required />
          </label>
        </div>

        <div className="option-row">
          <label className="toggle-label">
            <input name="british_auction_enabled" type="checkbox" defaultChecked />
            <span>British Auction</span>
          </label>
        </div>

        <div className="config-panel">
          <div className="section-heading">
            <h3>British Auction Configuration</h3>
          </div>
          <div className="form-grid">
            <label>
              Trigger Window (X Minutes)
              <input name="trigger_window_minutes" type="number" min="1" step="1" defaultValue="10" required />
            </label>
            <label>
              Extension Duration (Y Minutes)
              <input name="extension_minutes" type="number" min="1" step="1" defaultValue="5" required />
            </label>
          </div>
          <fieldset className="segmented-field">
            <legend>Extension Trigger</legend>
            <label>
              <input type="radio" name="trigger_type" value="bid-received" defaultChecked />
              <span>Bid Received</span>
            </label>
            <label>
              <input type="radio" name="trigger_type" value="any-rank-change" />
              <span>Any Rank Change</span>
            </label>
            <label>
              <input type="radio" name="trigger_type" value="l1-rank-change" />
              <span>L1 Change</span>
            </label>
          </fieldset>
        </div>

        <div className="config-panel">
          <div className="section-heading">
            <h3>Invited Suppliers</h3>
            <span>{suppliers.length} available</span>
          </div>
          {suppliers.length === 0 ? (
            <p className="muted">No supplier users are available.</p>
          ) : (
            <div className="supplier-checklist">
              {suppliers.map((supplier) => (
                <label className="toggle-label" key={supplier.id}>
                  <input name="supplier_ids" type="checkbox" value={supplier.id} defaultChecked />
                  <span>{supplier.company_name}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="primary-button" type="submit">
            Create RFQ
          </button>
        </div>
      </form>
    </section>
  );
}
