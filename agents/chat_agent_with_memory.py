# ============================================================
# ENHANCED CHAT AGENT WITH MEMORY
# ============================================================

# agents/chat_agent_with_memory.py
import json
import asyncio
from typing import Dict, Any, Optional
from database.connection import get_db
from services.memory_service import MemoryService
from services.demographics_service import DemographicsExtractor
from database.models import MessageRole
from llm.openai_client import OpenAIClient


from tools.api_tools import (
    trigger_auto_itr_filing,
    get_itr_status,
    get_portfolio,
    add_transaction,
    request_document,
    delete_transaction,
    delete_filing
)
import re

import logging
logger = logging.getLogger(__name__)


class ChatAgentWithMemory:
    """
    Enhanced Chat Agent with Short-term and Long-term Memory
    """
    
    SYSTEM_PROMPT_TEMPLATE = """You are TaxAI, an intelligent CA assistant with memory capabilities.

{context_summary}

AVAILABLE TOOLS:
1. Trigger Auto ITR Filing: Use when user wants to file ITR.
   Format: ACTION: {{"tool": "trigger_auto_itr_filing", "args": {{"user_id": "...", "pan": "...", "assessment_year": "...", "itr_type": "..."}}}}
2. Get Portfolio: Use when user asks for capital gains summary.
   Format: ACTION: {{"tool": "get_portfolio", "args": {{"user_id": "..."}}}}
3. Add Transaction: Use when user wants to add a buy/sell transaction.
   Format: ACTION: {{"tool": "add_transaction", "args": {{"user_id": "...", "asset_type": "...", "transaction_type": "...", "purchase_date": "...", "purchase_price": ..., "quantity": ..., "asset_name": "..."}}}}
4. Request Document: Use when you need a document.
   Format: ACTION: {{"tool": "request_document", "args": {{"user_id": "...", "document_type": "...", "reason": "..."}}}}
5. Delete Transaction: Use when user wants to delete a transaction.
   Format: ACTION: {{"tool": "delete_transaction", "args": {{"txn_id": "..."}}}}
6. Delete Filing: Use when user wants to delete a filing.
   Format: ACTION: {{"tool": "delete_filing", "args": {{"filing_id": "..."}}}}

RULES:
1. Use the user's profile and past context.
2. If user wants to perform a task supported by tools, use the ACTION format.
3. Only use one ACTION per message.
4. If you use an ACTION, keep the preceding text brief.
5. Example: "I will initiate the filing now. ACTION: {{"tool": "trigger_auto_itr_filing", "args": {{...}}}}"

Keep responses concise and professional."""

    def __init__(self, llm_client: OpenAIClient):
        self.llm = llm_client
        self.demographics_extractor = DemographicsExtractor(llm_client)

    
    async def chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
        detect_entities: bool = True
    ) -> Dict[str, Any]:
        """
        Process user message with memory-aware context
        
        Args:
            user_id: User identifier
            session_id: Conversation session ID
            message: User's message
            detect_entities: Whether to extract and store entities
            
        Returns:
            Response with intent, entities, and bot reply
        """
        with get_db() as db:
            memory_service = MemoryService(db)
            
            # Ensure session exists
            session = memory_service.get_or_create_session(user_id, session_id)
            
            # Store user message
            memory_service.add_message(
                session_id=session_id,
                role=MessageRole.USER,
                content=message
            )
            
            # Get full context (short + long term memory)
            context = memory_service.get_full_context(user_id, session_id)
            context_summary = memory_service.get_context_summary(user_id, session_id)
            
            # Prepare system prompt with context
            system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
                context_summary=context_summary
            )
            
            # Get conversation history
            history = context["conversation_history"]
            
            # Generate response
            response_text = await self.llm.generate_with_history(
                message=message,
                history=history[:-1],  # Exclude the message we just added
                system_prompt=system_prompt
            )
            
            # Detect intent
            intent = await self.detect_intent(message)
            
            # Extract entities if needed
            entities = None
            if detect_entities:
                entities = await self.extract_entities(message, context["entities"])
                
                # Store entities in long-term memory
                if entities:
                    for key, value in entities.items():
                        memory_service.add_entity(user_id, key, value)
            
            # Store assistant response
            memory_service.add_message(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=response_text,
                intent=intent,
                entities=entities
            )
            
            # Track intent in long-term memory
            if intent:
                memory_service.track_intent(user_id, intent)
            
            return {
                "response": response_text,
                "intent": intent,
                "entities": entities,
                "context": context,
                "requires_action": intent not in ["chat", "general_query"]
            }
    
    async def chat_stream(
        self,
        user_id: str,
        session_id: str,
        message: str
    ):
        """
        Stream response with memory context
        """
        with get_db() as db:
            memory_service = MemoryService(db)
            
            # Ensure session exists
            session = memory_service.get_or_create_session(user_id, session_id)
            
            # Store user message
            memory_service.add_message(
                session_id=session_id,
                role=MessageRole.USER,
                content=message
            )
            
            # Get context
            context = memory_service.get_full_context(user_id, session_id)
            context_summary = memory_service.get_context_summary(user_id, session_id)
            
            # Prepare system prompt
            system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
                context_summary=context_summary
            )
            
            # Get history
            history = context["conversation_history"]
            
            # Stream response
            full_response = ""
            async for chunk in self.llm.generate_stream(
                user_message=message,
                history=history[:-1],
                system_prompt=system_prompt
            ):
                full_response += chunk
                yield chunk
            
            # Check for ACTION
            action_match = re.search(r'ACTION:\s*(\{.*\})', full_response, re.DOTALL)
            if action_match:
                try:
                    json_str = action_match.group(1)
                    # Clean up JSON string if needed (sometimes LLM adds extra text)
                    # Find the last closing brace
                    last_brace = json_str.rfind('}')
                    if last_brace != -1:
                        json_str = json_str[:last_brace+1]
                    
                    action_data = json.loads(json_str)
                    tool_name = action_data.get("tool")
                    args = action_data.get("args", {})
                    
                    # Execute tool
                    result = await self.execute_tool(tool_name, args)
                    
                    # Yield result
                    output = f"\n\n**System Action**: Executing `{tool_name}`...\n\n> {result}"
                    yield output
                    full_response += output
                    
                except Exception as e:
                    error_msg = f"\n\n[System Error]: Failed to execute action. {str(e)}"
                    yield error_msg
                    full_response += error_msg
            
            # After streaming complete, store assistant response
            intent = await self.detect_intent(message)
            entities = await self.extract_entities(message, context["entities"])
            
            memory_service.add_message(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=full_response,
                intent=intent,
                entities=entities
            )
            
            if intent:
                memory_service.track_intent(user_id, intent)
            
            if entities:
                for key, value in entities.items():
                    memory_service.add_entity(user_id, key, value)
            
            # Extract demographics from recent conversation (every 5 messages)
            message_count = len(context["conversation_history"])
            if message_count % 5 == 0:  # Extract every 5 messages
                recent_messages = context["conversation_history"][-10:]  # Last 10 messages
                existing_demographics = context.get("demographics", {})
                
                try:
                    new_demographics = await self.demographics_extractor.extract_demographics(
                        recent_messages,
                        existing_demographics
                    )
                    
                    if new_demographics:
                        memory_service.update_demographics(user_id, new_demographics)
                        logger.info(f"Extracted demographics for {user_id}: {new_demographics}")
                except Exception as e:
                    logger.error(f"Demographics extraction failed: {str(e)}")


    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool by name (async wrapper)"""
        tool_map = {
            "trigger_auto_itr_filing": trigger_auto_itr_filing,
            "get_itr_status": get_itr_status,
            "get_portfolio": get_portfolio,
            "add_transaction": add_transaction,
            "request_document": request_document,
            "delete_transaction": delete_transaction,
            "delete_filing": delete_filing
        }
        
        if tool_name not in tool_map:
            return f"Error: Unknown tool {tool_name}"
        
        tool_obj = tool_map[tool_name]
        
        try:
            # Define helper for sync execution
            def run_sync():
                if hasattr(tool_obj, "run"):
                    return tool_obj.run(**args)
                else:
                    return tool_obj(**args)
            
            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, run_sync)
            
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    
    async def detect_intent(self, message: str) -> str:
        """Detect user intent from message"""
        message_lower = message.lower()
        
        # Intent mapping
        if any(keyword in message_lower for keyword in ["file gst", "gstr", "gst return"]):
            return "file_gst"
        elif any(keyword in message_lower for keyword in ["file itr", "income tax", "return filing"]):
            return "file_itr"
        elif any(keyword in message_lower for keyword in ["invoice", "bill"]):
            return "process_invoice"
        elif any(keyword in message_lower for keyword in ["bookkeeping", "entries", "ledger"]):
            return "bookkeeping"
        elif any(keyword in message_lower for keyword in ["capital gain", "investment", "stock"]):
            return "capital_gains"
        elif any(keyword in message_lower for keyword in ["tax planning", "tax saving", "deduction"]):
            return "tax_planning"
        
        return "chat"
    
    async def extract_entities(
        self,
        message: str,
        existing_entities: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Extract important entities from message
        Uses LLM for better extraction
        """
        # Simple regex-based extraction (can be enhanced with LLM)
        import re
        
        entities = {}
        
        # PAN pattern
        pan_match = re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', message.upper())
        if pan_match:
            entities["pan"] = pan_match.group()
        
        # GSTIN pattern
        gstin_match = re.search(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b', message.upper())
        if gstin_match:
            entities["gstin"] = gstin_match.group()
        
        # Phone number
        phone_match = re.search(r'\b(\+91[\s-]?)?[6-9]\d{9}\b', message)
        if phone_match:
            entities["phone"] = phone_match.group()
        
        # Email
        email_match = re.search(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', message.lower())
        if email_match:
            entities["email"] = email_match.group()
        
        # Amount (₹ or Rs)
        amount_match = re.search(r'(?:₹|Rs\.?|INR)\s*(\d+(?:,\d+)*(?:\.\d+)?)', message)
        if amount_match:
            entities["mentioned_amount"] = amount_match.group(1)
        
        return entities if entities else None
    
    async def update_user_profile(self, user_id: str):
        """
        Periodically update user profile summary using LLM
        Call this after every N conversations
        """
        with get_db() as db:
            memory_service = MemoryService(db)
            
            # Get recent sessions
            sessions = memory_service.get_user_sessions(user_id, active_only=False)
            
            # Collect session summaries
            summaries = [s.session_summary for s in sessions[:10] if s.session_summary]
            
            if not summaries:
                return
            
            # Generate profile summary using LLM
            prompt = f"""Analyze these conversation summaries and create a concise user profile:

{chr(10).join(summaries)}

Profile should include:
- User's role/profession
- Business type (if applicable)
- Key needs and frequent tasks
- Communication preferences

Keep it under 100 words."""
            
            profile_summary = await self.llm.generate(prompt)
            
            # Update long-term memory
            memory_service.update_profile_summary(user_id, profile_summary)
