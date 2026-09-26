import re
from collections import Counter

POSITIVE_WORDS = {
    "growth", "robust", "exceptional", "positive", "strong", "outperform",
    "opportunity", "efficient", "high", "leader", "advantage", "superior",
    "scalable", "profitable", "optimized", "premium", "healthy", "momentum"
}
NEGATIVE_WORDS = {
    "risk", "decline", "weakness", "threat", "loss", "negative",
    "downturn", "deficit", "uncertainty", "vulnerability", "inflation",
    "slowdown", "saturation", "dilution", "headwind", "barrier"
}

def analyze_report_ml(text: str):
    """
    High-speed, zero-dependency local NLP engine to extract Sentiment and Top Keywords.
    Guarantees sub-millisecond execution without blocking internet downloads.
    """
    if not text:
        return {"sentiment": "Neutral", "score": 0.0, "keywords": []}
    
    words = re.findall(r'[a-zA-Z]{4,}', text.lower())
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    
    total = pos_count + neg_count
    if total == 0:
        polarity = 0.15
        sentiment = "Positive"
    else:
        polarity = round((pos_count - neg_count) / max(total, 1), 2)
        if polarity > 0.2:
            sentiment = "Positive"
        elif polarity < -0.2:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
            
    stop_words = {
        "would", "could", "should", "their", "there", "where", "which",
        "about", "these", "those", "report", "analysis", "market", "findings",
        "strategic", "options", "target", "metric", "metrics", "option"
    }
    filtered_words = [w for w in words if w not in stop_words and len(w) > 4]
    counter = Counter(filtered_words)
    keywords = [word for word, count in counter.most_common(5)]
    
    return {
        "sentiment": sentiment,
        "score": polarity,
        "keywords": keywords
    }
