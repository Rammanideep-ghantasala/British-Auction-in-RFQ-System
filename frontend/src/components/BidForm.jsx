import { useState } from "react";

export function BidForm({ auction, user, onSubmit }) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const disabled = isSubmitting || auction.status !== "Active" || user.role !== "supplier";

  async function handleSubmit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);

    setIsSubmitting(true);
    try {
      const submitted = await onSubmit({
        freight_charges: data.get("freight_charges"),
        origin_charges: data.get("origin_charges"),
        destination_charges: data.get("destination_charges"),
        transit_time: data.get("transit_time"),
        validity: data.get("validity")
      });

      if (submitted !== false) {
        form.reset();
      }
    } finally {
      setIsSubmitting(false);
    }
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
          <input name="freight_charges" type="number" min="0" step="0.01" inputMode="decimal" required disabled={disabled} />
        </label>
        <label>
          Origin Charges
          <input name="origin_charges" type="number" min="0" step="0.01" inputMode="decimal" required disabled={disabled} />
        </label>
        <label>
          Destination Charges
          <input name="destination_charges" type="number" min="0" step="0.01" inputMode="decimal" required disabled={disabled} />
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
          {isSubmitting ? "Submitting" : "Submit Quote"}
        </button>
      </div>
    </form>
  );
}
