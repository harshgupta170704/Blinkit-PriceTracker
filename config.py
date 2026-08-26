# ─── Blinkit Price Tracker Configuration ──────────────────────────────────────

# Pincodes to check products in (outer loop)
PINCODES = [
    {"pincode": "400001", "city": "Mumbai"},
    {"pincode": "110001", "city": "Delhi"},
    {"pincode": "560001", "city": "Bangalore"},
    {"pincode": "500001", "city": "Hyderabad"},
    {"pincode": "600001", "city": "Chennai"},
    {"pincode": "700001", "city": "Kolkata"},
    {"pincode": "411001", "city": "Pune"},
    {"pincode": "380001", "city": "Ahmedabad"},
    {"pincode": "122001", "city": "Gurgaon"},
    {"pincode": "201301", "city": "Noida"},
]

# Zyte API
ZYTE_API_URL = "https://api.zyte.com/v1/extract"

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds between retries

# Zyte browser action timeout (seconds to wait after JS injection)
JS_WAIT_TIMEOUT = 12.0

# Input / Output
INPUT_CSV = "input_products.csv"
OUTPUT_DIR = "output"
SCREENSHOT_DIR = "screenshots"
