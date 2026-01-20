# ============================================================
# FASTAPI MAIN APPLICATION
# ============================================================

# main.py
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

from datetime import datetime
from typing import List, Dict, Optional
import uuid
import shutil
import os
from sqlalchemy.orm import Session
import json

from database.models import User, UserStatus
from database.connection import get_db_session, init_db
from utils import models
from llm.openai_client import OpenAIClient
from agents.chat_agent_with_memory import ChatAgentWithMemory
from agents.itr_filing_agent import ITRFilingCrew
from services.memory_service import MemoryService
from services.itr_service import ITRService
from services.capital_gains_service import CapitalGainsService
from services.document_service import DocumentService
from fastapi.responses import FileResponse




@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield



app = FastAPI(title="TaxAI Backend with Memory & ITR Filing", lifespan=lifespan)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#--------------------------------------------------
# Initialize components
#-----------------------------------------------------
llm_client = OpenAIClient()
chat_agent_memory = ChatAgentWithMemory(llm_client)
itr_crew = ITRFilingCrew()

# Ensure uploads directory exists
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)




#--------------------------------------------------
# Initialize logging
#-----------------------------------------------------

# Ensure logs directory exists (auto-create if deleted)
Path('logs').mkdir(exist_ok=True)

# Setup logging - outputs to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/TaxAI.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Suppress noisy HTTP request logs from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)






#--------------------------------------------------------------------------------------------------
# USER MANAGEMENT ENDPOINTS
#--------------------------------------------------------------------------------------------------

@app.post("/api/register")
async def register_user(
    request: models.RagisterRequest,
    db: Session = Depends(get_db_session)
):
    """Register a new user in PostgreSQL"""
    try:
        # Check if user exists
        existing_user = db.query(User).filter(User.user_id == request.user_id).first()
        if existing_user:
            return {"message": "User already registered", "user_id": request.user_id}
            
        new_user = User(
            user_id=request.user_id,
            user_name=request.user_name,
            status=UserStatus.ACTIVE
        )
        db.add(new_user)
        db.commit()
        
        # Initialize memory
        memory_service = MemoryService(db)
        memory_service.create_user_memory(request.user_id)
        
        return {"message": "User registered successfully", "user_id": request.user_id}
    except Exception as e:
        db.rollback()
        logger.error(f"Ragistration failed with error: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.get("/api/get_users")
async def get_users(db: Session = Depends(get_db_session)):
    """Get all users"""
    users = db.query(User).all()
    return [
        {
            "user_id": u.user_id,
            "user_name": u.user_name,
            "status": u.status.value,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]

@app.get("/api/get_user")
async def get_user(user_id: str, db: Session = Depends(get_db_session)):
    """Get specific user"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": user.user_id,
        "user_name": user.user_name,
        "email": user.email,
        "phone": user.phone,
        "pan": user.pan,
        "status": user.status.value
    }

@app.delete("/api/delete_user")
async def delete_user(user_id: str, db: Session = Depends(get_db_session)):
    """Delete user and all associated data"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    return {"message": f"User {user_id} deleted successfully"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = "default_user",
    document_type: str = "general",
    db: Session = Depends(get_db_session)
):
    """Handle file uploads and store metadata in PostgreSQL"""
    try:
        # Save file to disk
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Store metadata in DB
        doc_service = DocumentService(db)
        doc = doc_service.add_document(
            user_id=user_id,
            file_name=file.filename,
            file_path=file_path,
            document_type=document_type,
            file_size=file_size
        )
        
        return {
            "filename": file.filename,
            "document_id": doc.id,
            "status": "uploaded",
            "message": "File uploaded and metadata stored successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/api/documents/{user_id}")
async def get_user_documents(user_id: str, db: Session = Depends(get_db_session)):
    """Get all documents for a user"""
    doc_service = DocumentService(db)
    docs = doc_service.get_user_documents(user_id)
    
    return [
        {
            "id": d.id,
            "file_name": d.file_name,
            "document_type": d.document_type,
            "file_size": d.file_size,
            "uploaded_at": d.uploaded_at.isoformat()
        }
        for d in docs
    ]


@app.delete("/api/document/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db_session)):
    """Delete a document"""
    doc_service = DocumentService(db)
    
    # Get document to find path
    doc = doc_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file from disk
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass  # Ignore if file already gone
            
    # Delete from DB
    doc_service.delete_document(document_id)
    
    return {"message": "Document deleted successfully"}

@app.post("/api/chat/stream")
async def chat_stream(request: models.ChatRequest):
    """Streaming chat endpoint with Memory (Short-term + Long-term)"""
    
    async def generate_stream():
        logger.info(f"Starting stream for user :{request.user_id}\n Session: {request.conversation_id}")
        try:
            # Generate IDs
            user_id = request.user_id or "default_user"  # Should come from auth
            conversation_id = request.conversation_id or f"conv_{datetime.now().timestamp()}"
            
            # 1. Send Status: Thinking
            yield f"data: {json.dumps({'status': 'Thinking...'})}\n\n"
            
            # Check for upload intent immediately
            if "upload" in request.message.lower() or "attach" in request.message.lower():
                 print("User wants upload - triggering widget immediately")
                 yield f"data: {json.dumps({'request_upload': True, 'upload_type': 'document'})}\n\n"
            
            # 2. Stream response using memory-aware agent
            response_chunks = []
            
            async for chunk in chat_agent_memory.chat_stream(
                user_id=user_id,
                session_id=conversation_id,
                message=request.message
            ):
                response_chunks.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            full_response = "".join(response_chunks)
            
            # 3. Check for Intent & Documents
            user_wants_upload = "upload" in request.message.lower() or "attach" in request.message.lower()
            ai_asks_upload = "upload" in full_response.lower() or "provide" in full_response.lower() or "send" in full_response.lower()
            
            if user_wants_upload or (ai_asks_upload and ("invoice" in full_response.lower() or "document" in full_response.lower())):
                print("Triggering upload widget")
                yield f"data: {json.dumps({'request_upload': True, 'upload_type': 'document'})}\n\n"

            yield f"data: {json.dumps({'done': True, 'conversation_id': conversation_id})}\n\n"
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_stream(), media_type="text/event-stream")


#--------------------------------------------------------------------------------------------------
# MEMORY ENDPOINTS
#--------------------------------------------------------------------------------------------------

@app.get("/api/memory/sessions/{user_id}")
async def get_user_sessions(user_id: str, db: Session = Depends(get_db_session)):
    """Get all conversation sessions for a user"""
    memory_service = MemoryService(db)
    sessions = memory_service.get_user_sessions(user_id)
    
    return {
        "user_id": user_id,
        "sessions": [
            {
                "session_id": s.session_id,
                "title": s.title,
                "is_active": s.is_active,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "last_activity": s.last_activity.isoformat() if s.last_activity else None,
                "message_count": len(s.messages)
            }
            for s in sessions
        ]
    }

@app.get("/api/memory/conversation/{session_id}")
async def get_conversation_history(session_id: str, db: Session = Depends(get_db_session)):
    """Get conversation history for a session"""
    memory_service = MemoryService(db)
    messages = memory_service.get_recent_messages(session_id, limit=100)
    
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "intent": msg.intent,
                "entities": msg.entities
            }
            for msg in messages
        ]
    }

@app.get("/api/memory/user/{user_id}")
async def get_user_memory(user_id: str, db: Session = Depends(get_db_session)):
    """Get user's long-term memory"""
    memory_service = MemoryService(db)
    memory = memory_service.get_user_memory(user_id)
    
    if not memory:
        return {"user_id": user_id, "message": "No memory found"}
    
    return {
        "user_id": user_id,
        "profile_summary": memory.profile_summary,
        "business_type": memory.business_type,
        "tax_regime": memory.tax_regime,
        "entities": memory.entities,
        "frequent_intents": memory.frequent_intents,
        "financial_context": {
            "has_business_income": memory.has_business_income,
            "has_capital_gains": memory.has_capital_gains,
            "has_house_property": memory.has_house_property
        },
        "last_updated": memory.updated_at.isoformat() if memory.updated_at else None
    }

@app.post("/api/memory/update/{user_id}")
async def update_user_memory(user_id: str, updates: dict, db: Session = Depends(get_db_session)):
    """Update user's long-term memory"""
    memory_service = MemoryService(db)
    memory_service.update_user_memory(user_id, updates)
    
    return {"message": "Memory updated successfully"}

@app.delete("/api/memory/session/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db_session)):
    """Delete a conversation session"""
    memory_service = MemoryService(db)
    memory_service.delete_session(session_id)
    
    return {"message": "Session deleted successfully"}

@app.post("/api/memory/session/{session_id}/end")
async def end_session(session_id: str, db: Session = Depends(get_db_session)):
    """End a conversation session"""
    memory_service = MemoryService(db)
    memory_service.end_session(session_id)
    
    return {"message": "Session ended successfully"}

@app.post("/api/memory/session/new")
async def create_new_session(
    user_id: str,
    session_id: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Create a new conversation session"""
    if not session_id:
        session_id = f"session_{user_id}_{uuid.uuid4().hex[:8]}"
    
    memory_service = MemoryService(db)
    session = memory_service.create_session(user_id, session_id)
    
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "is_active": session.is_active
    }

@app.get("/api/memory/demographics/{user_id}")
async def get_user_demographics(user_id: str, db: Session = Depends(get_db_session)):
    """Get user's demographic information"""
    memory_service = MemoryService(db)
    demographics = memory_service.get_demographics(user_id)
    
    return {
        "user_id": user_id,
        "demographics": demographics
    }

@app.post("/api/memory/demographics/{user_id}")
async def update_user_demographics(
    user_id: str,
    demographics: dict,
    db: Session = Depends(get_db_session)
):
    """Update user's demographic information"""
    memory_service = MemoryService(db)
    memory_service.update_demographics(user_id, demographics)
    
    return {"message": "Demographics updated successfully", "demographics": demographics}


#--------------------------------------------------------------------------------------------------
# ITR FILING ENDPOINTS
#--------------------------------------------------------------------------------------------------

def run_itr_filing_task(user_id: str, pan: str, assessment_year: str, itr_type: str):
    """Background task for ITR filing"""
    try:
        print(f"Starting background ITR filing for {user_id}")
        itr_crew.file_itr_automatically(
            user_id=user_id,
            pan=pan,
            assessment_year=assessment_year,
            itr_type=itr_type
        )
        print(f"Background ITR filing completed for {user_id}")
    except Exception as e:
        print(f"Background ITR filing failed for {user_id}: {str(e)}")

@app.post("/api/itr/file-automatically")
async def file_itr_automatically(
    user_id: str,
    pan: str,
    assessment_year: str,
    background_tasks: BackgroundTasks,
    itr_type: str = "ITR-1",
    db: Session = Depends(get_db_session)
):
    """
    Automatically file ITR using CrewAI agents and mock government APIs
    
    This endpoint:
    1. Creates ITR filing record in PostgreSQL
    2. Uses CrewAI to orchestrate the entire filing process (in background)
    3. Stores all data (prefill, validation, submission) in database
    4. Returns filing ID immediately
    """
    try:
        # Create ITR filing record
        itr_service = ITRService(db)
        filing = itr_service.create_itr_filing(
            user_id=user_id,
            assessment_year=assessment_year,
            itr_type=itr_type
        )
        
        # Run CrewAI in background
        background_tasks.add_task(
            run_itr_filing_task,
            user_id=user_id,
            pan=pan,
            assessment_year=assessment_year,
            itr_type=itr_type
        )
        
        return {
            "success": True,
            "filing_id": filing.id,
            "message": "ITR filing process initiated in background. You can check status using the filing ID."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ITR filing initiation failed: {str(e)}")


@app.get("/api/itr/prefill/{user_id}")
async def get_itr_prefill(
    user_id: str,
    pan: str,
    assessment_year: str,
    db: Session = Depends(get_db_session)
):
    """Get prefill data summary for a user"""
    try:
        # Get or create filing record
        itr_service = ITRService(db)
        filing = itr_service.get_latest_filing(user_id, assessment_year)
        
        if not filing:
            filing = itr_service.create_itr_filing(user_id, assessment_year, "ITR-1")
        # Get prefill summary using CrewAI
        prefill_data = itr_service.get_filing_prefill(filing.id)
        return {
            "filing_id": filing.id,
            "prefill_data": prefill_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch prefill data: {str(e)}")


@app.get("/api/itr/status/{filing_id}")
async def get_filing_status(filing_id: int, db: Session = Depends(get_db_session)):
    """Get ITR filing status from PostgreSQL"""
    itr_service = ITRService(db)
    summary = itr_service.get_filing_summary(filing_id)
    
    if not summary:
        raise HTTPException(status_code=404, detail="ITR filing not found")
    
    return summary


@app.get("/api/itr/user/{user_id}")
async def get_user_filings(
    user_id: str,
    assessment_year: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get all ITR filings for a user"""
    itr_service = ITRService(db)
    filings = itr_service.get_user_filings(user_id, assessment_year)
    
    return {
        "user_id": user_id,
        "total_filings": len(filings),
        "filings": [
            {
                "id": f.id,
                "assessment_year": f.assessment_year,
                "itr_type": f.itr_type,
                "status": f.status.value,
                "acknowledgement_number": f.acknowledgement_number,
                "submitted_at": f.submitted_at.isoformat() if f.submitted_at else None,
                "created_at": f.created_at.isoformat() if f.created_at else None
            }
            for f in filings
        ]
    }


@app.get("/api/itr/stats/{user_id}")
async def get_user_filing_stats(user_id: str, db: Session = Depends(get_db_session)):
    """Get statistics about user's ITR filings"""
    itr_service = ITRService(db)
    stats = itr_service.get_user_filing_stats(user_id)
    
    return {
        "user_id": user_id,
        "stats": stats
    }


@app.delete("/api/itr/filing/{filing_id}")
async def delete_filing(filing_id: int, db: Session = Depends(get_db_session)):
    """Delete an ITR filing record"""
    itr_service = ITRService(db)
    success = itr_service.delete_filing(filing_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="ITR filing not found")
    
    return {"message": "ITR filing deleted successfully"}


#--------------------------------------------------------------------------------------------------
# CAPITAL GAINS ENDPOINTS
#--------------------------------------------------------------------------------------------------

@app.post("/api/capital-gains/transaction")
async def add_transaction(
    request: models.TransactionRequest,
    db: Session = Depends(get_db_session)
):
    """Add a capital gains transaction"""
    cg_service = CapitalGainsService(db)
    
    try:
        txn = cg_service.add_transaction(
            user_id=request.user_id,
            asset_type=request.asset_type,
            transaction_type=request.transaction_type,
            purchase_date=request.purchase_date,
            purchase_price=request.purchase_price,
            quantity=request.quantity,
            asset_name=request.asset_name,
            sale_date=request.sale_date,
            sale_price=request.sale_price,
            notes=request.notes
        )
        
        return {
            "message": "Transaction added successfully",
            "transaction_id": txn.id,
            "gain_loss": txn.gain_loss,
            "tax_applicable": txn.tax_applicable,
            "is_long_term": txn.is_long_term
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add transaction: {str(e)}")


@app.get("/api/capital-gains/portfolio/{user_id}")
async def get_portfolio(user_id: str, db: Session = Depends(get_db_session)):
    """Get capital gains portfolio summary"""
    cg_service = CapitalGainsService(db)
    summary = cg_service.get_portfolio_summary(user_id)
    
    return summary


@app.get("/api/capital-gains/transactions/{user_id}")
async def get_transactions(
    user_id: str,
    asset_type: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get all transactions for a user"""
    cg_service = CapitalGainsService(db)
    txns = cg_service.get_transactions(user_id, asset_type)
    
    return [
        {
            "id": t.id,
            "asset_name": t.asset_name,
            "asset_type": t.asset_type,
            "type": t.transaction_type,
            "quantity": t.quantity,
            "purchase_date": t.purchase_date.isoformat(),
            "purchase_price": t.purchase_price,
            "sale_date": t.sale_date.isoformat() if t.sale_date else None,
            "sale_price": t.sale_price,
            "gain_loss": t.gain_loss,
            "tax": t.tax_applicable,
            "is_long_term": t.is_long_term
        }
        for t in txns
    ]


@app.delete("/api/capital-gains/transaction/{txn_id}")
async def delete_transaction(txn_id: int, db: Session = Depends(get_db_session)):
    """Delete a transaction"""
    cg_service = CapitalGainsService(db)
    success = cg_service.delete_transaction(txn_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {"message": "Transaction deleted successfully"}
@app.get("/")
async def frontend():
    return FileResponse("index.html")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)