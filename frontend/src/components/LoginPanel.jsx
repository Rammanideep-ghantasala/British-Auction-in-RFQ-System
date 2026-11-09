import { useState } from "react";

const demoAccounts = [
  { label: "Buyer", email: "buyer@gocomet.test" },
  { label: "Supplier", email: "apex@carrier.test" },
  { label: "Supplier", email: "swift@carrier.test" }
];

const reviewerPassword = import.meta.env.VITE_REVIEWER_PASSWORD || "password123";

export function LoginPanel({ onLogin, isLoading }) {
  const [email, setEmail] = useState("buyer@gocomet.test");
  const [password, setPassword] = useState(reviewerPassword);

  function handleSubmit(event) {
    event.preventDefault();
    onLogin(email, password);
  }

  function handleSelectAccount(account) {
    setEmail(account.email);
    setPassword(reviewerPassword);
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
            <input name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
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
              onClick={() => handleSelectAccount(account)}
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
