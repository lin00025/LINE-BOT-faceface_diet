import subprocess
import re

print("Opening Cloudflare Tunnel on Port 8000...")
print("Waiting for URL to be generated...\n")

# Run cloudflared and read its output in real-time
# Cloudflared outputs its logs to stderr, so we redirect stderr to stdout
process = subprocess.Popen(
    ["/opt/homebrew/bin/cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

url_found = False

try:
    for line in iter(process.stdout.readline, ''):
        # Cloudflared prints info, we want to catch the trycloudflare.com link
        match = re.search(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)", line)
        
        if match and not url_found:
            url = match.group(0)
            print("="*65)
            print("🔥 SUCCESS! HERE IS YOUR EXACT WEBHOOK URL:")
            print(f"{url}/callback")
            print("="*65)
            print("\n(Leave this terminal window open to keep the tunnel alive! Press Ctrl+C to close it.)")
            url_found = True
            
except KeyboardInterrupt:
    print("\nStopping Tunnel...")
finally:
    process.terminate()
