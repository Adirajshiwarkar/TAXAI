"""
ITR Filing Service
Manages ITR filing process and stores data in PostgreSQL
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.models import ITRFiling, ITRStatus, User
from database.connection import get_db


class ITRService:
    """Service for managing ITR filings in PostgreSQL"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========================================================================
    # ITR FILING OPERATIONS
    # ========================================================================
    
    def create_itr_filing(
        self,
        user_id: str,
        assessment_year: str,
        itr_type: str
    ) -> ITRFiling:
        """Create a new ITR filing record"""
        filing = ITRFiling(
            user_id=user_id,
            assessment_year=assessment_year,
            itr_type=itr_type,
            status=ITRStatus.DRAFT
        )
        
        self.db.add(filing)
        self.db.commit()
        self.db.refresh(filing)
        
        return filing
    
    def get_itr_filing(self, filing_id: int) -> Optional[ITRFiling]:
        """Get ITR filing by ID"""
        return self.db.query(ITRFiling).filter(
            ITRFiling.id == filing_id
        ).first()
    
    def get_user_filings(
        self,
        user_id: str,
        assessment_year: Optional[str] = None
    ) -> List[ITRFiling]:
        """Get all ITR filings for a user"""
        query = self.db.query(ITRFiling).filter(
            ITRFiling.user_id == user_id
        )
        
        if assessment_year:
            query = query.filter(ITRFiling.assessment_year == assessment_year)
        
        return query.order_by(desc(ITRFiling.created_at)).all()
    
    def get_latest_filing(
        self,
        user_id: str,
        assessment_year: str
    ) -> Optional[ITRFiling]:
        """Get the latest ITR filing for a user and assessment year"""
        return self.db.query(ITRFiling).filter(
            ITRFiling.user_id == user_id,
            ITRFiling.assessment_year == assessment_year
        ).order_by(desc(ITRFiling.created_at)).first()
    
    # ========================================================================
    # UPDATE ITR STATUS
    # ========================================================================
    
    def update_session_id(self, filing_id: int, session_id: str):
        """Update session ID"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.session_id = session_id
            self.db.commit()
    
    def update_client_reference(self, filing_id: int, client_ref_id: str):
        """Update client reference ID"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.client_reference_id = client_ref_id
            self.db.commit()
    
    def update_prefill_data(self, filing_id: int, prefill_data: Dict[str, Any]):
        """Store prefill data"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.prefill_data = prefill_data
            self.db.commit()
    
    def update_itr_data(self, filing_id: int, itr_data: Dict[str, Any]):
        """Store complete ITR data"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.itr_data = itr_data
            self.db.commit()
    
    def update_validation(
        self,
        filing_id: int,
        validation_id: Optional[str] = None,
        errors: Optional[List[Dict]] = None
    ):
        """Update validation status"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            if validation_id:
                filing.validation_id = validation_id
                filing.status = ITRStatus.VALIDATED
                filing.validated_at = datetime.utcnow()
            else:
                filing.validation_errors = errors
            self.db.commit()
    
    def update_draft(self, filing_id: int, draft_id: str):
        """Update draft ID"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.draft_id = draft_id
            self.db.commit()
    
    def update_verification_mode(self, filing_id: int, mode: str):
        """Update verification mode"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.verification_mode = mode
            self.db.commit()
    
    def update_submission(self, filing_id: int, ack_number: str):
        """Update submission details"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.acknowledgement_number = ack_number
            filing.status = ITRStatus.SUBMITTED
            filing.submitted_at = datetime.utcnow()
            self.db.commit()
    
    def update_acknowledgement(self, filing_id: int):
        """Mark acknowledgement as received"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            filing.status = ITRStatus.ACKNOWLEDGED
            filing.acknowledged_at = datetime.utcnow()
            self.db.commit()
    
    # ========================================================================
    # STATUS QUERIES
    # ========================================================================
    
    def get_filing_status(self, filing_id: int) -> Optional[str]:
        """Get current status of ITR filing"""
        filing = self.get_itr_filing(filing_id)
        return filing.status.value if filing else None
    
    def get_filing_summary(self, filing_id: int) -> Optional[Dict[str, Any]]:
        """Get complete summary of ITR filing"""
        filing = self.get_itr_filing(filing_id)
        
        if not filing:
            return None
        
        return {
            "id": filing.id,
            "user_id": filing.user_id,
            "assessment_year": filing.assessment_year,
            "itr_type": filing.itr_type,
            "status": filing.status.value,
            "session_id": filing.session_id,
            "client_reference_id": filing.client_reference_id,
            "validation_id": filing.validation_id,
            "draft_id": filing.draft_id,
            "acknowledgement_number": filing.acknowledgement_number,
            "verification_mode": filing.verification_mode,
            "created_at": filing.created_at.isoformat() if filing.created_at else None,
            "validated_at": filing.validated_at.isoformat() if filing.validated_at else None,
            "submitted_at": filing.submitted_at.isoformat() if filing.submitted_at else None,
            "acknowledged_at": filing.acknowledged_at.isoformat() if filing.acknowledged_at else None,
            "has_prefill_data": filing.prefill_data is not None,
            "has_itr_data": filing.itr_data is not None,
            "has_errors": filing.validation_errors is not None
        }
    
    def get_user_filing_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about user's ITR filings"""
        filings = self.get_user_filings(user_id)
        
        stats = {
            "total_filings": len(filings),
            "by_status": {},
            "by_year": {},
            "latest_filing": None
        }
        
        for filing in filings:
            # Count by status
            status = filing.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            # Count by year
            year = filing.assessment_year
            stats["by_year"][year] = stats["by_year"].get(year, 0) + 1
        
        # Get latest filing
        if filings:
            latest = filings[0]
            stats["latest_filing"] = {
                "id": latest.id,
                "assessment_year": latest.assessment_year,
                "status": latest.status.value,
                "created_at": latest.created_at.isoformat() if latest.created_at else None
            }
        
        return stats
    
    # ========================================================================
    # DELETE OPERATIONS
    # ========================================================================
    
    def delete_filing(self, filing_id: int) -> bool:
        """Delete an ITR filing"""
        filing = self.get_itr_filing(filing_id)
        if filing:
            self.db.delete(filing)
            self.db.commit()
            return True
        return False
