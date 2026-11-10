import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuctionList } from "./AuctionList";
import { BidForm } from "./BidForm";
import { LoginPanel } from "./LoginPanel";
import { money } from "../formatters";

const activeAuction = {
  status: "Active"
};

const supplierUser = {
  role: "supplier",
  company_name: "Apex Roadways"
};

afterEach(() => {
  cleanup();
});

async function fillBidForm() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/Freight Charges/i), "1200.50");
  await user.type(screen.getByLabelText(/Origin Charges/i), "10.25");
  await user.type(screen.getByLabelText(/Destination Charges/i), "5.75");
  await user.type(screen.getByLabelText(/Transit Time/i), "2 days");
  await user.type(screen.getByLabelText(/Validity of Quote/i), "7 days");
  return user;
}

describe("LoginPanel", () => {
  it("fills email and password when a demo account is selected", async () => {
    const user = userEvent.setup();
    render(<LoginPanel onLogin={vi.fn()} isLoading={false} />);

    await user.click(screen.getByRole("button", { name: /Buyer: buyer@gocomet\.test/i }));

    expect(screen.getByLabelText(/Email/i).value).toBe("buyer@gocomet.test");
    expect(screen.getByLabelText(/Password/i).value).toBe("password123");
  });
});

describe("BidForm", () => {
  it("preserves typed values when the API rejects the bid", async () => {
    const onSubmit = vi.fn().mockResolvedValue(false);
    render(<BidForm auction={activeAuction} user={supplierUser} onSubmit={onSubmit} />);
    const user = await fillBidForm();

    await user.click(screen.getByRole("button", { name: /Submit Quote/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      freight_charges: "1200.5",
      origin_charges: "10.25",
      destination_charges: "5.75",
      transit_time: "2 days",
      validity: "7 days"
    });
    expect(screen.getByLabelText(/Freight Charges/i).value).toBe("1200.5");
  });

  it("resets typed values after a successful bid", async () => {
    const onSubmit = vi.fn().mockResolvedValue(true);
    render(<BidForm auction={activeAuction} user={supplierUser} onSubmit={onSubmit} />);
    const user = await fillBidForm();

    await user.click(screen.getByRole("button", { name: /Submit Quote/i }));

    expect(screen.getByLabelText(/Freight Charges/i).value).toBe("");
    expect(screen.getByLabelText(/Transit Time/i).value).toBe("");
  });
});

describe("AuctionList", () => {
  it("renders pagination controls and requests the next page", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(
      <AuctionList
        auctions={[
          {
            id: "rfq-1",
            reference_id: "RFQ-1",
            name: "First RFQ",
            current_lowest_bid: "1200.50",
            close_at: "2026-01-01T10:00:00Z",
            forced_close_at: "2026-01-01T10:30:00Z",
            status: "Active"
          }
        ]}
        selectedId="rfq-1"
        canCreate
        page={{ total: 30, limit: 25, offset: 0 }}
        onSelect={vi.fn()}
        onCreate={vi.fn()}
        onPageChange={onPageChange}
      />
    );

    expect(screen.getByText("Showing 1-1 of 30")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Next/i }));

    expect(onPageChange).toHaveBeenCalledWith(25);
  });
});

describe("formatters", () => {
  it("keeps quote precision visible", () => {
    expect(money("1200.50")).toContain("1,200.50");
  });
});
