"""
ITR Filing Tools for CrewAI
Wraps the mock ITR filing APIs from itr.py
"""

from crewai.tools import tool
import requests
import json
import base64
import secrets
from typing import Dict, Any, Optional


# ITR API Base URL (running on port 8002)
ITR_API_BASE = "http://localhost:8002"


def create_request_wrapper(data: dict) -> dict:
    """Create encoded and signed request wrapper for ITR APIs"""
    # Encode data
    data_json = json.dumps(data)
    encoded_data = base64.b64encode(data_json.encode()).decode()
    
    # Create signature (mock - just a random string for now)
    signature = secrets.token_urlsafe(32)
    
    return {
        "data": encoded_data,
        "signature": signature
    }


@tool("ITR Login Tool")
def itr_login_tool(client_id: str = "ERI_TEST_CLIENT", client_secret: str = "test_secret_123") -> str:
    """
    Authenticate with ITR system and get session ID.
    
    Args:
        client_id: ERI client ID (default: ERI_TEST_CLIENT)
        client_secret: ERI client secret (default: test_secret_123)
    
    Returns:
        Session ID for subsequent API calls
    """
    try:
        auth_data = {
            "clientId": client_id,
            "clientSecret": client_secret,
            "eriUserId": "test_user",
            "eriPassword": "test_pass"
        }
        
        wrapper = create_request_wrapper(auth_data)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/auth/login",
            json=wrapper,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        result = response.json()
        return f"✅ Login successful! Session ID: {result['sessionId']}"
    except Exception as e:
        return f"❌ Login failed: {str(e)}"


@tool("Add ITR Client Tool")
def add_client_tool(session_id: str, pan: str, assessment_year: str) -> str:
    """
    Add a client (PAN) to the ITR system.
    
    Args:
        session_id: Session ID from login
        pan: Client's PAN (10 characters)
        assessment_year: Assessment year (e.g., "2024-25")
    
    Returns:
        Client reference ID
    """
    try:
        client_data = {
            "pan": pan,
            "assessmentYear": assessment_year
        }
        
        wrapper = create_request_wrapper(client_data)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/client/add",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        return f"✅ Client added! Reference ID: {result['clientReferenceId']}"
    except Exception as e:
        return f"❌ Failed to add client: {str(e)}"


@tool("Get ITR Prefill Data Tool")
def get_prefill_data_tool(session_id: str, pan: str, assessment_year: str) -> str:
    """
    Fetch pre-filled data from government systems (AIS, TIS, Form 26AS).
    
    Args:
        session_id: Session ID from login
        pan: Client's PAN
        assessment_year: Assessment year
    
    Returns:
        Pre-filled ITR data (salary, interest, TDS, etc.)
    """
    try:
        prefill_request = {
            "pan": pan,
            "assessmentYear": assessment_year
        }
        
        wrapper = create_request_wrapper(prefill_request)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/prefill/get",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Format the response nicely
        summary = f"""
✅ Prefill data retrieved successfully!

📋 Personal Info:
- Name: {result.get('personalInfo', {}).get('name', 'N/A')}
- PAN: {result.get('personalInfo', {}).get('pan', 'N/A')}
- Email: {result.get('personalInfo', {}).get('email', 'N/A')}

💰 Income Summary:
- Gross Salary: ₹{result.get('salary', {}).get('totalGrossSalary', 0):,}
- Net Salary: ₹{result.get('salary', {}).get('netSalary', 0):,}
- Interest Income: ₹{result.get('interestIncome', {}).get('totalInterest', 0):,}

💳 Tax Deductions:
- TDS on Salary: ₹{result.get('tds', {}).get('totalTDS', 0):,}
- Section 80C: ₹{result.get('section80C', {}).get('total', 0):,}
- Section 80D: ₹{result.get('section80D', {}).get('total', 0):,}
"""
        return summary
    except Exception as e:
        return f"❌ Failed to fetch prefill data: {str(e)}"


@tool("Validate ITR Tool")
def validate_itr_tool(session_id: str, pan: str, assessment_year: str, itr_type: str, itr_data: dict) -> str:
    """
    Validate ITR data before submission.
    
    Args:
        session_id: Session ID
        pan: Client's PAN
        assessment_year: Assessment year
        itr_type: ITR form type (ITR-1, ITR-2, etc.)
        itr_data: Complete ITR data
    
    Returns:
        Validation ID if valid, or list of errors
    """
    try:
        validation_request = {
            "pan": pan,
            "assessmentYear": assessment_year,
            "itrType": itr_type,
            "itrData": itr_data
        }
        
        wrapper = create_request_wrapper(validation_request)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/itr/validate",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('isValid'):
            return f"✅ ITR validation successful! Validation ID: {result['validationId']}"
        else:
            errors = result.get('errors', [])
            error_list = "\n".join([f"- {err['message']}" for err in errors])
            return f"❌ ITR validation failed:\n{error_list}"
    except Exception as e:
        return f"❌ Validation error: {str(e)}"


@tool("Save ITR Draft Tool")
def save_draft_tool(session_id: str, validation_id: str) -> str:
    """
    Save validated ITR as draft in the ITD system.
    
    Args:
        session_id: Session ID
        validation_id: Validation ID from validate_itr_tool
    
    Returns:
        Draft ID
    """
    try:
        draft_request = {
            "validationId": validation_id
        }
        
        wrapper = create_request_wrapper(draft_request)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/itr/save-draft",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        return f"✅ Draft saved! Draft ID: {result['draftId']}"
    except Exception as e:
        return f"❌ Failed to save draft: {str(e)}"


@tool("Set Verification Mode Tool")
def set_verification_mode_tool(session_id: str, draft_id: str, mode: str = "eVerify Later") -> str:
    """
    Set e-verification mode for ITR.
    
    Args:
        session_id: Session ID
        draft_id: Draft ID
        mode: Verification mode (DSC, eVerify Later, ITR-V)
    
    Returns:
        Confirmation message
    """
    try:
        verify_request = {
            "draftId": draft_id,
            "verificationMode": mode
        }
        
        wrapper = create_request_wrapper(verify_request)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/verification/set-mode",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        return f"✅ Verification mode set to: {mode}"
    except Exception as e:
        return f"❌ Failed to set verification mode: {str(e)}"


@tool("Submit ITR Tool")
def submit_itr_tool(session_id: str, draft_id: str) -> str:
    """
    Final submission of ITR to CPC.
    
    Args:
        session_id: Session ID
        draft_id: Draft ID
    
    Returns:
        Acknowledgement number
    """
    try:
        submit_request = {
            "draftId": draft_id,
            "signedItrData": "mock_signature_data"
        }
        
        wrapper = create_request_wrapper(submit_request)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/itr/submit",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        return f"""
🎉 ITR SUBMITTED SUCCESSFULLY!

📋 Acknowledgement Number: {result['acknowledgementNumber']}
📅 Submission Date: {result['submissionDate']}

Next Steps:
1. Download acknowledgement receipt
2. Complete e-verification (if selected)
3. Check refund status after processing
"""
    except Exception as e:
        return f"❌ ITR submission failed: {str(e)}"


@tool("Get Acknowledgement Tool")
def get_acknowledgement_tool(session_id: str, ack_number: str) -> str:
    """
    Get ITR acknowledgement receipt.
    
    Args:
        session_id: Session ID
        ack_number: Acknowledgement number
    
    Returns:
        Acknowledgement details and PDF URL
    """
    try:
        ack_request = {
            "acknowledgementNumber": ack_number
        }
        
        wrapper = create_request_wrapper(ack_request)
        
        response = requests.post(
            f"{ITR_API_BASE}/api/v1/acknowledgement/get",
            json=wrapper,
            headers={
                "Content-Type": "application/json",
                "Authorization": session_id
            }
        )
        response.raise_for_status()
        
        result = response.json()
        return f"""
✅ Acknowledgement Retrieved!

PDF URL: {result['pdfUrl']}
ITR-V Available: {'Yes' if result['itrVAvailable'] else 'No'}
"""
    except Exception as e:
        return f"❌ Failed to get acknowledgement: {str(e)}"
