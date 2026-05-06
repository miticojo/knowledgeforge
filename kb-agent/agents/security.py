import os
from google.genai import types

try:
    from google.cloud import modelarmor_v1
    _MA_AVAILABLE = True
except ImportError:
    _MA_AVAILABLE = False

MODEL_ARMOR_TEMPLATE_ID = os.getenv("MODEL_ARMOR_TEMPLATE_ID")
ENABLE_MODEL_ARMOR = os.getenv("ENABLE_MODEL_ARMOR", "false").lower() == "true"

def sanitize_with_model_armor(text: str, user_id: str):
    """
    Send text to the Model Armor API for validation.
    Returns (sanitized_text, error).
    """
    if not _MA_AVAILABLE or not ENABLE_MODEL_ARMOR or not MODEL_ARMOR_TEMPLATE_ID:
        return text, None
        
    try:
        ma_client = modelarmor_v1.ModelArmorClient()
        request_ma = modelarmor_v1.types.SanitizeUserPromptRequest(
            name=MODEL_ARMOR_TEMPLATE_ID,
            user_prompt_data=modelarmor_v1.types.DataItem(text=text)
        )
        response = ma_client.sanitize_user_prompt(request=request_ma)
        
        # Access the overall match state (integer 2 = MATCH_FOUND)
        if int(response.sanitization_result.filter_match_state) == 2:
            return None, "Policy Violation: The content was flagged as unsafe."
            
        return text, None
    except Exception as e:
        print(f"Model Armor Error: {e}")
        return text, None  # Fail-open allowing content if service is unreachable

def before_agent_security_check(callback_context, **kwargs):
    """
    ADK before-agent callback that blocks malicious requests using Model Armor.
    """
    if not ENABLE_MODEL_ARMOR:
        return None
        
    text = ""
    # ADK's CallbackContext exposes user_content and session properties
    if hasattr(callback_context, 'user_content') and callback_context.user_content and callback_context.user_content.parts:
        for p in callback_context.user_content.parts:
            if hasattr(p, 'text') and p.text:
                text += p.text
                
    if text:
        user_id = getattr(callback_context, 'user_id', 'unknown_user')
        sanitized, err = sanitize_with_model_armor(text, user_id)
        if err:
            print(f"[Security] Request blocked: {err}")
            return types.Content(
                role="model", 
                parts=[types.Part.from_text(text="Sorry, but this request violates security policies and cannot be processed.")]
            )
            
    return None
