import urllib.request
import os

os.makedirs("src/clarity_v/settings/ui_web/lib", exist_ok=True)

# Download Preact + HTM standalone
preact_url = "https://unpkg.com/htm/preact/standalone.module.js"
urllib.request.urlretrieve(preact_url, "src/clarity_v/settings/ui_web/lib/preact.js")

print("Downloaded Preact + HTM standalone.")
