import { useEffect, useState } from "react";
import { Message, ChatResponse } from "../types";

const API_URL = "http://localhost:8000";

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 0,
      role: "bot",
      content: "Hello! I'm your AI support assistant. How can I help you today?",
      timestamp: new Date(),
    },
  ]);
  const [loading, setLoading] = useState(false);
 const [sessionId, setSessionId] = useState("");

useEffect(() => {
  setSessionId(Math.random().toString(36).slice(2));
}, []);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = {
      id: Date.now(),
      role: "user",
      content: text.trim(),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          telegram_chat_id: sessionId,
          message: text.trim(),
          customer_name: "Web User",
        }),
      });

      const data: ChatResponse = await res.json();

      const botMsg: Message = {
        id: Date.now() + 1,
        role: "bot",
        content: data.answer,
        sentiment_label: data.sentiment_label as Message["sentiment_label"],
        sentiment_score: data.sentiment_score,
        escalated: data.escalated,
        cache_hit: data.cache_hit,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "bot",
          content: "Connection error. Is the API running?",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: 0,
        role: "bot",
        content: "Hello! How can I help you today?",
        timestamp: new Date(),
      },
    ]);
  };

  return { messages, loading, sessionId, sendMessage, clearChat };
}