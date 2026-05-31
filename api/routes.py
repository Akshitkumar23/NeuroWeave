import os
import asyncio
import uuid
import json
import logging
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from storage.database import DatabaseManager
from storage.repository import SessionRepository
from agents.orchestrator import MasterOrchestrator

logger = logging.getLogger("neuroweave.routes")
router = APIRouter()

# Central DB Manager (initialized in main.py)
db_manager: Optional[DatabaseManager] = None

# Active sessions stream queues
session_queues: Dict[str, asyncio.Queue] = {}

class AnalysisRequest(BaseModel):
    query: str
    api_key: Optional[str] = None
    provider: Optional[str] = "gemini"

class SaveKeyRequest(BaseModel):
    api_key: str
    provider: Optional[str] = "gemini"

@router.post("/api/analyze")
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """
    Spawns the autonomous orchestrator in the background.
    """
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database Manager not initialized.")
        
    session_id = str(uuid.uuid4())
    logger.info(f"Received query request, creating session: {session_id}")
    
    # Register SSE message queue
    queue = asyncio.Queue()
    session_queues[session_id] = queue
    
    # Instantiate and trigger Master Orchestrator
    orchestrator = MasterOrchestrator(session_id, db_manager, queue)
    
    # Store dynamic UI key transiently in environment variables if supplied
    if request.api_key:
        provider_var = f"{request.provider.upper()}_API_KEY"
        os.environ[provider_var] = request.api_key
        logger.info(f"Transient API Key registered for provider: {request.provider}")
    else:
        # Check if a key is already loaded in environment (from .env or previous save)
        provider_var = f"{request.provider.upper()}_API_KEY"
        existing_key = os.environ.get(provider_var) or os.environ.get("GEMINI_API_KEY")
        if existing_key:
            logger.info(f"Using previously saved API key for provider: {request.provider}")

    # Launch non-blocking background task
    background_tasks.add_task(_run_orchestrator, orchestrator, request.query)
    
    return {
        "success": True,
        "session_id": session_id,
        "message": "Autonomous multi-agent research pipeline successfully started in background."
    }

async def _run_orchestrator(orchestrator: MasterOrchestrator, query: str):
    try:
        await orchestrator.execute_workflow(query)
    except Exception as e:
        logger.exception(f"Fatal error in background orchestration execution: {e}")
        # Put error state in queue to notify listener
        if orchestrator.stream_queue:
            await orchestrator.stream_queue.put({
                "status": "failed",
                "logs": [{"agent": "system", "message": f"Pipeline crashed: {str(e)}", "type": "error"}],
                "tasks": {}
            })

@router.get("/api/stream/{session_id}")
async def stream_session(session_id: str):
    """
    SSE stream yielding real-time JSON state events.
    """
    if session_id not in session_queues:
        raise HTTPException(status_code=404, detail="Active streaming session not found.")
        
    queue = session_queues[session_id]
    
    async def sse_generator():
        logger.info(f"SSE client connected to session: {session_id}")
        try:
            while True:
                # Retrieve from orchestrator queue
                state_data = await queue.get()
                
                # Format event stream data
                yield f"data: {json.dumps(state_data)}\n\n"
                
                # Check terminal state
                if state_data.get("status") in ["completed", "failed", "degraded"]:
                    logger.info(f"Streaming complete for session: {session_id}")
                    # Clean up
                    session_queues.pop(session_id, None)
                    break
        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected from session: {session_id}")
            session_queues.pop(session_id, None)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@router.post("/api/upload")
async def upload_rag_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form("global_corpus"),
    api_key: Optional[str] = Form(None)
):
    """
    Uploads a txt/md file and parses contents into the semantic memory database.
    """
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized.")

    if not file.filename.endswith((".txt", ".md", ".json")):
        raise HTTPException(status_code=400, detail="Only plain text files (.txt, .md, .json) are supported out-of-the-box.")
        
    try:
        content_bytes = await file.read()
        content_text = content_bytes.decode("utf-8")
        
        # Load transient Memory Manager to ingest chunks
        orchestrator = MasterOrchestrator(session_id or str(uuid.uuid4()), db_manager)
        await orchestrator.memory.ingest_document(
            text=content_text,
            document_name=file.filename,
            api_key=api_key
        )
        
        return {
            "success": True,
            "filename": file.filename,
            "message": "Document parsed and successfully indexed in Semantic Vector Store."
        }
    except Exception as e:
        logger.error(f"Error parsing document upload: {e}")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")

@router.get("/api/sessions")
async def list_sessions():
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized.")
    repo = SessionRepository(db_manager)
    sessions = await repo.list_sessions()
    return {"sessions": sessions}

@router.get("/api/report/{session_id}")
async def get_report(session_id: str):
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized.")
    repo = SessionRepository(db_manager)
    report = await repo.get_session_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Synthesized report not found for this session.")
    return report

@router.post("/api/save-key")
async def save_api_key(request: SaveKeyRequest):
    """
    Persists the API key to the .env file so users don't need to enter it again.
    Also injects it into the current process environment immediately.
    """
    if not request.api_key or len(request.api_key.strip()) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key provided.")
    
    provider = request.provider.upper() if request.provider else "GEMINI"
    env_var_name = f"{provider}_API_KEY"
    
    # Inject into live process immediately
    os.environ[env_var_name] = request.api_key.strip()
    logger.info(f"API key saved to process environment for provider: {provider}")
    
    # Persist to .env file for future server restarts
    try:
        env_path = ".env"
        if not os.path.exists(env_path):
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        
        # Read existing .env content
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
        
        # Find and update or append the key
        key_found = False
        updated_lines = []
        for line in env_lines:
            if line.strip().startswith(f"{env_var_name}=") or line.strip().startswith(f"{env_var_name}=\""):
                updated_lines.append(f"{env_var_name}=\"{request.api_key.strip()}\"\n")
                key_found = True
            else:
                updated_lines.append(line)
        
        if not key_found:
            updated_lines.append(f"{env_var_name}=\"{request.api_key.strip()}\"\n")
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        
        logger.info(f"API key successfully persisted to .env for provider: {provider}")
        return {
            "success": True,
            "provider": provider.lower(),
            "message": f"API key saved successfully. You won't need to enter it again."
        }
    except Exception as e:
        logger.error(f"Failed to persist key to .env: {e}")
        return {
            "success": True,
            "provider": provider.lower(),
            "message": "Key active for this session (file save failed, but key is loaded)."
        }

@router.get("/api/key-status")
async def get_key_status():
    """
    Returns which providers already have API keys configured (without exposing the actual keys).
    """
    providers = {
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "groq": bool(os.environ.get("GROQ_API_KEY")),
    }
    active_providers = [p for p, has_key in providers.items() if has_key]
    return {
        "providers": providers,
        "active_count": len(active_providers),
        "active_providers": active_providers,
        "mode": "live" if active_providers else "simulation"
    }
