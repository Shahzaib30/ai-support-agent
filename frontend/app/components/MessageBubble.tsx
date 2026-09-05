import { Message } from "../types";

interface Props {
  message: Message;
}

const sentimentConfig = {
  positive: { color: "text-emerald-400", emoji: "😊" },
  neutral:  { color: "text-slate-400",   emoji: "😐" },
  negative: { color: "text-red-400",     emoji: "😞" },
};

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const sentiment = message.sentiment_label
    ? sentimentConfig[message.sentiment_label]
    : null;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`flex flex-col gap-1 max-w-xl ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        {/* Bubble */}
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? "bg-indigo-600 text-white rounded-br-sm"
              : "bg-slate-800 text-slate-100 rounded-bl-sm"
          }`}
        >
          {message.content}
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-2 px-1">
          {/* Time */}
          <span className="text-xs text-slate-600">
            {message.timestamp.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>

          {/* Sentiment */}
          {sentiment && (
            <span className={`text-xs ${sentiment.color}`}>
              {sentiment.emoji} {message.sentiment_label}
            </span>
          )}

          {/* Cache hit */}
          {message.cache_hit && (
            <span className="text-xs text-amber-400">
              ⚡ cached
            </span>
          )}

          {/* Escalated */}
          {message.escalated && (
            <span className="text-xs text-red-400">
              🚨 escalated
            </span>
          )}
        </div>
      </div>
    </div>
  );
}