import re
from collections import Counter
try:
    from textblob import TextBlob
    import nltk
    nltk.download('punkt_tab', quiet=True)
    nltk.download('punkt', quiet=True)
except ImportError:
    TextBlob = None

def analyze_report_ml(text: str):
    """
    Analyzes the report text to extract Sentiment and Top Keyphrases.
    Returns a dict with 'sentiment' and 'keywords'.
    """
    if not TextBlob or not text:
        return {"sentiment": "Neutral", "score": 0.0, "keywords": []}
    
    # Sentiment
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    if polarity > 0.3:
        sentiment = "Positive"
    elif polarity < -0.3:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"
        
    # Keyword extraction (Simple TF based on nouns/adjectives > 4 chars)
    words = [word.lower() for word in blob.words if len(word) > 4]
    stop_words = {"would", "could", "should", "their", "there", "where", "which", "about"}
    filtered_words = [w for w in words if w not in stop_words]
    
    # Get top 5
    counter = Counter(filtered_words)
    keywords = [word for word, count in counter.most_common(5)]
    
    return {
        "sentiment": sentiment,
        "score": polarity,
        "keywords": keywords
    }
