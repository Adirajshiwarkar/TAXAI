from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import secrets
import json
import base64
from enum import Enum

app = FastAPI(
    title="ERI Type-2 Mock ITR API",
    description="Mock Government ITR APIs for testing ERI Type-2 integrations",
    version="1.0.0"
)

# ============================================================================
# MODELS
# ============================================================================

class AuthRequest(BaseModel):
    clientId: str
    clientSecret: str
    eriUserId: str
    eriPassword: str

class AuthResponse(BaseModel):
    status: str
    sessionId: str
    expiresIn: int

class AddClientRequest(BaseModel):
    pan: str
    assessmentYear: str

class AddClientResponse(BaseModel):
    status: str
    clientReferenceId: str

class PrefillRequest(BaseModel):
    pan: str
    assessmentYear: str

class ValidationRequest(BaseModel):
    pan: str
    assessmentYear: str
    itrType: str
    itrData: Dict[str, Any]

class ValidationError(BaseModel):
    code: str
    message: str

class ValidationResponse(BaseModel):
    isValid: bool
    validationId: Optional[str] = None
    errors: Optional[List[ValidationError]] = None

class SaveDraftRequest(BaseModel):
    validationId: str

class SaveDraftResponse(BaseModel):
    status: str
    draftId: str

class VerificationMode(str, Enum):
    DSC = "DSC"
    EVERIFY_LATER = "eVerify Later"
    ITRV = "ITR-V"

class VerificationModeRequest(BaseModel):
    draftId: str
    verificationMode: VerificationMode

class VerificationModeResponse(BaseModel):
    status: str

class SubmitITRRequest(BaseModel):
    draftId: str
    signedItrData: str

class SubmitITRResponse(BaseModel):
    status: str
    acknowledgementNumber: str
    submissionDate: str

class AcknowledgementRequest(BaseModel):
    acknowledgementNumber: str

class AcknowledgementResponse(BaseModel):
    status: str
    pdfUrl: str
    itrVAvailable: bool

class RequestWrapper(BaseModel):
    data: str
    signature: str

# ============================================================================
# IN-MEMORY STORAGE (simulates session/database)
# ============================================================================

sessions = {}
clients = {}
validations = {}
drafts = {}
submissions = {}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def verify_signature(signature: str) -> bool:
    """Mock signature verification - in real API, this validates DSC"""
    return len(signature) > 20

def decode_wrapper(wrapper: RequestWrapper) -> dict:
    """Decode and verify wrapped request"""
    if not verify_signature(wrapper.signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        decoded = base64.b64decode(wrapper.data).decode('utf-8')
        return json.loads(decoded)
    except:
        raise HTTPException(status_code=400, detail="Invalid request format")

def verify_session(session_id: Optional[str]) -> bool:
    """Verify session is valid"""
    if not session_id or session_id not in sessions:
        return False
    
    session = sessions[session_id]
    if datetime.fromisoformat(session['expires']) < datetime.now():
        del sessions[session_id]
        return False
    
    return True

def generate_realistic_prefill(pan: str, ay: str) -> dict:
    """Generate realistic prefill data"""
    return {
        "personalInfo": {
            "pan": pan,
            "name": "RAJESH KUMAR SHARMA",
            "dob": "1985-04-15",
            "aadhaar": "XXXX-XXXX-5678",
            "email": "rajesh.sharma@email.com",
            "mobile": "+91-98765XXXXX",
            "address": {
                "flatNo": "A-204",
                "buildingName": "Sunshine Apartments",
                "street": "MG Road",
                "city": "MUMBAI",
                "state": "MAHARASHTRA",
                "pincode": "400001"
            }
        },
        "salary": {
            "employers": [
                {
                    "employerName": "TECH SOLUTIONS PVT LTD",
                    "tan": "MUMB12345D",
                    "grossSalary": 1500000,
                    "exemptions": 50000,
                    "professionalTax": 2500,
                    "standardDeduction": 50000
                }
            ],
            "totalGrossSalary": 1500000,
            "totalExemptions": 50000,
            "netSalary": 1397500
        },
        "interestIncome": {
            "savingsAccountInterest": 15000,
            "fdInterest": 45000,
            "totalInterest": 60000
        },
        "tds": {
            "salary": [
                {
                    "employerTan": "MUMB12345D",
                    "amountPaid": 1500000,
                    "tdsDeducted": 125000,
                    "quarter": "Q4"
                }
            ],
            "others": [
                {
                    "deductorTan": "DELB67890C",
                    "nature": "Interest on Securities",
                    "amountPaid": 45000,
                    "tdsDeducted": 4500
                }
            ],
            "totalTDS": 129500
        },
        "advanceTax": {
            "payments": [
                {
                    "bsrCode": "0123456",
                    "challanDate": "2024-09-15",
                    "amount": 25000
                }
            ],
            "totalAdvanceTax": 25000
        },
        "ais": {
            "salaryInformation": True,
            "interestInformation": True,
            "dividendInformation": False,
            "lastUpdated": "2024-06-30"
        },
        "tis": {
            "taxPayments": True,
            "refunds": False,
            "lastUpdated": "2024-06-30"
        },
        "section80C": {
            "ppf": 100000,
            "elss": 50000,
            "lifeInsurance": 25000,
            "total": 175000
        },
        "section80D": {
            "selfHealthInsurance": 25000,
            "parentsHealthInsurance": 50000,
            "total": 75000
        },
        "houseProperty": {
            "selfOccupied": True,
            "address": "A-204, Sunshine Apartments, MG Road, Mumbai",
            "loanInterest": 200000,
            "lenderPan": "HDFC0001234"
        }
    }

def validate_itr_data(itr_type: str, itr_data: dict) -> tuple[bool, list]:
    """Mock validation logic"""
    errors = []
    
    # Basic validation rules
    if not itr_data.get("personalInfo"):
        errors.append({
            "code": "ERR_ITR_001",
            "message": "Personal information is mandatory"
        })
    
    if itr_type in ["ITR-3", "ITR-4"]:
        if not itr_data.get("businessIncome"):
            errors.append({
                "code": "ERR_ITR_045",
                "message": "Business income details required for ITR-3/4"
            })
    
    # Tax computation validation
    if itr_data.get("taxComputation"):
        total_income = itr_data["taxComputation"].get("totalIncome", 0)
        if total_income < 0:
            errors.append({
                "code": "ERR_ITR_078",
                "message": "Total income cannot be negative"
            })
    
    return len(errors) == 0, errors

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.post("/api/v1/auth/login", response_model=AuthResponse)
async def login(request: RequestWrapper):
    """
    1. Authentication API (Login)
    Create a session for ERI Type-2 software
    """
    try:
        data = decode_wrapper(request)
        auth_data = AuthRequest(**data)
        
        # Mock authentication
        if auth_data.clientId != "ERI_TEST_CLIENT":
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        session_id = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(days=1)
        
        sessions[session_id] = {
            "clientId": auth_data.clientId,
            "eriUserId": auth_data.eriUserId,
            "expires": expires.isoformat()
        }
        
        return AuthResponse(
            status="SUCCESS",
            sessionId=session_id,
            expiresIn=86400
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/client/add", response_model=AddClientResponse)
async def add_client(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    2. Add Client API (PAN Mapping)
    Authorize ERI to act on behalf of a taxpayer PAN
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        client_data = AddClientRequest(**data)
        
        # Validate PAN format
        if len(client_data.pan) != 10:
            raise HTTPException(status_code=400, detail="Invalid PAN format")
        
        client_ref_id = f"CLT_{secrets.token_hex(8)}"
        clients[client_data.pan] = {
            "referenceId": client_ref_id,
            "assessmentYear": client_data.assessmentYear,
            "addedAt": datetime.now().isoformat()
        }
        
        return AddClientResponse(
            status="SUCCESS",
            clientReferenceId=client_ref_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/prefill/get")
async def get_prefill(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    3. Get Prefill API
    Fetch government-available data for return preparation
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        prefill_req = PrefillRequest(**data)
        
        # Check if client is added
        if prefill_req.pan not in clients:
            raise HTTPException(status_code=400, detail="Client not added. Call add_client first")
        
        prefill_data = generate_realistic_prefill(prefill_req.pan, prefill_req.assessmentYear)
        
        return JSONResponse(content=prefill_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/itr/validate", response_model=ValidationResponse)
async def validate_itr(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    4. ITR Validation API
    Final validation before submission
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        validation_req = ValidationRequest(**data)
        
        is_valid, errors = validate_itr_data(validation_req.itrType, validation_req.itrData)
        
        if is_valid:
            validation_id = f"VAL_{secrets.token_hex(16)}"
            validations[validation_id] = {
                "pan": validation_req.pan,
                "assessmentYear": validation_req.assessmentYear,
                "itrType": validation_req.itrType,
                "itrData": validation_req.itrData,
                "validatedAt": datetime.now().isoformat()
            }
            
            return ValidationResponse(
                isValid=True,
                validationId=validation_id
            )
        else:
            return ValidationResponse(
                isValid=False,
                errors=[ValidationError(**err) for err in errors]
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/itr/save-draft", response_model=SaveDraftResponse)
async def save_draft(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    5. Save Validated Return API
    Save validated return as a draft in ITD system
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        save_req = SaveDraftRequest(**data)
        
        if save_req.validationId not in validations:
            raise HTTPException(status_code=400, detail="Invalid validation ID")
        
        draft_id = f"DRF_{secrets.token_hex(16)}"
        drafts[draft_id] = {
            "validationId": save_req.validationId,
            "validationData": validations[save_req.validationId],
            "savedAt": datetime.now().isoformat()
        }
        
        return SaveDraftResponse(
            status="SAVED",
            draftId=draft_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/verification/set-mode", response_model=VerificationModeResponse)
async def set_verification_mode(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    6. e-Verification Mode Selection API
    Declare how verification will happen
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        verify_req = VerificationModeRequest(**data)
        
        if verify_req.draftId not in drafts:
            raise HTTPException(status_code=400, detail="Invalid draft ID")
        
        # Update draft with verification mode
        drafts[verify_req.draftId]["verificationMode"] = verify_req.verificationMode
        
        return VerificationModeResponse(
            status="VERIFICATION_MODE_SET"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/itr/submit", response_model=SubmitITRResponse)
async def submit_itr(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    7. Submit ITR API
    Final submission to CPC
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        submit_req = SubmitITRRequest(**data)
        
        if submit_req.draftId not in drafts:
            raise HTTPException(status_code=400, detail="Invalid draft ID")
        
        draft = drafts[submit_req.draftId]
        
        if "verificationMode" not in draft:
            raise HTTPException(status_code=400, detail="Verification mode not set")
        
        # Generate acknowledgement number (14 digits)
        ack_number = f"{datetime.now().year}{secrets.randbelow(10**10):010d}"
        submission_date = datetime.now().isoformat()
        
        submissions[ack_number] = {
            "draftId": submit_req.draftId,
            "draft": draft,
            "submittedAt": submission_date,
            "status": "SUBMITTED"
        }
        
        return SubmitITRResponse(
            status="SUBMITTED",
            acknowledgementNumber=ack_number,
            submissionDate=submission_date
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/acknowledgement/get", response_model=AcknowledgementResponse)
async def get_acknowledgement(
    request: RequestWrapper,
    authorization: Optional[str] = Header(None)
):
    """
    8. Get Acknowledgement API
    Fetch acknowledgement details / receipt
    """
    if not verify_session(authorization):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        data = decode_wrapper(request)
        ack_req = AcknowledgementRequest(**data)
        
        if ack_req.acknowledgementNumber not in submissions:
            raise HTTPException(status_code=404, detail="Acknowledgement not found")
        
        return AcknowledgementResponse(
            status="SUCCESS",
            pdfUrl=f"https://eportal.incometax.gov.in/iec/foservices/{ack_req.acknowledgementNumber}/download",
            itrVAvailable=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """
    9. Logout API
    Terminate ERI session
    """
    if authorization and authorization in sessions:
        del sessions[authorization]
    
    return {"status": "LOGGED_OUT"}

# ============================================================================
# UTILITY ENDPOINTS (for testing)
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "ERI Type-2 Mock ITR API Server",
        "version": "1.0.0",
        "endpoints": [
            "POST /api/v1/auth/login",
            "POST /api/v1/client/add",
            "POST /api/v1/prefill/get",
            "POST /api/v1/itr/validate",
            "POST /api/v1/itr/save-draft",
            "POST /api/v1/verification/set-mode",
            "POST /api/v1/itr/submit",
            "POST /api/v1/acknowledgement/get",
            "POST /api/v1/auth/logout"
        ],
        "testCredentials": {
            "clientId": "ERI_TEST_CLIENT",
            "clientSecret": "test_secret_123",
            "eriUserId": "test_user",
            "eriPassword": "test_pass"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "activeSessions": len(sessions),
        "totalClients": len(clients),
        "totalSubmissions": len(submissions)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)