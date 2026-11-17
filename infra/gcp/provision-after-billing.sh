#!/usr/bin/env bash
set -euo pipefail

# Run after a billing account is linked and GCP_ZONE is set to a verified
# zone with NVIDIA L4 quota and current g2 capacity.
: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID to the reviewed project ID}"
: "${GCP_ZONE:?Set GCP_ZONE to a verified zone}"
PROJECT_ID="$GCP_PROJECT_ID"
ZONE="$GCP_ZONE"
VM_NAME="${GCP_VM_NAME:-gamst-bench-gpu}"
BUCKET="${GCP_BUCKET:-gamst-bench-data-$PROJECT_ID}"
LOCATION="${GCP_BUCKET_LOCATION:-${ZONE%-*}}"

# Enable required APIs after billing is available.
gcloud services enable \
  compute.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  serviceusage.googleapis.com \
  --project "$PROJECT_ID"

# GPU VM: private inference ports, no automatic restart, terminate on host maintenance.
gcloud compute instances create "$VM_NAME" \
  --project "$PROJECT_ID" \
  --zone "$ZONE" \
  --machine-type=g2-standard-8 \
  --accelerator=type=nvidia-l4,count=1 \
  --maintenance-policy=TERMINATE \
  --restart-on-failure=no \
  --boot-disk-size=200GB \
  --boot-disk-type=pd-balanced \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --scopes=cloud-platform \
  --tags=gamst-bench-ssh \
  --metadata=startup-script='#!/bin/bash\n# Safety stop: prevent an unattended GPU VM from running beyond four hours.\nshutdown -h +240\n'

# Optional separate persistent data disk. Disabled by default so running this
# script never creates extra billable storage without an explicit opt-in.
if [[ "${GCP_DATA_DISK_GB:-0}" =~ ^[1-9][0-9]*$ ]]; then
  gcloud compute disks create gamst-bench-data \
    --project "$PROJECT_ID" \
    --zone "$ZONE" \
    --size="${GCP_DATA_DISK_GB}GB" \
    --type=pd-balanced

  gcloud compute instances attach-disk "$VM_NAME" \
    --project "$PROJECT_ID" \
    --zone "$ZONE" \
    --disk=gamst-bench-data
else
  echo "Skipping separate data disk: GCP_DATA_DISK_GB=${GCP_DATA_DISK_GB:-0}"
fi

# Private, uniform-bucket-level-access storage for raw data and artifacts.
if ! gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" \
    --project "$PROJECT_ID" \
    --location="$LOCATION" \
    --default-storage-class=STANDARD \
    --uniform-bucket-level-access
else
  echo "Bucket already exists: gs://$BUCKET"
fi

# Create the expected private directory layout and prepare the attached disk.
gcloud compute ssh "$VM_NAME" \
  --project "$PROJECT_ID" \
  --zone "$ZONE" \
  --command='set -e; sudo mkdir -p /mnt/gamst-data/{raw,manifests,checkpoints,runs}; sudo chown -R "$USER":"$USER" /mnt/gamst-data; sudo mkdir -p /srv/{data,gamst-runs,manifests,models}; sudo chown -R "$USER":"$USER" /srv/data /srv/gamst-runs /srv/manifests /srv/models'

# Install the repository and MCP launcher. Native benchmark/model/data setup stays explicit.
gcloud compute ssh "$VM_NAME" \
  --project "$PROJECT_ID" \
  --zone "$ZONE" \
  --command='set -e; if [ ! -d /srv/gamst-bench/.git ]; then git clone https://github.com/NomaDamas/Gamst-bench.git /srv/gamst-bench; fi; cd /srv/gamst-bench; git pull --ff-only; chmod +x scripts/serve-mcp.sh'

echo "Provisioned $VM_NAME in $PROJECT_ID/$ZONE. Configure a reviewed /srv/private/gamst-mcp.json before connecting MCP."
