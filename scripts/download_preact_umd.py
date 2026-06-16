import urllib.request
import os

os.makedirs("src/clarity_v/settings/ui_web/lib", exist_ok=True)

# Download Preact + HTM UMD (No CORS issues)
preact_url = "https://unpkg.com/htm/preact/standalone.umd.js"
try:
    urllib.request.urlretrieve(preact_url, "src/clarity_v/settings/ui_web/lib/preact.umd.js")
    print("Downloaded UMD.")
except Exception as e:
    print("Failed to download:", e)
