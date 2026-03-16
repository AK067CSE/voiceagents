"""
web_service.py - Render Web Service wrapper for LiveKit voice agent
Provides HTTP health endpoint while running voice_agent.py in background
"""
import os
import subprocess
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Voice Agent Worker Service")

# Global subprocess reference
worker_process: Optional[subprocess.Popen] = None


@app.on_event("startup")
async def startup_event():
    """Start the voice agent worker in background when FastAPI starts"""
    global worker_process
    
    print("🚀 Starting voice agent worker in background...")
    
    # Start voice_agent.py as subprocess
    worker_process = subprocess.Popen(
        ["python", "voice_agent.py", "dev"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    
    print("✅ Voice agent worker started")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up worker process when FastAPI shuts down"""
    global worker_process
    
    if worker_process and worker_process.poll() is None:
        print("🛑 Stopping voice agent worker...")
        worker_process.terminate()
        try:
            worker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker_process.kill()
        print("✅ Worker stopped")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"status": "ok", "service": "voice-agent-worker"}


@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    global worker_process
    
    if worker_process is None:
        return {"status": "initializing"}
    
    if worker_process.poll() is not None:
        # Worker process has exited
        return {"status": "worker_stopped"}
    
    return {"status": "healthy", "worker_running": True}


if __name__ == "__main__":
    # Run FastAPI with uvicorn (Render will call this with --port $PORT)
    uvicorn.run(
        "web_service:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info"
    )
