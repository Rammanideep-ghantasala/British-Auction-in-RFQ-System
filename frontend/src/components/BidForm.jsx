export function BidForm({ auction, user, onSubmit }) {
  const disabled = auction.status !== "Active" || user.role !== "supplier";

  function handleSubmit(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);

    onSubmit({
      freight_charges: Number(data.get("freight_charges")),
      origin_charges: Number(data.get("origin_charges")),
      destination_charges: Number(data.get("destination_charges")),
      transit_time: data.get("transit_time"),
      validity: data.get("validity")
    });

    event.currentTarget.reset();
  }

  return (
    <form className="stacked-form" onSubmit={handleSubmit}>
      <div className="form-grid">
        <label>
          Carrier
          <input value={user.role === "supplier" ? user.company_name : "Buyer view"} readOnly disabled />
        </label>
        <label>
          Freight Charges
          <input name="freight_charges" type="number" min="0" step="100" required disabled={disabled} />
        </label>
        <label>
          Origin Charges
          <input name="origin_charges" type="number" min="0" step="100" required disabled={disabled} />
        </label>
        <label>
          Destination Charges
          <input name="destination_charges" type="number" min="0" step="100" required disabled={disabled} />
        </label>
        <label>
          Transit Time
          <input name="transit_time" placeholder="2 days" required disabled={disabled} />
        </label>
        <label>
          Validity of Quote
          <input name="validity" placeholder="7 days" required disabled={disabled} />
        </label>
      </div>
      <div className="form-actions">
        <button className="primary-button" type="submit" disabled={disabled}>
          Submit Quote
        </button>
      </div>
    </form>
  );
}
