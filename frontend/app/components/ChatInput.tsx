import { useState } from "react";

interface Props {
  onSend: (text: string) => void;
  loading: boolean;
}

export default function ChatInput({ onSend, loading }: Props) {
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim() || loading) return;
    onSend(input.trim());
    setInput("");
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-slate-800 px-6 py-4">
      <div className="flex gap-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Type a message..."
          rows={1}
          disabled={loading}
          className="flex-1 bg-slate-800 text-slate-100
                     placeholder-slate-500 rounded-xl px-4 py-3
                     text-sm resize-none focus:outline-none
                     focus:ring-1 focus:ring-indigo-500
                     disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="bg-indigo-600 hover:bg-indigo-500
                     disabled:opacity-40 disabled:cursor-not-allowed
                     text-white px-5 py-3 rounded-xl text-sm
                     font-medium transition-colors shrink-0"
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
      <p className="text-xs text-slate-600 mt-2">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}