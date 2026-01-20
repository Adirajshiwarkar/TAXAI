"""
Document Service
Manages document storage and metadata in PostgreSQL
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.models import Document
from database.connection import get_db

class DocumentService:
    """Service for managing user documents"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def add_document(
        self,
        user_id: str,
        file_name: str,
        file_path: str,
        document_type: str = "general",
        file_size: Optional[int] = None,
        extracted_data: Optional[Dict] = None
    ) -> Document:
        """Add a new document record"""
        
        doc = Document(
            user_id=user_id,
            file_name=file_name,
            file_path=file_path,
            document_type=document_type,
            file_size=file_size,
            extracted_data=extracted_data
        )
        
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        
        return doc
    
    def get_user_documents(self, user_id: str) -> List[Document]:
        """Get all documents for a user"""
        return self.db.query(Document).filter(
            Document.user_id == user_id
        ).order_by(desc(Document.uploaded_at)).all()
    
    def get_document(self, document_id: int) -> Optional[Document]:
        """Get document by ID"""
        return self.db.query(Document).filter(Document.id == document_id).first()
    
    def delete_document(self, document_id: int) -> bool:
        """Delete a document record"""
        doc = self.get_document(document_id)
        if doc:
            self.db.delete(doc)
            self.db.commit()
            return True
        return False
