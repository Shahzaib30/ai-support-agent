"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Stats {
  total_messages:      number;
  total_conversations: number;
  total_escalations:   number;
  avg_sentiment:       number;
  avg_response_ms:     number;
  cache_hit_rate:      number;
}

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col gap-2">
      <p className="text-xs text-slate-500 uppercase tracking-widest">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-slate-600">{sub}</p>}
    </div>
  );
}

function SentimentBar({ value }: { value: number }) {
  // value is -1 to 1, convert to 0-100
  const pct = Math.round(((value + 1) / 2) * 100);
  const color =
    value > 0.2
      ? "bg-emerald-500"
      : value < -0.2
      ? "bg-red-500"
      : "bg-amber-500";

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col gap-3">
      <p className="text-xs text-slate-500 uppercase tracking-widest">
        Avg Sentiment
      </p>
      <p
        className={`text-3xl font-bold ${
          value > 0.2
            ? "text-emerald-400"
            : value < -0.2
            ? "text-red-400"
            : "text-amber-400"
        }`}
      >
        {value > 0.2 ? "😊 Positive" : value < -0.2 ? "😞 Negative" : "😐 Neutral"}
      </p>
      <div className="w-full bg-slate-800 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-600">Score: {value.toFixed(2)}</p>
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats]       = useState<Stats | null>(null);
  const [loading, setLoading]   = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [error, setError]       = useState(false);

  const fetchStats = async () => {
    try {
      const res  = await fetch(`${API_URL}/stats`);
      const data = await res.json();
      setStats(data.today);
      setLastUpdated(new Date().toLocaleTimeString());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Standard fetch-on-mount-plus-poll pattern; fetchStats' setState calls
    // happen after an await, not synchronously within this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Header */}
      <header className="border-b border-slate-800 px-8 py-5 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Support Dashboard</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Today&apos;s metrics · auto-refreshes every 30s
          </p>
        </div>
        <div className="flex items-center gap-4">
          {lastUpdated && (
            <p className="text-xs text-slate-600">Updated {lastUpdated}</p>
          )}
          <button
            onClick={fetchStats}
            className="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg transition-colors"
          >
            Refresh
          </button>
          <Link
            href="/"
            className="text-xs bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 rounded-lg transition-colors"
          >
            ← Chat
          </Link>
        </div>
      </header>

      <main className="px-8 py-8 max-w-6xl mx-auto">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-6 text-sm text-red-400">
            Could not reach API. Is the backend running?
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="bg-slate-900 border border-slate-800 rounded-2xl p-6 h-32 animate-pulse"
              />
            ))}
          </div>
        ) : stats ? (
          <>
            {/* Stat cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <StatCard
                label="Total Messages"
                value={stats.total_messages.toLocaleString()}
                sub="user messages today"
                color="text-indigo-400"
              />
              <StatCard
                label="Conversations"
                value={stats.total_conversations.toLocaleString()}
                sub="unique sessions today"
                color="text-sky-400"
              />
              <StatCard
                label="Escalations"
                value={stats.total_escalations.toLocaleString()}
                sub="routed to human agents"
                color={
                  stats.total_escalations > 0
                    ? "text-red-400"
                    : "text-emerald-400"
                }
              />
              <StatCard
                label="Cache Hit Rate"
                value={`${stats.cache_hit_rate.toFixed(1)}%`}
                sub="Redis cache efficiency"
                color={
                  stats.cache_hit_rate > 50
                    ? "text-emerald-400"
                    : "text-amber-400"
                }
              />
              <StatCard
                label="Avg Response"
                value={`${Math.round(stats.avg_response_ms)}ms`}
                sub="RAG pipeline latency"
                color={
                  stats.avg_response_ms < 2000
                    ? "text-emerald-400"
                    : "text-red-400"
                }
              />
              <StatCard
                label="Active Conversations"
                value={stats.total_conversations.toLocaleString()}
                sub="tracked in PostgreSQL"
                color="text-purple-400"
              />
            </div>

            {/* Sentiment bar */}
            <div className="mt-4">
              <SentimentBar value={stats.avg_sentiment} />
            </div>

            {/* Links to external tools */}
            <div className="mt-8 grid grid-cols-2 md:grid-cols-3 gap-4">
              <a
                href="http://localhost:3000"
                target="_blank"
                rel="noreferrer"
                className="bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-2xl p-5 flex flex-col gap-1 transition-colors"
              >
                <p className="text-sm font-medium text-slate-200">
                  Grafana
                </p>
                <p className="text-xs text-slate-500">
                  Full metrics dashboard
                </p>
              </a>
              <a
                href="http://localhost:9090"
                target="_blank"
                rel="noreferrer"
                className="bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-2xl p-5 flex flex-col gap-1 transition-colors"
              >
                <p className="text-sm font-medium text-slate-200">
                  Prometheus
                </p>
                <p className="text-xs text-slate-500">Raw metrics explorer</p>
              </a>
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-2xl p-5 flex flex-col gap-1 transition-colors"
              >
                <p className="text-sm font-medium text-slate-200">
                  API Docs
                </p>
                <p className="text-xs text-slate-500">FastAPI Swagger UI</p>
              </a>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}