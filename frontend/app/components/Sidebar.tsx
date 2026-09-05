interface Props {
  sessionId: string;
  onClear: () => void;
}

const capabilities = [
  "Answers from your documents",
  "Sentiment detection",
  "Auto escalation to humans",
  "Conversation memory",
  "Redis response caching",
];

export default function Sidebar({ sessionId, onClear }: Props) {
  return (
    <aside className="w-64 border-r border-slate-800 flex flex-col p-5 gap-6 shrink-0">

      {/* Agent Info */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs text-emerald-400 font-medium">Online</span>
        </div>
        <h1 className="text-lg font-semibold tracking-tight">Support Agent</h1>
        <p className="text-xs text-slate-500 mt-0.5">Powered by DeepSeek + RAG</p>
      </div>

      {/* Capabilities */}
      <div className="space-y-3">
        <p className="text-xs text-slate-500 uppercase tracking-wider">Capabilities</p>
        {capabilities.map((cap) => (
          <div key={cap} className="flex items-start gap-2 text-sm text-slate-400">
            <span className="text-emerald-500 mt-0.5">✓</span>
            {cap}
          </div>
        ))}
      </div>

      {/* Links */}
      <div className="space-y-3">
        <p className="text-xs text-slate-500 uppercase tracking-wider">Quick Links</p>
        <a href="/dashboard" className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
          <span>📊</span> Dashboard
        </a>
        <a href="http://localhost:9090" target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
          <span>🔥</span> Prometheus
        </a>
        <a href="http://localhost:3000" target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
          <span>📈</span> Grafana
        </a>
      </div>

      {/* Actions */}
      <div className="space-y-2">
        <button onClick={onClear} className="w-full text-left text-sm text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-2">
          <span>🗑️</span> Clear conversation
        </button>
      </div>

      {/* Session */}
      <div className="mt-auto space-y-1">
        <p className="text-xs text-slate-500 uppercase tracking-wider">Session ID</p>
        <p className="text-xs text-slate-600 font-mono break-all">{sessionId}</p>
      </div>
    </aside>
  );
}