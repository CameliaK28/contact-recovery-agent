"""
Customer Contact Recovery Agent - FastAPI Server

Web API server that orchestrates the contact recovery workflow.
"""

import logging
import asyncio
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from agent.orchestrator import run_recovery
from agent.parser import parse_customer_text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Customer Contact Recovery Agent",
    description="AI Agent that finds alternative contact information for customers when original contacts fail.",
    version="1.0.0"
)

# Serve frontend static files
frontend_path = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


class CustomerInput(BaseModel):
    """Input model for customer information."""
    name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    other_info: str = ""


class ParseRequest(BaseModel):
    """Request model for text parsing."""
    raw_text: str


class ProgressEvent(BaseModel):
    """Progress event for SSE streaming."""
    step: int
    message: str
    data: Optional[Dict] = None


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    return FileResponse(str(frontend_path / "index.html"))


@app.post("/api/search")
async def search_contacts(customer: CustomerInput):
    """
    Main search endpoint: run the full contact recovery workflow.
    
    Accepts customer information and returns new contact details
    with source URLs, evidence, and confidence scores.
    """
    # Validate that at least some info is provided
    if not any([customer.name, customer.company, customer.email, customer.phone]):
        raise HTTPException(
            status_code=400,
            detail="请至少提供姓名、公司名称、邮箱或电话之一"
        )
    
    customer_info = {
        "name": customer.name,
        "company": customer.company,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "other_info": customer.other_info,
    }
    
    logger.info(f"Starting search for: {customer_info}")
    
    try:
        # Run the recovery process in a thread pool to avoid blocking
        result = await asyncio.to_thread(run_recovery, customer_info)
        return result
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"搜索过程出错: {str(e)}"
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Customer Contact Recovery Agent"}


@app.post("/api/parse")
async def parse_text(req: ParseRequest):
    """
    Parse free-form pasted text into structured customer fields.
    Returns: name, company, email, phone, address, confidence, warnings.
    """
    if not req.raw_text or not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="请提供需要解析的文本内容")

    try:
        result = parse_customer_text(req.raw_text)
        return result
    except Exception as e:
        logger.error(f"Parse failed: {e}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
