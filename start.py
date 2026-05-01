import subprocess
import time
import json
import os
import sys
import requests

print("\n🚀 Cross-Blockchain Passport System — Auto Startup")
print("=" * 52)

# Step 1: Deploy contracts
print("\n📦 Step 1: Deploying smart contracts to Ganache...")
result = subprocess.run(
    "truffle migrate --reset --network development",
    capture_output = True,
    text           = True,
    shell          = True,
    cwd            = os.path.dirname(os.path.abspath(__file__))
)

output = result.stdout + result.stderr
print(output)

# Step 2: Extract new contract addresses
aadhaar_address  = None
passport_address = None
current_contract = None

for line in output.split("\n"):
    if "Deploying 'AadhaarRegistry'"  in line: current_contract = "aadhaar"
    if "Deploying 'PassportRegistry'" in line: current_contract = "passport"
    if "contract address:" in line:
        address = line.split("contract address:")[-1].strip()
        if current_contract == "aadhaar":
            aadhaar_address  = address
        elif current_contract == "passport":
            passport_address = address

if not aadhaar_address or not passport_address:
    print("❌ Could not extract contract addresses!")
    print("   Make sure Ganache is running on port 8545")
    sys.exit(1)

print(f"✅ AadhaarRegistry  : {aadhaar_address}")
print(f"✅ PassportRegistry : {passport_address}")

# Step 3: Save new addresses
addresses_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'crypto_core', 'contract_addresses.json'
)
with open(addresses_file, "w") as f:
    json.dump({
        "AadhaarRegistry" : aadhaar_address,
        "PassportRegistry": passport_address
    }, f, indent=4)

print(f"✅ Contract addresses saved!")
print("\n⚠️  Please restart Flask now:")
print("   Stop Flask (Ctrl+C) and run: python app.py")
input("\nPress Enter after Flask is restarted...")

# Step 4: Register citizens automatically
print("\n👥 Step 2: Registering citizens on Aadhaar Blockchain...")

citizens = [
    {"name": "Rajesh Kumar", "dob": "15-06-1985", "aadhaar_id": "1111-2222-3333"},
    {"name": "Priya Sharma", "dob": "22-03-1990", "aadhaar_id": "2222-3333-4444"},
    {"name": "Arun Mehta",   "dob": "08-11-1978", "aadhaar_id": "3333-4444-5555"},
    {"name": "Divya Nair",   "dob": "30-07-1995", "aadhaar_id": "4444-5555-6666"},
]

for citizen in citizens:
    try:
        res  = requests.post(
            "http://localhost:5000/aadhaar/register",
            json    = citizen,
            timeout = 10
        )
        data = res.json()
        if "error" in data:
            print(f"   ⚠️  {citizen['name']}: {data['error']}")
        else:
            print(f"   ✅ {citizen['name']} registered at block #{data['block_number']}")
    except Exception as e:
        print(f"   ❌ {citizen['name']}: {e}")

print("\n🎉 System Ready!")
print("   Open http://127.0.0.1:5500 in your browser")
print("=" * 52)