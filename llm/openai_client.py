# ============================================================
# 10. LLM CLIENT (OpenAI)
# ============================================================

# llm/openai_client.py
import openai
from utils.config import settings
from typing import AsyncGenerator, List, Dict, Optional

class OpenAIClient:
    """Wrapper for OpenAI API"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"
    
    async def generate(self, prompt: str, max_tokens: int = 4000) -> str:
        """Generate response from OpenAI"""
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    
    async def generate_with_history(
        self,
        message: str,
        history: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4000
    ) -> str:
        """Generate response with conversation history"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add history
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages
        )
        return response.choices[0].message.content
    
    async def generate_stream(self, user_message: str, history: list, system_prompt: str = None) -> AsyncGenerator[str, None]:
        """Stream response from OpenAI"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        
        stream = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=messages,
            stream=True
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

