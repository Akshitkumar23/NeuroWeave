import os
import uvicorn
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import systems modules
from storage.database import DatabaseManager
from observability.logger import setup_observability_logging
import api.routes as routes

# Load env variables
load_dotenv()

# Setup observability structured logs pipeline
setup_observability_logging()
logger = logging.getLogger("neuroweave.main")

# Initialize FastAPI
app = FastAPI(
    title="NeuroWeave Orchestration Platform",
    description="Production-grade Autonomous Multi-Agent Research & Strategic Synthesis Engine.",
    version="1.0.0"
)

# Enable CORS for local testing environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount system static dashboard files
ui_folder = "ui"
if not os.path.exists(ui_folder):
    os.makedirs(ui_folder, exist_ok=True)

# Register routes to database instance on startup
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing NeuroWeave systems on startup.")
    
    # Establish SQLite manager
    db_mgr = DatabaseManager()
    await db_mgr.initialize_tables()
    
    # Expose db manager to routes router
    routes.db_manager = db_mgr
    logger.info("NeuroWeave systems successfully initialized.")

@app.get("/")
async def serve_index():
    """
    Serves the main glassmorphic single-page dashboard.
    """
    index_path = os.path.join(ui_folder, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to NeuroWeave. UI Dashboard index.html is not created yet."}

# Register API Router
app.include_router(routes.router)

# Mount remaining static assets (styles, scripts)
app.mount("/", StaticFiles(directory=ui_folder), name="ui")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    logger.info(f"Starting NeuroWeave Server at http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
