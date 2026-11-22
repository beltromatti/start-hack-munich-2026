import { FormEvent, useState } from "react";
import { Me, post } from "../api";
import { Ground, Mark } from "./Ground";

// The sign-in: an account in the register (backend/app/accounts.py), a session cookie the page never reads.
export function Login({ done }: { done: (me: Me) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const go = (e: FormEvent) => {
    e.preventDefault();
    if (busy || !username.trim() || !password) return;
    setBusy(true); setError("");
    post<Me>("/api/login", { username: username.trim(), password })
      .then(done)
      .catch((x: Error) => setError(x.message.startsWith("429") ? "Too many tries. Wait ten minutes, then try again." : x.message.startsWith("401") ? "Wrong username or password." : "The desk cannot be reached right now."))
      .finally(() => setBusy(false));
  };
  return (
    <div className="dk-app" data-mood="calm">
      <Ground mood="calm" />
      <main className="dk-login">
        <form onSubmit={go} aria-labelledby="dk-login-h">
          <div className="dk-logo"><Mark size={34} />Milan Forwarding</div>
          <h1 id="dk-login-h">Sign in to the desk</h1>
          <p>Giulia answers requests, prices and books on her own. Here you follow every shipment and step in when you want.</p>
          <label>Username<input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {error ? <p className="dk-login-err" role="alert">{error}</p> : null}
          <button className="dk-btn k big" disabled={busy || !username.trim() || !password}>{busy ? "Signing in" : "Sign in"}</button>
        </form>
      </main>
    </div>
  );
}
