import os
import json
from typing import Optional

try:
    import httpx
except Exception:
    httpx = None  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None  # type: ignore


class LLMUnavailableError(Exception):
    """Raised when LLM is unavailable or cannot be accessed."""
    pass


def complete_json(system: str, user: str) -> str:
    """
    Complete with JSON output from configured provider.

    Provider and model come from env variables:
    - LLM_PROVIDER: 'gemini' (and others may exist, but implement Gemini as specified)
    - LLM_MODEL: model name
    - LLM_API_KEY: API key

    Implement Gemini using plain HTTPS with httpx or the official SDK,
    with temperature 0, JSON output mode, and a 60 second timeout.
    All provider-specific code stays in this file.
    Raise clear custom LLMUnavailableError on missing key, timeout,
    network error or bad status. Never log message text or the key.
    """
    provider = (os.getenv('LLM_PROVIDER') or 'gemini').lower()
    model = os.getenv('LLM_MODEL') or 'gemini-1.5-flash'
    api_key = os.getenv('LLM_API_KEY')

    if provider == 'gemini':
        if not api_key:
            raise LLMUnavailableError('LLM API key is missing (LLM_API_KEY)')

        # Prefer official SDK if available, but must also support plain HTTPS with httpx
        # As per requirement: "Implement Gemini using plain HTTPS with httpx or the official SDK"
        if genai is not None:
            try:
                genai.configure(api_key=api_key)
                generation_config = {
                    'temperature': 0,
                    'response_mime_type': 'application/json',
                }
                model_instance = genai.GenerativeModel(
                    model_name=model,
                    generation_config=generation_config,
                )
                response = model_instance.generate_content(
                    [f'System: {system}\n\nUser: {user}'],
                    request_options={'timeout': 60}
                )
                # Try to extract text
                text = response.text if hasattr(response, 'text') else ''
                if not text:
                    # Fallback: parts
                    try:
                        parts = response.candidates[0].content.parts if response.candidates else []
                        text = ''.join(p.text for p in parts if hasattr(p, 'text'))
                    except Exception:
                        text = ''
                if not text:
                    raise LLMUnavailableError('Empty response from Gemini')
                return text
            except Exception as e:
                # Map to clear errors
                err = str(e).lower()
                if 'timeout' in err:
                    raise LLMUnavailableError(f'LLM timeout: {e}')
                if 'network' in err or 'connection' in err or 'unavailable' in err:
                    raise LLMUnavailableError(f'LLM network error: {e}')
                if 'api key' in err or 'unauthorized' in err or '401' in err or '403' in err:
                    raise LLMUnavailableError(f'LLM auth error: {e}')
                if 'bad request' in err or '400' in err or 'invalid' in err:
                    raise LLMUnavailableError(f'LLM bad request: {e}')
                # Default to LLMUnavailableError
                raise LLMUnavailableError(f'LLM error: {e}')

        # Fallback to plain HTTPS with httpx
        if httpx is None:
            raise LLMUnavailableError('httpx is not installed and google-generativeai not available')

        try:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
            payload = {
                'contents': [
                    {
                        'parts': [
                            {'text': f'System: {system}\n\nUser: {user}'}
                        ]
                    }
                ],
                'generationConfig': {
                    'temperature': 0,
                    'responseMimeType': 'application/json',
                }
            }
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code >= 400:
                    raise LLMUnavailableError(f'LLM bad status: {resp.status_code}')
                data = resp.json()
                # Extract text from response
                try:
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    return text
                except Exception:
                    raise LLMUnavailableError('Invalid response format from Gemini')
        except httpx.TimeoutException as e:
            raise LLMUnavailableError(f'LLM timeout: {e}')
        except httpx.NetworkError as e:
            raise LLMUnavailableError(f'LLM network error: {e}')
        except LLMUnavailableError:
            raise
        except Exception as e:
            raise LLMUnavailableError(f'LLM error: {e}')

    # For other providers, also follow the same pattern if they appear - but
    # per instruction focus on Gemini; still raise clear errors
    if not api_key:
        raise LLMUnavailableError('LLM API key is missing (LLM_API_KEY)')
    raise LLMUnavailableError(f'Unsupported LLM provider: {provider}')
