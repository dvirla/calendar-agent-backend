import re
from typing import Optional, Dict, Any

class VerificationService:
    """Service for handling user verification processes"""
    def __init__(self):
        pass
    
    def validate_user_input(self, message: str, user_id: int) -> Dict:
        hebrew_check_result = self.validate_message_not_hebrew(message)
        print(f"hebrew_check_result: {hebrew_check_result}")
        if not hebrew_check_result["valid"]:
            print(f"Validation failed: {hebrew_check_result['error']}")
        #TODO: Add here more validations
        return hebrew_check_result
        
    def validate_message_not_hebrew(self, message: str) -> Dict[str, Any]:
        """Validate that a message does not contain Hebrew characters"""
        print("Validating message for Hebrew characters...")
        hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
        
        if hebrew_pattern.search(message):
            return {
                "valid": False,
                "error": "Message contains Hebrew characters which are not allowed",
                "error_code": "HEBREW_NOT_ALLOWED"
            }
        
        return {
            "valid": True,
            "message": "Message validation passed"
        }