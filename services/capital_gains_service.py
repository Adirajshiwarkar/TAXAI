"""
Capital Gains Service
Manages capital gains transactions and calculations
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from database.models import CapitalGains, User
from database.connection import get_db

class CapitalGainsService:
    """Service for managing capital gains transactions"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========================================================================
    # TRANSACTION MANAGEMENT
    # ========================================================================
    
    def add_transaction(
        self,
        user_id: str,
        asset_type: str,
        transaction_type: str,
        purchase_date: datetime,
        purchase_price: float,
        quantity: float,
        asset_name: str,
        sale_date: Optional[datetime] = None,
        sale_price: Optional[float] = None,
        notes: Optional[str] = None
    ) -> CapitalGains:
        """Add a new capital asset transaction"""
        
        # Calculate gains if sold
        holding_period_days = None
        is_long_term = None
        gain_loss = None
        tax_applicable = None
        
        if transaction_type == 'sell' or (sale_date and sale_price):
            if not sale_date:
                sale_date = datetime.utcnow()
            
            # Calculate holding period
            delta = sale_date - purchase_date
            holding_period_days = delta.days
            
            # Determine term (simplified rules)
            # Equity: > 365 days is Long Term
            # Others: > 1095 days (3 years) is Long Term
            if asset_type in ['equity', 'equity_mf']:
                is_long_term = holding_period_days > 365
            else:
                is_long_term = holding_period_days > 1095
            
            # Calculate Gain/Loss
            total_buy_cost = purchase_price * quantity
            total_sell_value = sale_price * quantity
            gain_loss = total_sell_value - total_buy_cost
            
            # Estimate Tax (Simplified)
            if gain_loss > 0:
                if asset_type in ['equity', 'equity_mf']:
                    if is_long_term:
                        # LTCG Equity: 10% (ignoring 1L exemption for individual txn)
                        tax_applicable = gain_loss * 0.10
                    else:
                        # STCG Equity: 15%
                        tax_applicable = gain_loss * 0.15
                else:
                    if is_long_term:
                        # LTCG Others: 20% (approx)
                        tax_applicable = gain_loss * 0.20
                    else:
                        # STCG Others: Slab rate (placeholder 30%)
                        tax_applicable = gain_loss * 0.30
            else:
                tax_applicable = 0
        
        transaction = CapitalGains(
            user_id=user_id,
            asset_type=asset_type,
            transaction_type=transaction_type,
            purchase_date=purchase_date,
            purchase_price=purchase_price,
            quantity=quantity,
            asset_name=asset_name,
            sale_date=sale_date,
            sale_price=sale_price,
            notes=notes,
            holding_period_days=holding_period_days,
            is_long_term=is_long_term,
            gain_loss=gain_loss,
            tax_applicable=tax_applicable
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        return transaction
    
    def get_transactions(
        self,
        user_id: str,
        asset_type: Optional[str] = None,
        year: Optional[int] = None
    ) -> List[CapitalGains]:
        """Get transactions for a user"""
        query = self.db.query(CapitalGains).filter(
            CapitalGains.user_id == user_id
        )
        
        if asset_type:
            query = query.filter(CapitalGains.asset_type == asset_type)
        
        if year:
            # Filter by sale date year if sold, else purchase date
            # This is a bit complex, let's just filter by created_at for now or simple logic
            pass
            
        return query.order_by(desc(CapitalGains.purchase_date)).all()
    
    def get_portfolio_summary(self, user_id: str) -> Dict[str, Any]:
        """Get summary of capital gains portfolio"""
        transactions = self.get_transactions(user_id)
        
        summary = {
            "total_invested": 0.0,
            "current_value": 0.0, # Only for sold items in this simple model
            "total_gain_loss": 0.0,
            "total_tax_liability": 0.0,
            "asset_allocation": {},
            "stcg_total": 0.0,
            "ltcg_total": 0.0
        }
        
        for txn in transactions:
            # Add to allocation
            summary["asset_allocation"][txn.asset_type] = summary["asset_allocation"].get(txn.asset_type, 0) + (txn.purchase_price * txn.quantity)
            
            summary["total_invested"] += (txn.purchase_price * txn.quantity)
            
            if txn.gain_loss is not None:
                summary["total_gain_loss"] += txn.gain_loss
                summary["total_tax_liability"] += (txn.tax_applicable or 0)
                
                if txn.is_long_term:
                    summary["ltcg_total"] += txn.gain_loss
                else:
                    summary["stcg_total"] += txn.gain_loss
                    
        return summary
        
    def delete_transaction(self, transaction_id: int) -> bool:
        """Delete a transaction"""
        txn = self.db.query(CapitalGains).filter(CapitalGains.id == transaction_id).first()
        if txn:
            self.db.delete(txn)
            self.db.commit()
            return True
        return False
