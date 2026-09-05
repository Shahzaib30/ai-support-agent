export interface Message {
  id: number;
  role: "user" | "bot";
  content: string;
  sentiment_label?: "positive" | "neutral" | "negative";
  sentiment_score?: number;
  escalated?: boolean;
  cache_hit?: boolean;
  timestamp: Date;
}

export interface ChatResponse {
  answer: string;
  escalated: boolean;
  cache_hit: boolean;
  sentiment_label: string;
  sentiment_score: number;
}

export interface Stats {
  today: {
    total_messages: number;
    total_conversations: number;
    total_escalations: number;
    avg_sentiment: number;
    avg_response_ms: number;
    cache_hit_rate: number;
  };
}