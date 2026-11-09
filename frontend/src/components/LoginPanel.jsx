const demoAccounts = [
  { label: "Buyer", email: "buyer@gocomet.test" },
  { label: "Supplier", email: "apex@carrier.test" },
  { label: "Supplier", email: "swift@carrier.test" }
];

const reviewerPassword = import.meta.env.VITE_REVIEWER_PASSWORD || "password123";

export function LoginPanel({ onLogin, isLoading }) {
  function handleSubmit(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onLogin(data.get("email"), data.get("password"));
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="login-title">
        <div>
          <p className="eyebrow">Secure RFQ Console</p>
          <h1 id="login-title">Sign in to continue</h1>
          <p className="muted">Use a buyer account to create RFQs or a supplier account to submit invited quotes.</p>
        </div>

        <form className="stacked-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input name="email" type="email" defaultValue="buyer@gocomet.test" required />
          </label>
          <label>
            Password
            <input name="password" type="password" defaultValue={reviewerPassword} required />
          </label>
          <button className="primary-button" type="submit" disabled={isLoading}>
            {isLoading ? "Signing in" : "Sign In"}
          </button>
        </form>

        <div className="demo-accounts" aria-label="Demo accounts">
          {demoAccounts.map((account) => (
            <button
              className="secondary-button"
              type="button"
              key={account.email}
              onClick={() => onLogin(account.email, reviewerPassword)}
              disabled={isLoading}
            >
              {account.label}: {account.email}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
