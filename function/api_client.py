import time
import threading

class ApiClient:
    """
    A "smart" and resilient API client that implements the Circuit Breaker pattern.
    This prevents the application from repeatedly calling a service that is known to be failing.
    """
    def __init__(self, logger, failure_threshold=5, recovery_timeout=300):
        """
        Initializes the circuit breaker.
        :param logger: The logger instance.
        :param failure_threshold: Number of failures to allow before opening the circuit.
        :param recovery_timeout: Seconds to wait before moving to a half-open state.
        """
        self.logger = logger
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        
        # State is stored per-endpoint to manage multiple APIs
        self._states = {}
        self._lock = threading.Lock()

    def _get_state(self, endpoint_id):
        """Gets the state for a specific endpoint, creating it if it doesn't exist."""
        with self._lock:
            if endpoint_id not in self._states:
                self._states[endpoint_id] = {
                    "failures": 0,
                    "state": "closed", # Can be "closed", "open", or "half-open"
                    "last_failure_time": 0
                }
            return self._states[endpoint_id]

    def execute(self, endpoint_id, api_call_func, *args, **kwargs):
        """
        Executes an API call through the circuit breaker.
        :param endpoint_id: A unique name for the API endpoint (e.g., 'hunter', 'zapier').
        :param api_call_func: The function that makes the actual API call.
        :return: The result of the API call, or None if the circuit is open or the call fails.
        """
        state = self._get_state(endpoint_id)

        if state["state"] == "open":
            if time.time() - state["last_failure_time"] > self._recovery_timeout:
                state["state"] = "half-open"
                self.logger.info(f"Circuit Breaker for '{endpoint_id}': State changed to HALF-OPEN. Permitting one test call.")
            else:
                self.logger.debug(f"Circuit Breaker for '{endpoint_id}': Circuit is open. Skipping call.")
                return None

        try:
            result = api_call_func(*args, **kwargs)
            # If the call was successful (especially in half-open state), reset the circuit.
            if state["state"] != "closed":
                self.logger.info(f"Circuit Breaker for '{endpoint_id}': API call successful. Circuit is now CLOSED.")
                state["failures"] = 0
                state["state"] = "closed"
            return result
        except Exception as e:
            # Record the failure
            state["failures"] += 1
            state["last_failure_time"] = time.time()
            
            # If we are in half-open, the test failed, so re-open the circuit.
            if state["state"] == "half-open":
                state["state"] = "open"
                self.logger.warning(f"Circuit Breaker for '{endpoint_id}': Test call failed. Circuit is RE-OPENED for {self._recovery_timeout}s.")
            # If we have exceeded the failure threshold, open the circuit.
            elif state["failures"] >= self._failure_threshold:
                if state["state"] != "open": # Log only on the transition
                    state["state"] = "open"
                    self.logger.error(f"Circuit Breaker for '{endpoint_id}': Threshold of {self._failure_threshold} failures reached. Circuit is OPEN for {self._recovery_timeout}s.")
            
            # Re-raise the exception so the calling function knows it failed.
            raise e