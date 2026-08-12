import logging
import re

logger = logging.getLogger(__name__)

class Guardrails:
    """
    Guardrail validation for prompt sanitization and output checking.
    """
    
    # Precompiled regex for lightweight filtering
    SENSITIVE_PATTERN = re.compile(
        r'\b(hack|steal|bypass|exploit|password|malware|virus|phishing|harmful|malicious)\b',
        re.IGNORECASE
    )

    @staticmethod
    def validate_input(text: str) -> bool:
        """
        Validates user input text. Returns True if safe, False otherwise.
        """
        if not text or not text.strip():
            return False
            
        if Guardrails.SENSITIVE_PATTERN.search(text):
            logger.warning(f"Guardrails: Input validation failed for text containing sensitive keywords.")
            return False
        return True

    @staticmethod
    def validate_output(text: str) -> bool:
        """
        Validates agent output text. Returns True if safe, False otherwise.
        """
        if not text or not text.strip():
            return False
            
        if Guardrails.SENSITIVE_PATTERN.search(text):
            logger.warning(f"Guardrails: Output validation failed for generated text.")
            return False
        return True
