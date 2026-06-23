import os
import threading
import time

try:
    import openai
    # Try to import the modern client (v1.0+)
    try:
        from openai import OpenAI, DefaultHttpxClient
    except ImportError:
        from openai import OpenAI # Fallback for older v1.x
        DefaultHttpxClient = None # Mark as unavailable
except ImportError:
    openai = None
    OpenAI = None
    DefaultHttpxClient = None

# --- "World-Class" Fix: Import httpx for modern proxy support in the openai library ---
try:
    import httpx
except ImportError:
    httpx = None

# --- "World-Class" Fix: Add safe import for httpx_socks ---
try:
    from httpx_socks import SyncProxyTransport
except ImportError:
    SyncProxyTransport = None

# --- "World-Class" Fix: Add native Gemini client support ---
try:
    import google.genai as genai
except ImportError:
    genai = None

# A singleton pattern to cache the client instance
_ai_client_instance = None
_ai_client_instance_lock = threading.Lock()

def get_ai_client(settings, logger):
    """
    A "world-class" factory function to get the correct AI client based on settings.
    This is a centralized function to be used across the application.
    It uses a singleton pattern to return a cached client instance.
    Returns a configured OpenAI-compatible client instance or None.
    """
    # --- "World-Class" Fix: Respect the enabled flag immediately ---
    # If AI is disabled in settings (e.g. by the user after a failed health check),
    # we must return None immediately, even if a client instance is cached.
    if not settings.ai.ai_enabled:
        return None

    global _ai_client_instance
    # Fast path without lock
    if _ai_client_instance:
        return _ai_client_instance

    with _ai_client_instance_lock:
        # Check again inside the lock
        if _ai_client_instance:
            return _ai_client_instance

        if not settings.ai.ai_enabled:
            return None

        provider = settings.ai.ai_provider.lower()
        if provider == 'groq':
            if not openai: return None
            api_key = settings.dev.groq_api_key
            base_url = 'https://api.groq.com/openai/v1'
            if not api_key:
                logger.debug("AI is enabled, but 'GROQ_API_KEY' not found in .env file.")
                return None
        elif provider == 'gemini':
            if not genai:
                logger.error("Gemini provider selected, but 'google-genai' is not installed. Please run 'pip install -r requirements.txt'.")
                return None
            api_key = settings.dev.gemini_api_key
            base_url = None # Not used for native Gemini client
            if not api_key:
                logger.debug("AI is enabled, but 'GEMINI_API_KEY' not found in .env file.")
                return None
        elif provider == 'ollama':
            if not openai: return None
            api_key = 'ollama'  # Dummy key for Ollama
            base_url = 'http://localhost:11434/v1'
        else:
            logger.error(f"Unsupported AI provider: {provider}")
            return None

        http_client = None
        
        # --- "World-Class" Resiliency: Try all configured proxies, not just the first one ---
        proxies_to_try = []
        if settings.proxy.proxy_enabled and settings.proxy.proxy_ai_connections:
            if not httpx:
                logger.error("Proxy for AI is enabled, but 'httpx' is not installed. Please run 'pip install httpx'.")
                return None
            proxies_to_try.extend(settings.proxy.proxy_list)

        # Only add a direct connection as a fallback if proxies are not enabled for AI
        if not (settings.proxy.proxy_enabled and settings.proxy.proxy_ai_connections):
            proxies_to_try.append(None)

        for proxy_str in proxies_to_try:
            if proxy_str:
                parts = proxy_str.split('|')
                if len(parts) < 3: continue
                proxy_type, host, port = parts[0], parts[1], parts[2]
                user = parts[3] if len(parts) > 3 else None
                pwd = parts[4] if len(parts) > 4 else None
                auth = f"{user}:{pwd}@" if user and pwd else ""
                proxy_url = f"{proxy_type}://{auth}{host}:{port}"
                logger.info(f"Attempting AI connection via proxy: {host}:{port}")
            else:
                logger.info("Attempting AI connection directly (no proxy)...")
                proxy_url = None

            try:
                # --- Provider-Specific Client Initialization ---
                if provider == 'gemini':
                    # The google-generativeai library respects https_proxy env var
                    if proxy_url:
                        os.environ['https_proxy'] = proxy_url
                        os.environ['http_proxy'] = proxy_url
                    else:
                        if 'https_proxy' in os.environ: del os.environ['https_proxy']
                        if 'http_proxy' in os.environ: del os.environ['http_proxy']

                    temp_client = _GeminiClientWrapper(api_key)
                    temp_client.models.list() # Health check
                else: # Groq, Ollama use the OpenAI client
                    if proxy_url:
                        proxy_timeout = httpx.Timeout(30.0, connect=60.0)
                        if proxy_type.lower() == "socks5":
                            if SyncProxyTransport:
                                transport = SyncProxyTransport.from_url(proxy_url)
                                http_client = httpx.Client(transport=transport, timeout=proxy_timeout)
                            else:
                                logger.warning("SOCKS5 proxy requested but 'httpx_socks' is not installed. Falling back to direct connection.")
                                http_client = None
                        elif proxy_type.lower() == "http":
                            http_client = httpx.Client(proxies=proxy_url, timeout=proxy_timeout)
                        else:
                            logger.warning(f"Unsupported proxy type for OpenAI client: {proxy_type}. Skipping.")
                            continue
                    else:
                        http_client = None

                    client_params = {'base_url': base_url, 'api_key': api_key.strip() if api_key else None}
                    
                    # --- "World-Class" Tuning: Optimize for Provider Type ---
                    if provider == 'ollama':
                        # Local models need more time to process but fewer retries to prevent congestion/queueing.
                        client_params['max_retries'] = 0  # Do not retry; if the machine is overloaded, adding load helps nothing.
                        client_params['timeout'] = 300.0  # Give local hardware 5 minutes to finish a queue.
                    else:
                        # Cloud providers (Groq/OpenAI) fail fast and benefit from retries.
                        client_params['max_retries'] = 3
                        client_params['timeout'] = 60.0

                    if http_client:
                        client_params['http_client'] = http_client
                    
                    temp_client = OpenAI(**client_params)
                    temp_client.models.list() # Health check

                # If we got here, the connection is good. Set the singleton and return.
                _ai_client_instance = temp_client
                proxy_status = f"YES ({host}:{port})" if proxy_str else "NO"
                logger.info(f"AI Client initialized successfully. Provider: {provider.upper()} | Proxy: {proxy_status}")
                return _ai_client_instance

            except openai.APIConnectionError as e:
                logger.warning(f"AI connection attempt failed with APIConnectionError: {e}. Trying next option.")
                continue
            except openai.AuthenticationError as e:
                logger.error(f"AI Authentication Failed: {e}. Please check your API key for the '{provider}' provider.")
                return None
            except Exception as e:
                logger.warning(f"AI connection attempt failed: {e.__class__.__name__}. Trying next option.")
                continue

    # If the loop finishes without a successful connection
    logger.error("All AI connection methods (proxies and direct) failed.")
    return None # Explicitly return None if all attempts fail


class _GeminiClientWrapper:
    """
    A "world-class" factory function to get the correct AI client based on settings.
    Wrapper for the new google-genai SDK to make it look like an OpenAI client.
    """
    def __init__(self, api_key):
        from google.genai import Client, types
        self.client = Client(api_key=api_key)
        self.models = self._Models(self.client)
        self.chat = self._Chat(self.client, self)
        self.working_model = None # Cache for the model that succeeds after a fallback
        self.failed_models = set() # Track models that have 404'd to avoid retrying them

    class _Models:
        def __init__(self, client):
            self.client = client

        def list(self):
            # Perform a real API call to verify credentials (iterate once)
            try:
                next(iter(self.client.models.list()), None)
            except Exception:
                # Let the exception propagate to be caught by get_ai_client
                raise

            class MockPage:
                def __init__(self, data):
                    self.data = data
            return MockPage([])

    class _Chat:
        def __init__(self, client, wrapper):
            self.completions = self._Completions(client, wrapper)

        class _Completions:
            def __init__(self, client, wrapper):
                self.client = client
                self.wrapper = wrapper

            def create(self, model, messages, **kwargs):
                # Convert OpenAI messages to single string for simple Gemini usage
                # New SDK requires 'contents' to be a list or string.
                # We will construct a simple string prompt to avoid complex Message object construction errors.

                # --- "World-Class" Self-Healing ---
                # If a fallback has previously succeeded, use the cached working model
                # instead of retrying the failing one from the config.
                if self.wrapper.working_model:
                    model = self.wrapper.working_model
                
                prompt_parts = []
                system_instruction = None
                
                for msg in messages:
                    if msg['role'] == 'system':
                        prompt_parts.append(f"System: {msg['content']}")
                    elif msg['role'] == 'user':
                        prompt_parts.append(f"User: {msg['content']}")
                    elif msg['role'] == 'assistant':
                        prompt_parts.append(f"Model: {msg['content']}")
                
                full_prompt = "\n".join(prompt_parts)

                # --- "World-Class" Retry Helper ---
                # Encapsulate the retry logic so it can be used for both primary and fallback attempts.
                def generate_with_retry(model_id, prompt_text):
                    for attempt in range(3):
                        try:
                            return self.client.models.generate_content(
                                model=model_id,
                                contents=prompt_text
                            )
                        except Exception as retry_err:
                            # Check for rate limit errors
                            if "429" in str(retry_err) or "RESOURCE_EXHAUSTED" in str(retry_err):
                                if attempt < 2:
                                    # Linear backoff: 12s, 17s
                                    time.sleep(12 + attempt * 5)
                                    continue
                            raise retry_err

                # Skip known bad models
                if model in self.wrapper.failed_models:
                    # If the requested model is already known to fail, force a fallback immediately
                    raise Exception(f"Model {model} previously failed. Triggering fallback.")

                try:
                    # Attempt to use the requested model (with retry)
                    response = generate_with_retry(model, full_prompt)
                except Exception as e:
                    # Mark this model as failed ONLY if it's not a rate limit error.
                    # If it's just busy (429), we want to be able to try it again later.
                    if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                        self.wrapper.failed_models.add(model)

                    # --- "World-Class" Resilience ---
                    # If the specific model fails (404), try a known fallback list.
                    # Updated with newer 2.0/2.5 models found in your available list
                    fallbacks = ['gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-flash', 'gemini-1.5-pro']
                    
                    # Filter out any models we already know are bad
                    candidates = [m for m in fallbacks if m not in self.wrapper.failed_models]
                    
                    for fallback in candidates:
                        try:
                            # Apply the same retry logic to fallbacks
                            response = generate_with_retry(fallback, full_prompt)
                            # On success, cache this model for the rest of the session.
                            self.wrapper.working_model = fallback
                            model = fallback # Update the model used for this response
                            
                            # Only log this once to avoid spam
                            if not getattr(self.wrapper, '_fallback_logged', False):
                                print(f"  [AI Info] Successfully fell back to model: {fallback}. Caching for session.")
                                self.wrapper._fallback_logged = True
                            break # Success!
                        except Exception as fb_err:
                            # print(f"  [AI Debug] Fallback {fallback} failed: {fb_err}")
                            continue # Try next fallback
                    else:
                        raise e # All fallbacks failed, raise the original error or last error

                class MockChoice:
                    class MockMessage:
                        def __init__(self, content):
                            self.content = content
                            self.role = 'assistant'
                    def __init__(self, content):
                        self.message = self.MockMessage(content)
                
                class MockCompletion:
                    def __init__(self, content, used_model):
                        self.choices = [MockChoice(content)]
                        # Add the model attribute for accurate logging
                        self.model = used_model

                return MockCompletion(response.text, model)