"""
Demographics Extraction Service
Extracts user demographic information from conversation messages using LLM
"""

from typing import Dict, Any, Optional
from llm.openai_client import OpenAIClient
import json
import re


class DemographicsExtractor:
    """Extract user demographics from conversation messages"""
    
    EXTRACTION_PROMPT = """Analyze the following conversation messages and extract any demographic information about the user.

Extract ONLY the information that is explicitly mentioned or can be clearly inferred. Do not make assumptions.

Demographics to extract:
- age: User's age or age range (e.g., "35", "30-35", "mid-30s")
- gender: User's gender if mentioned (e.g., "male", "female")
- occupation: User's profession or job (e.g., "software engineer", "doctor", "freelancer", "business owner")
- location: User's city, state, or country (e.g., "Mumbai", "Delhi, India")
- marital_status: User's marital status if mentioned (e.g., "married", "single")
- education: User's education level if mentioned (e.g., "graduate", "MBA", "engineer")
- income_bracket: Approximate income if mentioned (e.g., "5-10 LPA", "middle income")
- dependents: Number or mention of dependents (e.g., "2 children", "spouse and parents")

Messages:
{messages}

Return ONLY a valid JSON object with the extracted demographics. If nothing is found, return an empty object {{}}.
Example: {{"age": "35", "occupation": "software engineer", "location": "Bangalore"}}

JSON Response:"""

    def __init__(self, llm_client: OpenAIClient):
        self.llm = llm_client
    
    async def extract_demographics(
        self,
        messages: list,
        existing_demographics: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Extract demographics from recent messages
        
        Args:
            messages: List of recent messages
            existing_demographics: Already known demographics to avoid re-extraction
            
        Returns:
            Dictionary of newly extracted demographics or None
        """
        if not messages:
            return None
        
        # Format messages for the prompt
        messages_text = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in messages
        ])
        
        # Generate extraction prompt
        prompt = self.EXTRACTION_PROMPT.format(messages=messages_text)
        
        try:
            # Call LLM to extract demographics
            response = await self.llm.generate(prompt, max_tokens=300)
            
            # Try to extract JSON from response
            demographics = self._parse_json_response(response)
            
            # Filter out empty values
            if demographics:
                demographics = {k: v for k, v in demographics.items() if v and str(v).strip()}
            
            # Only return new information
            if existing_demographics and demographics:
                new_demographics = {}
                for key, value in demographics.items():
                    if key not in existing_demographics or existing_demographics[key] != value:
                        new_demographics[key] = value
                return new_demographics if new_demographics else None
            
            return demographics if demographics else None
            
        except Exception as e:
            print(f"Demographics extraction error: {str(e)}")
            return None
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response"""
        try:
            # Try direct JSON parse
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Try to find JSON object in the text
            json_match = re.search(r'\{[^{}]*\}', response)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
            
            return None
