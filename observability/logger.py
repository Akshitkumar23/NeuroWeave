import json
import logging
import os
import sys
import time
from datetime import datetime

class JsonFormatter(logging.Formatter):
    """
    Custom formatter writing log elements as distinct JSON key-value records.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno
        }
        
        # Include custom attributes if present
        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id
        if hasattr(record, "agent"):
            log_data["agent"] = record.agent
            
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)

def setup_observability_logging(log_file: str = "storage/neuroweave.log"):
    # Ensure logs folder exists
    folder = os.path.dirname(log_file)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
        
    root_logger = logging.getLogger()
    # Avoid duplicate setups
    if root_logger.hasHandlers():
        return
        
    root_logger.setLevel(logging.INFO)
    
    # Formatter
    json_formatter = JsonFormatter()
    
    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)
    
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    
    logging.info("Observability JSON Logging pipeline successfully configured.")
