#!/usr/bin/env bash
# ==============================================================================
# Agentic Terraform as a Service (TaaS) - One-Click Setup Script
# ==============================================================================
set -e

echo "=================================================================="
echo " Setting up Agentic Terraform as a Service (TaaS)"
echo "=================================================================="

# 1. Install / Verify Terraform (Persistent in Cloud Shell $HOME)
echo "[1/4] Checking Terraform binary..."
USER_BIN="$HOME/.local/bin"
mkdir -p "$USER_BIN"

if ! grep -q "$USER_BIN" ~/.bashrc 2>/dev/null; then
    echo "export PATH=\"$USER_BIN:\$PATH\"" >> ~/.bashrc
fi
export PATH="$USER_BIN:$PATH"

if [ ! -x "$USER_BIN/terraform" ] && (! command -v terraform &> /dev/null || ! terraform version &> /dev/null); then
    echo "  -> Installing persistent Terraform v1.9.8 to $USER_BIN..."
    TERRAFORM_VERSION="1.9.8"
    TMP_DIR=$(mktemp -d)
    curl -sLo "${TMP_DIR}/terraform.zip" "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
    unzip -q "${TMP_DIR}/terraform.zip" -d "${TMP_DIR}"
    
    # 1. Install to persistent home directory so it survives Cloud Shell reboots
    cp "${TMP_DIR}/terraform" "$USER_BIN/terraform"
    chmod +x "$USER_BIN/terraform"
    
    # 2. Also symlink to system directories so any cached shell paths work
    if [ "$(id -u)" -eq 0 ]; then
        ln -sf "$USER_BIN/terraform" /usr/local/bin/terraform 2>/dev/null || true
        ln -sf "$USER_BIN/terraform" /usr/bin/terraform 2>/dev/null || true
    else
        sudo ln -sf "$USER_BIN/terraform" /usr/local/bin/terraform 2>/dev/null || true
        sudo ln -sf "$USER_BIN/terraform" /usr/bin/terraform 2>/dev/null || true
    fi
    rm -rf "${TMP_DIR}"
    hash -r
    echo "  ✓ Persistent Terraform installed successfully: $($USER_BIN/terraform version | head -n 1)"
else
    # Ensure system symlinks and PATH are refreshed
    if [ -x "$USER_BIN/terraform" ]; then
        sudo ln -sf "$USER_BIN/terraform" /usr/bin/terraform 2>/dev/null || true
        sudo ln -sf "$USER_BIN/terraform" /usr/local/bin/terraform 2>/dev/null || true
        hash -r
        echo "  ✓ Persistent Terraform is ready: $($USER_BIN/terraform version | head -n 1)"
    else
        echo "  ✓ Terraform is already available: $(terraform version | head -n 1)"
    fi
fi

# 2. Virtual Environment & Python Dependencies
echo "[2/4] Setting up Python virtual environment..."
if [ -z "$VIRTUAL_ENV" ]; then
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
fi

echo "  -> Installing requirements from requirements.txt..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Python dependencies installed."

# 3. Environment Variables
echo "[3/4] Configuring Environment Variables..."
CURRENT_PROJECT="$(gcloud config get-value project 2>/dev/null || echo '')"

export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$CURRENT_PROJECT}"
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-asia-south2}"
export TAAS_STATE_BUCKET="${TAAS_STATE_BUCKET:-terraform-implementation}"
export TAAS_MODEL="${TAAS_MODEL:-gemini-3.5-flash-lite}"

# Write to .env for persistence
cat <<EOF > .env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT}
GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}
TAAS_STATE_BUCKET=${TAAS_STATE_BUCKET}
TAAS_MODEL=${TAAS_MODEL}
EOF

echo "  • GOOGLE_CLOUD_PROJECT   : ${GOOGLE_CLOUD_PROJECT}"
echo "  • GOOGLE_CLOUD_LOCATION  : ${GOOGLE_CLOUD_LOCATION}"
echo "  • TAAS_STATE_BUCKET      : ${TAAS_STATE_BUCKET}"
echo "  • TAAS_MODEL             : ${TAAS_MODEL}"
echo "  ✓ Variables configured and saved to .env"

# 4. Finish
echo "[4/4] Ready to run!"
echo "=================================================================="
echo "To start the Google ADK Web UI, run:"
echo "  source venv/bin/activate"
echo "  adk web --allow_origins \"regex:https://.*\.cloudshell\.dev\""
echo ""
echo "Or to run the CLI directly:"
echo "  python run.py"
echo "=================================================================="
