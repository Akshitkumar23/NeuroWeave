import re
import json
import logging
import os
import math
import httpx
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("neuroweave.vector_store")

class PureVectorStore:
    """
    A pure-Python semantic knowledge index for RAG.
    Maintains a local JSON file store. Computes cosine similarity.
    Dual-mode: Semantic Embeddings (online) or Keyphrase-TFIDF (offline).
    """
    def __init__(self, storage_path: str = "storage/vector_store.json"):
        self.storage_path = storage_path
        self.documents: List[Dict[str, Any]] = []
        self._ensure_storage()
        self.load()

    def _ensure_storage(self):
        folder = os.path.dirname(self.storage_path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        if not os.path.exists(self.storage_path):
            self.save()

    def save(self):
        """
        Saves the memory store documents to the local JSON file.
        Explicitly uses utf-8 encoding to support international characters cleanly.
        """
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.documents, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving vector database: {e}")

    def load(self):
        """
        Loads the memory store documents from the local JSON file.
        Explicitly uses utf-8 encoding and safely handles JSON parsing issues.
        """
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.documents = json.load(f) or []
        except Exception as e:
            logger.error(f"Error loading vector database: {e}")
            self.documents = []

    async def get_embedding(self, text: str, api_key: Optional[str] = None) -> Optional[List[float]]:
        """
        Fetches text embeddings from Gemini API if online, else returns None.
        Includes logging for non-200 responses to aid debugging.
        """
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
            
        if not api_key:
            return None
            
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": "models/text-embedding-004",
                "content": {
                    "parts": [{"text": text}]
                }
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    return response.json()["embedding"]["values"]
                else:
                    logger.warning(
                        f"Gemini API returned status code {response.status_code}: {response.text}. "
                        f"Falling back to TF-IDF matching."
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch remote semantic embedding, falling back to TF-IDF: {e}")
        return None

    def _tokenize(self, text: str) -> List[str]:
        """
        Safely tokenizes input string, converting to lowercase and stripping non-alphanumeric.
        Filters out common english stopwords and single-character words.
        """
        if not text or not isinstance(text, str):
            return []
        # Simple lowercase tokenizing, stripping non-alphanumeric
        words = re.sub(r"[^\w\s]", " ", text.lower()).split()
        # Filter short words and common stopwords
        stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "is", "are", "of", "that", "it"}
        return [w for w in words if w not in stopwords and len(w) > 1]

    def _compute_tfidf_vector(self, text: str) -> Dict[str, float]:
        """
        Computes term-frequency (TF) vector, normalized to unit length.
        Maintained for backwards compatibility with any existing files.
        """
        tokens = self._tokenize(text)
        if not tokens:
            return {}
            
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0.0) + 1.0
            
        # Normalize
        length = math.sqrt(sum(v * v for v in tf.values()))
        if length > 0:
            for k in tf:
                tf[k] /= length
        return tf

    def _cosine_similarity_tfidf(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """
        Computes basic dot product of pre-normalized TF vectors.
        Maintained for backwards compatibility.
        """
        score = 0.0
        for token, val in vec1.items():
            if token in vec2:
                score += val * vec2[token]
        return score

    def _compute_proper_tfidf_similarity(
        self, 
        query: str, 
        doc_text: str, 
        df: Dict[str, int], 
        N: int
    ) -> float:
        """
        Computes the standard TF-IDF Cosine Similarity between a query and a document.
        Incorporate standard Inverse Document Frequency (IDF) derived dynamically from the corpus.
        Formula: IDF(term) = ln((1 + N) / (1 + DF(term))) + 1
        """
        query_tokens = self._tokenize(query)
        doc_tokens = self._tokenize(doc_text)
        if not query_tokens or not doc_tokens:
            return 0.0

        # Term frequencies (raw counts)
        query_tf = {}
        for token in query_tokens:
            query_tf[token] = query_tf.get(token, 0.0) + 1.0

        doc_tf = {}
        for token in doc_tokens:
            doc_tf[token] = doc_tf.get(token, 0.0) + 1.0

        # Calculate TF-IDF vectors
        vec_q = {}
        for t, tf in query_tf.items():
            term_df = df.get(t, 0)
            idf = math.log((1 + N) / (1 + term_df)) + 1.0
            vec_q[t] = tf * idf

        vec_d = {}
        for t, tf in doc_tf.items():
            term_df = df.get(t, 0)
            idf = math.log((1 + N) / (1 + term_df)) + 1.0
            vec_d[t] = tf * idf

        norm_q = math.sqrt(sum(v * v for v in vec_q.values()))
        norm_d = math.sqrt(sum(v * v for v in vec_d.values()))

        if norm_q == 0.0 or norm_d == 0.0:
            return 0.0

        dot_product = sum(vec_q[t] * vec_d.get(t, 0.0) for t in vec_q)
        return dot_product / (norm_q * norm_d)

    def _cosine_similarity_embeddings(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Computes standard cosine similarity of two float embedding lists.
        Validates vector dimensions match to avoid partial dot products.
        """
        if len(vec1) != len(vec2):
            logger.warning(f"Embedding dimensions mismatch: {len(vec1)} vs {len(vec2)}")
            return 0.0
            
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))
        if norm_a > 0 and norm_b > 0:
            return dot_product / (norm_a * norm_b)
        return 0.0

    async def add_document(self, text: str, metadata: Dict[str, Any], api_key: Optional[str] = None):
        """
        Inserts a new document chunk, dynamically computing a float semantic vector
        if online or a TF-IDF helper token map if offline.
        """
        if not text or not text.strip():
            logger.warning("Attempted to index an empty or blank document. Skipping.")
            return

        embedding = await self.get_embedding(text, api_key)
        tfidf = self._compute_tfidf_vector(text)
        
        self.documents.append({
            "text": text,
            "metadata": metadata,
            "embedding": embedding,
            "tfidf": tfidf
        })
        self.save()
        logger.info(f"Ingested document into PureVectorStore. Total count: {len(self.documents)}")

    async def similarity_search(
        self, 
        query: str, 
        top_k: int = 3, 
        api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top matching documents using cosine similarity of remote semantic embeddings (online)
        or a fully-realized proper dynamic TF-IDF algorithm (offline).
        """
        if not self.documents or not query or not query.strip():
            return []
            
        query_embedding = await self.get_embedding(query, api_key)
        
        # Precompute corpus-wide Document Frequency (DF) for proper TF-IDF similarity calculation
        N = len(self.documents)
        df = {}
        for doc in self.documents:
            doc_tokens = self._tokenize(doc.get("text", ""))
            for token in set(doc_tokens):
                df[token] = df.get(token, 0) + 1
        
        matches = []
        
        for doc in self.documents:
            # Dual-path evaluation: Semantic Embeddings or Proper TF-IDF
            if query_embedding and doc.get("embedding"):
                score = self._cosine_similarity_embeddings(query_embedding, doc["embedding"])
                match_type = "semantic"
            else:
                score = self._compute_proper_tfidf_similarity(query, doc.get("text", ""), df, N)
                match_type = "tfidf"
                
            matches.append((score, doc, match_type))
            
        # Sort by similarity score descending
        matches.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        for score, doc, m_type in matches[:top_k]:
            if score > 0.05:  # threshold filter
                results.append({
                    "text": doc["text"],
                    "metadata": doc["metadata"],
                    "score": score,
                    "match_type": m_type
                })
                
        return results
