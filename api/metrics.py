from prometheus_client import Counter, Gauge, Histogram

MESSAGES_TOTAL = Counter("messages_total", "Total messages processed")
ESCALATIONS_TOTAL = Counter("escalations_total", "Total escalations triggered")
CACHE_HITS = Counter("cache_hits_total", "Total Redis cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Total Redis cache misses")
RESPONSE_TIME = Histogram("rag_response_seconds", "RAG pipeline response time in seconds")
ACTIVE_CONVERSATIONS = Gauge("active_conversations", "Currently active conversations")
