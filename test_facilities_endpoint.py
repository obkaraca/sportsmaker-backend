"""
Facilities endpoint'ini test et
"""
import requests

API_URL = "https://tourneys-portal.preview.emergentagent.com/api"

# Test request
response = requests.get(
    f"{API_URL}/facilities/approved",
    params={"city": "Ankara", "sport": "Masa Tenisi"},
    timeout=10
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text[:500]}")
