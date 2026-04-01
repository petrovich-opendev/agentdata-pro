import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MessageCircleHeart } from "lucide-react";
import { useAuthStore } from "../stores/authStore";

type Step = "request" | "verify";

export default function Landing() {
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);

  const [step, setStep] = useState<Step>("request");
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function normalizeUsername(raw: string): string {
    const trimmed = raw.trim();
    return trimmed.startsWith("@") ? trimmed : `@${trimmed}`;
  }

  async function handleRequestCode(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const trimmed = username.trim().replace(/^@/, "");
    if (trimmed.length < 2) {
      setError("Enter a valid Telegram username (e.g. @username)");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/request-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_username: normalizeUsername(username) }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? `Request failed (${res.status})`);
      }
      setStep("verify");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!/^\d{6}$/.test(code)) {
      setError("Enter a 6-digit code");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/verify-code", {
        credentials: "include",
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          telegram_username: normalizeUsername(username),
          code,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? `Verification failed (${res.status})`);
      }
      const data = await res.json();
      setToken(data.access_token);
      navigate("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f0f23] px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <MessageCircleHeart className="w-12 h-12 text-indigo-400 mb-3" />
          <h1 className="text-2xl font-bold text-gray-100">BioCoach</h1>
          <p className="text-gray-500 text-sm mt-1">
            Personal AI Health Advisor
          </p>
        </div>

        <div className="bg-[#1e1e3a] rounded-xl border border-[#3a3a5c] p-6">
          {step === "request" ? (
            <form onSubmit={handleRequestCode} className="space-y-4">
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Telegram username
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="@username"
                  required
                  autoComplete="username"
                  className="w-full px-3 py-2 bg-[#0f0f23] text-gray-100 border border-[#3a3a5c] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-500"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !username.trim()}
                className="w-full py-2 px-4 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? "Sending..." : "Get code"}
              </button>
              <p className="text-xs text-gray-500 text-center">
                First, send{" "}
                <span className="font-mono">/start</span> to the bot in
                Telegram, then enter your username here.
              </p>
            </form>
          ) : (
            <form onSubmit={handleVerifyCode} className="space-y-4">
              <div>
                <label
                  htmlFor="code"
                  className="block text-sm font-medium text-gray-300 mb-1"
                >
                  Verification code
                </label>
                <input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  value={code}
                  onChange={(e) =>
                    setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  placeholder="6-digit code"
                  maxLength={6}
                  required
                  className="w-full px-3 py-2 bg-[#0f0f23] text-gray-100 border border-[#3a3a5c] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-500 text-center text-lg tracking-widest"
                />
              </div>
              <button
                type="submit"
                disabled={loading || code.length !== 6}
                className="w-full py-2 px-4 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? "Verifying..." : "Verify"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStep("request");
                  setCode("");
                  setError("");
                }}
                className="w-full text-sm text-gray-500 hover:text-gray-300"
              >
                Back
              </button>
            </form>
          )}

          {error && (
            <p className="mt-3 text-sm text-red-400 text-center">{error}</p>
          )}
        </div>
      </div>
    </div>
  );
}
