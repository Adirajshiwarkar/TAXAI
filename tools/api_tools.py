from crewai.tools import tool
import requests
import json

API_BASE = "http://localhost:8000/api"

@tool("Trigger Auto ITR Filing")
def trigger_auto_itr_filing(user_id: str, pan: str, assessment_year: str, itr_type: str) -> str:
    """
    Triggers the automatic ITR filing process for a user.
    Args:
        user_id: The user's ID
        pan: The user's PAN number
        assessment_year: Assessment year (e.g., '2024-25')
        itr_type: Type of ITR (e.g., 'ITR-1')
    """
    try:
        params = {
            "user_id": user_id,
            "pan": pan,
            "assessment_year": assessment_year,
            "itr_type": itr_type
        }
        response = requests.post(f"{API_BASE}/itr/file-automatically", params=params)
        response.raise_for_status()
        return f"✅ ITR Filing Initiated! Response: {response.json()}"
    except Exception as e:
        return f"❌ Failed to trigger filing: {str(e)}"

@tool("Get ITR Status")
def get_itr_status(filing_id: str) -> str:
    """Checks the status of an ITR filing."""
    try:
        response = requests.get(f"{API_BASE}/itr/status/{filing_id}")
        response.raise_for_status()
        return str(response.json())
    except Exception as e:
        return f"❌ Error fetching status: {str(e)}"

@tool("Get Portfolio")
def get_portfolio(user_id: str) -> str:
    """Gets the capital gains portfolio summary for a user."""
    try:
        response = requests.get(f"{API_BASE}/capital-gains/portfolio/{user_id}")
        response.raise_for_status()
        return str(response.json())
    except Exception as e:
        return f"❌ Error fetching portfolio: {str(e)}"

@tool("Add Transaction")
def add_transaction(user_id: str, asset_type: str, transaction_type: str, purchase_date: str, purchase_price: float, quantity: float, asset_name: str) -> str:
    """
    Adds a capital gains transaction.
    Dates must be YYYY-MM-DD.
    """
    try:
        data = {
            "user_id": user_id,
            "asset_type": asset_type,
            "transaction_type": transaction_type,
            "purchase_date": purchase_date,
            "purchase_price": purchase_price,
            "quantity": quantity,
            "asset_name": asset_name
        }
        response = requests.post(f"{API_BASE}/capital-gains/transaction", json=data)
        response.raise_for_status()
        return f"✅ Transaction added: {response.json()}"
    except Exception as e:
        return f"❌ Error adding transaction: {str(e)}"

@tool("Request Document")
def request_document(user_id: str, document_type: str, reason: str) -> str:
    """
    Requests a document from the user.
    Use this when you need the user to upload a file (e.g., Form 16, PAN Card).
    Returns a special signal that the UI will interpret to show the upload box.
    """
    # This returns a structured string that the ChatAgent or UI can parse
    return f"UI_ACTION:REQUEST_UPLOAD:{document_type}:{reason}"

@tool("Delete Transaction")
def delete_transaction(txn_id: str) -> str:
    """Deletes a capital gains transaction."""
    try:
        response = requests.delete(f"{API_BASE}/capital-gains/transaction/{txn_id}")
        response.raise_for_status()
        return "✅ Transaction deleted."
    except Exception as e:
        return f"❌ Error deleting transaction: {str(e)}"

@tool("Delete Filing")
def delete_filing(filing_id: str) -> str:
    """Deletes an ITR filing."""
    try:
        response = requests.delete(f"{API_BASE}/itr/filing/{filing_id}")
        response.raise_for_status()
        return "✅ Filing deleted."
    except Exception as e:
        return f"❌ Error deleting filing: {str(e)}"
