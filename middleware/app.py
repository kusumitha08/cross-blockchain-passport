from flask               import Flask, request, jsonify
from flask_cors          import CORS
from web3                import Web3
import json
import os
import sys
from datetime            import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'crypto_core'))
from crypto_utils import generate_identity_hash, sign_identity, verify_signature
from keys         import load_or_generate_keys

app  = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
# Connect to Ganache
# ─────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

if w3.is_connected():
    print("   ✅ Connected to Ganache blockchain!")
else:
    print("   ❌ Could not connect to Ganache!")

# ─────────────────────────────────────────
# Load contract addresses
# ─────────────────────────────────────────
ADDRESSES_FILE = os.path.join(
    os.path.dirname(__file__), '..', 'crypto_core', 'contract_addresses.json'
)
with open(ADDRESSES_FILE) as f:
    addresses = json.load(f)

AADHAAR_ADDRESS  = addresses["AadhaarRegistry"]
PASSPORT_ADDRESS = addresses["PassportRegistry"]

# ─────────────────────────────────────────
# Load contract ABIs from build folder
# ─────────────────────────────────────────
BUILD_DIR = os.path.join(os.path.dirname(__file__), '..', 'build', 'contracts')

with open(os.path.join(BUILD_DIR, 'AadhaarRegistry.json')) as f:
    AADHAAR_ABI = json.load(f)["abi"]

with open(os.path.join(BUILD_DIR, 'PassportRegistry.json')) as f:
    PASSPORT_ABI = json.load(f)["abi"]

# ─────────────────────────────────────────
# Create contract instances
# ─────────────────────────────────────────
aadhaar_contract  = w3.eth.contract(
    address = Web3.to_checksum_address(AADHAAR_ADDRESS),
    abi     = AADHAAR_ABI
)
passport_contract = w3.eth.contract(
    address = Web3.to_checksum_address(PASSPORT_ADDRESS),
    abi     = PASSPORT_ABI
)

# ─────────────────────────────────────────
# Default account (Ganache account 0)
# ─────────────────────────────────────────
default_account = w3.eth.accounts[0]
w3.eth.default_account = default_account

# ─────────────────────────────────────────
# Load shared ECDSA keys
# ─────────────────────────────────────────
private_key, public_key = load_or_generate_keys()

# ─────────────────────────────────────────
# Helper: send transaction
# ─────────────────────────────────────────
def send_transaction(func):
    tx_hash    = func.transact({"from": default_account})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return tx_receipt

# ═══════════════════════════════════════════════════
# ROUTE 1 — Home
# ═══════════════════════════════════════════════════
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message"          : "Cross-Blockchain Middleware running on Ganache!",
        "status"           : "online",
        "ganache"          : "connected" if w3.is_connected() else "disconnected",
        "aadhaar_contract" : AADHAAR_ADDRESS,
        "passport_contract": PASSPORT_ADDRESS,
        "routes"           : [
            "GET  /health",
            "POST /aadhaar/register",
            "GET  /aadhaar/citizens",
            "GET  /aadhaar/proof/<aadhaar_id>",
            "POST /passport/apply",
            "GET  /passport/applications",
            "GET  /passport/validate"
        ]
    })

# ═══════════════════════════════════════════════════
# ROUTE 2 — Health check
# ═══════════════════════════════════════════════════
@app.route("/health", methods=["GET"])
def health():
    try:
        aadhaar_count  = aadhaar_contract.functions.getTotalRegistered().call()
        passport_count = passport_contract.functions.getTotalApplications().call()
        return jsonify({
            "middleware"          : "online",
            "ganache"             : "connected",
            "aadhaar_registered"  : aadhaar_count,
            "passport_applications": passport_count,
            "block_number"        : w3.eth.block_number,
            "network_id"          : w3.net.version
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# ROUTE 3 — Register citizen on Aadhaar blockchain
# ═══════════════════════════════════════════════════
@app.route("/aadhaar/register", methods=["POST"])
def register_citizen():
    data       = request.get_json()
    name       = data.get("name")
    dob        = data.get("dob")
    aadhaar_id = data.get("aadhaar_id")

    if not name or not dob or not aadhaar_id:
        return jsonify({"error": "name, dob and aadhaar_id are required"}), 400

    try:
        # Check if already registered on blockchain
        already = aadhaar_contract.functions.isRegistered(aadhaar_id).call()
        if already:
            return jsonify({"error": "Aadhaar ID already registered on blockchain"}), 400

        # Generate hash and signature
        identity_hash = generate_identity_hash(name, dob, aadhaar_id)
        signature     = sign_identity(private_key, identity_hash)

        # Register on Aadhaar blockchain (Ganache)
        receipt = send_transaction(
            aadhaar_contract.functions.registerIdentity(
                aadhaar_id,
                identity_hash,
                signature
            )
        )

        return jsonify({
            "success"         : True,
            "name"            : name,
            "aadhaar_id"      : aadhaar_id,
            "identity_hash"   : identity_hash,
            "transaction_hash": receipt.transactionHash.hex(),
            "block_number"    : receipt.blockNumber,
            "gas_used"        : receipt.gasUsed
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# ROUTE 4 — Get all registered citizens
# ═══════════════════════════════════════════════════
@app.route("/aadhaar/citizens", methods=["GET"])
def get_citizens():
    try:
        total = aadhaar_contract.functions.getTotalRegistered().call()
        citizens = []
        for i in range(total):
            aadhaar_id = aadhaar_contract.functions.registeredIds(i).call()
            proof      = aadhaar_contract.functions.getIdentityProof(aadhaar_id).call()
            citizens.append({
                "aadhaar_id"   : aadhaar_id,
                "identity_hash": proof[0][:30] + "...",
                "timestamp"    : proof[2]
            })
        return jsonify({
            "total"   : total,
            "citizens": citizens
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# ROUTE 5 — Get identity proof from Aadhaar chain
# ═══════════════════════════════════════════════════
@app.route("/aadhaar/proof/<aadhaar_id>", methods=["GET"])
def get_identity_proof(aadhaar_id):
    try:
        proof = aadhaar_contract.functions.getIdentityProof(aadhaar_id).call()
        identity_hash = proof[0]
        signature     = proof[1]
        timestamp     = proof[2]
        exists        = proof[3]

        if not exists:
            return jsonify({"found": False, "error": "Aadhaar ID not found"}), 404

        return jsonify({
            "found"        : True,
            "aadhaar_id"   : aadhaar_id,
            "identity_hash": identity_hash,
            "signature"    : signature,
            "timestamp"    : timestamp,
            "block_number" : w3.eth.block_number
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# ROUTE 6 — Apply for passport
# ═══════════════════════════════════════════════════
@app.route("/passport/apply", methods=["POST"])
def apply_for_passport():
    data           = request.get_json()
    applicant_name = data.get("name")
    aadhaar_id     = data.get("aadhaar_id")

    if not applicant_name or not aadhaar_id:
        return jsonify({"error": "name and aadhaar_id are required"}), 400

    try:
        # Step 1: Get proof from Aadhaar blockchain
        proof         = aadhaar_contract.functions.getIdentityProof(aadhaar_id).call()
        identity_hash = proof[0]
        signature     = proof[1]
        exists        = proof[3]

        # Step 2: Verify signature
        if not exists:
            status   = "REJECTED"
            reason   = "Aadhaar ID not found on blockchain"
            verified = False
            identity_hash = "0" * 64
        else:
            verified = verify_signature(public_key, identity_hash, signature)
            if verified:
                status = "APPROVED"
                reason = "Identity verified successfully"
            else:
                status   = "REJECTED"
                reason   = "Invalid signature — possible tampering"

        # Step 3: Record result on Passport blockchain
        receipt = send_transaction(
            passport_contract.functions.submitApplication(
                aadhaar_id,
                applicant_name,
                status,
                identity_hash
            )
        )

        return jsonify({
            "applicant"        : applicant_name,
            "aadhaar_id"       : aadhaar_id,
            "status"           : status,
            "reason"           : reason,
            "verified"         : verified,
            "transaction_hash" : receipt.transactionHash.hex(),
            "block_number"     : receipt.blockNumber,
            "gas_used"         : receipt.gasUsed,
            "timestamp"        : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "identity_hash"    : identity_hash[:30] + "..."
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# ROUTE 7 — Get all passport applications
# ═══════════════════════════════════════════════════
@app.route("/passport/applications", methods=["GET"])
def get_applications():
    try:
        total        = passport_contract.functions.getTotalApplications().call()
        applications = []
        for i in range(1, total + 1):
            app_data = passport_contract.functions.getApplication(i).call()
            applications.append({
                "app_id"        : i,
                "applicant_name": app_data[0],
                "aadhaar_id"    : app_data[1],
                "status"        : app_data[2],
                "timestamp"     : app_data[3]
            })
        return jsonify({
            "total"       : total,
            "applications": applications
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# ROUTE 8 — Validate (show blockchain stats)
# ═══════════════════════════════════════════════════
@app.route("/passport/validate", methods=["GET"])
def validate():
    try:
        return jsonify({
            "valid"                : True,
            "block_number"         : w3.eth.block_number,
            "total_registered"     : aadhaar_contract.functions.getTotalRegistered().call(),
            "total_applications"   : passport_contract.functions.getTotalApplications().call(),
            "aadhaar_contract"     : AADHAAR_ADDRESS,
            "passport_contract"    : PASSPORT_ADDRESS,
            "message"              : "Blockchain is valid and running on Ganache!"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════════════
# Run Flask
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n✅ Cross-Blockchain Middleware Starting...")
    print(f"   Ganache              : http://127.0.0.1:8545")
    print(f"   Aadhaar Contract     : {AADHAAR_ADDRESS}")
    print(f"   Passport Contract    : {PASSPORT_ADDRESS}")
    print(f"   Server running at    : http://localhost:5000\n")
    app.run(debug=True, port=5000)