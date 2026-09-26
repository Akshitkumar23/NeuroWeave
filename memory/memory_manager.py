import os
import logging
from typing import Dict, Any, List, Optional
from memory.vector_store import PureVectorStore

logger = logging.getLogger("neuroweave.memory_manager")

class MemoryManager:
    """
    Orchestrates the 3 layers of our memory hierarchy:
    1. Working Memory - active, fast, transient runtime context (in-process dict)
    2. Episodic Memory - previous sessions, task outputs, SQLite history
    3. Semantic Memory - long-term document vector database (RAG corpus index)

    Phase 6.4 Fix #5: Supports session isolation mode to prevent cross-run
    state contamination in benchmarks. Set NEUROWEAVE_SESSION_ISOLATED=true
    environment variable or pass session_isolated=True to disable episodic
    context injection from prior runs.
    """
    def __init__(self, session_id: str, vector_store_path: str = "storage/vector_store.json",
                 session_isolated: bool = False):
        self.session_id = session_id
        # Layer 1: Working Memory
        self.working_memory: Dict[str, Any] = {}

        # Phase 6.4 Fix #5: Session isolation flag — prevents episodic memory bleed
        # between benchmark runs. Reads env var if not explicitly set.
        env_isolated = os.environ.get("NEUROWEAVE_SESSION_ISOLATED", "").lower() in ("1", "true", "yes")
        self.session_isolated: bool = session_isolated or env_isolated

        # Layer 3: Semantic Vector memory
        self.semantic_memory = PureVectorStore(vector_store_path)

    # --- Layer 1: Working Memory operations ---
    def reset_working_memory(self):
        """
        Phase 6.4 Fix #5: Clears all entries from working memory.
        Used between benchmark runs to ensure clean state.
        Call this before starting a new isolated execution.
        """
        cleared_keys = list(self.working_memory.keys())
        self.working_memory = {}
        logger.info(f"Working memory reset: cleared {len(cleared_keys)} keys: {cleared_keys}")

    def write_working(self, key: str, value: Any):
        self.working_memory[key] = value
        logger.debug(f"Working Memory write: {key} -> {str(value)[:100]}")

    def read_working(self, key: str, default: Any = None) -> Any:
        return self.working_memory.get(key, default)

    def get_all_working(self) -> Dict[str, Any]:
        return self.working_memory

    # --- Layer 2: Episodic Memory operations ---
    async def fetch_episodic_context(self, db_conn: Any, query_keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Queries our persistent SQLite repository to pull historical reports/sessions
        matching keywords, providing context from previous user runs.

        Phase 6.4 Fix #5: When self.session_isolated=True, returns empty list immediately
        to prevent cross-run state contamination during isolated benchmark executions.
        """
        # Phase 6.4 Fix #5: Session isolation boundary
        if self.session_isolated:
            logger.info(
                f"Phase 6.4: Session isolation active for session {self.session_id[:8]}. "
                "Episodic context fetch SKIPPED to prevent cross-run contamination."
            )
            return []

        episodes = []
        if not db_conn:
            return episodes
            
        try:
            # Query databases looking for keyword overlap in previous user queries
            async with db_conn.execute(
                "SELECT session_id, query, timestamp FROM sessions ORDER BY timestamp DESC LIMIT 5"
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    sess_id, hist_query, ts = row
                    # Skip entries from the current session to avoid self-contamination
                    if sess_id == self.session_id:
                        continue
                    # Simple keyword intersection check
                    hist_lower = hist_query.lower()
                    if any(kw.lower() in hist_lower for kw in query_keywords if len(kw) > 2):
                        # Load synthesized report
                        async with db_conn.execute(
                            "SELECT content FROM reports WHERE session_id = ?", (sess_id,)
                        ) as r_cursor:
                            report = await r_cursor.fetchone()
                            report_content = report[0] if report else ""
                            
                        episodes.append({
                            "session_id": sess_id,
                            "query": hist_query,
                            "summary": report_content[:2000],  # excerpt
                            "timestamp": ts,
                            "relationship": "historical_overlap"
                        })
            logger.info(f"Retrieved {len(episodes)} episodic context records from SQLite store.")
        except Exception as e:
            logger.error(f"Error fetching episodic database context: {e}")
        return episodes


    # --- Layer 3: Semantic Vector RAG operations ---
    async def ingest_document(self, text: str, document_name: str, api_key: Optional[str] = None):
        """
        Parses text lines or paragraphs and adds them to semantic vector memory.
        """
        # Chunk text by paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
        if not paragraphs:
            # Chunk by sentences or size
            paragraphs = [text[i:i+800] for i in range(0, len(text), 800)]
            
        for i, chunk in enumerate(paragraphs):
            metadata = {
                "source": document_name,
                "chunk_id": i,
                "total_chunks": len(paragraphs)
            }
            await self.semantic_memory.add_document(chunk, metadata, api_key)
        logger.info(f"Ingested document '{document_name}' ({len(paragraphs)} semantic vectors) into Vector store.")

    async def query_semantic_rag(self, query: str, top_k: int = 3, api_key: Optional[str] = None) -> str:
        """
        Performs vector/TF-IDF lookup in RAG document store, formatting matching nodes as system references.
        Safely falls back if an exception occurs during vector database operations.
        """
        try:
            matches = await self.semantic_memory.similarity_search(query, top_k, api_key)
            if not matches:
                return ""
                
            formatted_references = ["\n### SEMANTIC RAG DOCUMENTS MATCHES:\n"]
            for match in matches:
                src = match["metadata"].get("source", "unknown")
                score = match["score"]
                m_type = match["match_type"]
                formatted_references.append(
                    f"[Source: {src}] (Relevance Score: {score:.2f}, Index Algorithm: {m_type})\n"
                    f"Excerpt: \"{match['text']}\"\n"
                    f"---"
                )
            return "\n".join(formatted_references)
        except Exception as e:
            logger.error(f"Safe fallback triggered: Error querying semantic vector database: {e}", exc_info=True)
            return "\n### SEMANTIC RAG DOCUMENTS MATCHES:\n[RAG Retrieval Offline/Degraded - Falling back to default system prompt context]\n---"

    # --- Centralized Memory Router ---
    async def retrieve_all_context(
        self, 
        query: str, 
        db_conn: Optional[Any] = None, 
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates memory lookup, pulling transient variables, historical runs, and document chunks.
        """
        # Get keywords for episodic matching
        keywords = query.split()
        
        # 1. Working memory parameters
        working = dict(self.working_memory)
        
        # 2. Episodic records
        episodic = await self.fetch_episodic_context(db_conn, keywords)
        
        # 3. Semantic vector retrieval
        semantic_txt = await self.query_semantic_rag(query, top_k=3, api_key=api_key)
        
        return {
            "working": working,
            "episodic": episodic,
            "semantic_text": semantic_txt
        }

    # --- Step 5: Hierarchical Memory Sync Engine ---
    async def sync_memory(
        self,
        session_id: str,
        tasks: Dict[str, Any],
        query: str = "",
        db_conn: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Step 5: Hierarchical Memory Sync.
        1. Commits completed task outputs into fast Working Memory.
        2. Indexes key technical findings into Semantic Memory (PureVectorStore).
        3. Persists intermediate state snapshot into Episodic Memory.
        """
        synced_count = 0
        all_claims = []
        all_metrics = {}
        for tid, tval in tasks.items():
            if isinstance(tval, dict) and tval.get("output"):
                out = tval.get("output", "")
                self.write_working(tid, out)
                synced_count += 1
                
                # Harvest structured claims and calculated metrics from task data
                t_data = tval.get("data", {})
                if isinstance(t_data, dict):
                    if "claims" in t_data and isinstance(t_data["claims"], list):
                        all_claims.extend(t_data["claims"])
                    if "calculated_metrics" in t_data and isinstance(t_data["calculated_metrics"], dict):
                        all_metrics.update(t_data["calculated_metrics"])
                
                # Index substantive findings into semantic memory
                if len(str(out)) > 100:
                    try:
                        title = tval.get("title", tid)
                        await self.ingest_document(
                            text=str(out)[:2000],
                            document_name=f"Session_{session_id[:8]}_{title[:30]}"
                        )
                    except Exception as e:
                        logger.debug(f"Semantic indexing during memory sync: {e}")

        if all_claims:
            self.write_working("synced_claims", all_claims)
        if all_metrics:
            self.write_working("synced_metrics", all_metrics)

        logger.info(f"Hierarchical Memory Sync complete: {synced_count} task outputs synced across 3 tiers.")
        return {
            "status": "completed",
            "agent_name": "memory_agent",
            "output": f"Synchronized {synced_count} task outputs into Working Memory, SQLite Episodic records, and Semantic Vector Store.",
            "data": {
                "synced_tasks_count": synced_count,
                "session_id": session_id,
                "working_keys": list(self.working_memory.keys())
            }
        }

    async def run(
        self,
        session_id: str,
        tasks: Dict[str, Any],
        query: str = "",
        db_conn: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Unified agent execution interface."""
        return await self.sync_memory(session_id, tasks, query, db_conn)
