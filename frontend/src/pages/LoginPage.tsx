// src/pages/LoginPage.tsx
import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import octagonLogo from "../assets/footer-logo-octagon2.png";

const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: Location } };

  const [email, setEmail] = useState("luis@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const from = location.state?.from?.pathname || "/dashboard";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError("Credenciales inválidas o error de servidor.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page h-screen flex items-center justify-center">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-box">
            <img src={octagonLogo} alt="Octagon" />
          </div>
          <div>
            <div className="login-title">RMCP Invoices</div>
          </div>
        </div>

        <div className="login-copy">
          <h1>Welcome back</h1>
          <p>Sign in to continue managing invoices.</p>
        </div>

        <form onSubmit={handleSubmit} className="mt-4">
          <label className="form-label">
            Email
            <input
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>

          <label className="form-label mt-3">
            Password
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          {error && <div className="form-error mt-2">{error}</div>}

          <button type="submit" className="btn-primary login-submit mt-4" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>

          <button type="button" className="register-disabled mt-3" disabled>
            Register account
            <span>Coming soon</span>
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
