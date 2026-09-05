"use client";

import { useRef, useEffect } from "react";
import { useChat } from "./hooks/useChat";
import MessageBubble from "./components/MessageBubble";
import ChatInput from "./components/ChatInput";
import Sidebar from "./components/Sidebar";
import LoadingDots from "./components/LoadingDots";

export default function ChatPage() {
  const { messages, loading, sessionId, sendMessage, clearChat } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-sans">

      {/* Sidebar */}
      <Sidebar sessionId={sessionId} onClear={clearChat} />

      {/* Main */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Header */}
        <header className="border-b border-slate-800 px-6 py-4 shrink-0">
          <h2 className="font-medium">Chat</h2>
          <p className="text-xs text-slate-500">
            Ask anything about our products or policies
          </p>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {loading && <LoadingDots />}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <ChatInput onSend={sendMessage} loading={loading} />
      </div>
    </div>
  );
}