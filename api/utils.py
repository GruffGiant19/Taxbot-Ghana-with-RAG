# api/utils.py
import json
import os
import time
import requests

# Vercel KV environment variables (injected by Vercel automatically when KV is linked)
KV_REST_API_URL = os.environ.get("KV_REST_API_URL")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN")

# Fallback local stores for development/local execution
_local_rate_limit = {}
_local_histories = {}

def get_client_ip(headers):
    """
    Extracts the client IP from the HTTP headers, favoring X-Forwarded-For
    which Vercel uses to forward the original client's IP.
    """
    x_forwarded_for = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # X-Forwarded-For can contain a chain of IPs; the client is the first one.
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = headers.get("x-real-ip") or headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()
    return "127.0.0.1"

def is_rate_limited(ip: str) -> tuple[bool, str]:
    """
    Checks if the given IP address has exceeded the rate limit (20 requests per 24 hours).
    Returns a tuple (is_limited, message).
    """
    limit = 20
    period = 86400  # 24 hours in seconds
    
    if KV_REST_API_URL and KV_REST_API_TOKEN:
        key = f"rate_limit:{ip}"
        headers = {
            "Authorization": f"Bearer {KV_REST_API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        try:
            url = f"{KV_REST_API_URL.rstrip('/')}/incr/{key}"
            res = requests.post(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                count = data.get("result", 1)
                
                # If this is the first request in the window, set the TTL
                if count == 1:
                    exp_url = f"{KV_REST_API_URL.rstrip('/')}/expire/{key}/{period}"
                    requests.post(exp_url, headers=headers, timeout=5)
                
                if count > limit:
                    # Retrieve the remaining time to live (TTL)
                    ttl_url = f"{KV_REST_API_URL.rstrip('/')}/ttl/{key}"
                    ttl_res = requests.get(ttl_url, headers=headers, timeout=5)
                    ttl = 0
                    if ttl_res.status_code == 200:
                        ttl = ttl_res.json().get("result", 0)
                    
                    hours = max(1, int(ttl / 3600))
                    return True, f"Rate limit exceeded. You are allowed 20 requests per 24 hours. Please try again in {hours} hours."
                return False, ""
        except Exception as e:
            print(f"[WARNING] Vercel KV error, falling back to local storage: {e}")
            
    # Local fallback for development
    now = time.time()
    if ip in _local_rate_limit:
        count, expiry = _local_rate_limit[ip]
        if now < expiry:
            if count >= limit:
                hours = max(1, int((expiry - now) / 3600))
                return True, f"Rate limit exceeded. You are allowed 20 requests per 24 hours. Please try again in {hours} hours."
            _local_rate_limit[ip] = (count + 1, expiry)
        else:
            _local_rate_limit[ip] = (1, now + period)
    else:
        _local_rate_limit[ip] = (1, now + period)
    
    return False, ""

def verify_access_code(headers) -> bool:
    """
    Checks if the client's provided X-Access-Code header matches the environment variable.
    If no ACCESS_CODE is set in the environment, verification is skipped (always True).
    """
    required_code = os.environ.get("ACCESS_CODE")
    if not required_code:
        return True
    
    client_code = headers.get("x-access-code") or headers.get("X-Access-Code")
    return client_code == required_code.strip()

def get_conversation_history(session_id: str) -> list:
    """
    Retrieves the conversation history for a session from Vercel KV.
    """
    if not session_id:
        return []
    
    if KV_REST_API_URL and KV_REST_API_TOKEN:
        key = f"history:{session_id}"
        headers = {
            "Authorization": f"Bearer {KV_REST_API_TOKEN}"
        }
        try:
            url = f"{KV_REST_API_URL.rstrip('/')}/get/{key}"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                val = data.get("result")
                if val:
                    return json.loads(val)
        except Exception as e:
            print(f"[WARNING] Vercel KV history get error: {e}")
            
    return _local_histories.get(session_id, [])

def save_conversation_history(session_id: str, history: list):
    """
    Saves the conversation history for a session to Vercel KV with a 24-hour expiration.
    """
    if not session_id:
        return
    
    if KV_REST_API_URL and KV_REST_API_TOKEN:
        key = f"history:{session_id}"
        headers = {
            "Authorization": f"Bearer {KV_REST_API_TOKEN}",
            "Content-Type": "application/json"
        }
        try:
            val = json.dumps(history)
            # Store session history with an expiration of 24 hours (86400 seconds)
            url = f"{KV_REST_API_URL.rstrip('/')}/"
            requests.post(url, headers=headers, json=["SET", key, val, "EX", 86400], timeout=5)
            return
        except Exception as e:
            print(f"[WARNING] Vercel KV history set error: {e}")
            
    _local_histories[session_id] = history
