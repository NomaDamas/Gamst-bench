#!/usr/bin/env bash
# Create one L4 VM (fresh DLVM image, no snapshot restore) in the first zone with capacity.
# Hard stop: max-run-duration + STOP so credit cannot leak.
G=${GCLOUD:-gcloud}
ZONES=${ZONES:-"asia-northeast1-a asia-northeast1-b asia-northeast1-c asia-northeast3-b asia-northeast3-a asia-east1-a asia-east1-b asia-east1-c us-central1-b us-central1-c us-east1-b us-east1-d us-west1-a us-west1-b us-west1-c us-west4-a us-west4-c europe-west4-a europe-west4-b europe-west4-c"}
for z in $ZONES; do
  case $z in asia-northeast3-*|us-central1-*) dtype=pd-standard ;; *) dtype=pd-balanced ;; esac
  echo "=== $z ($dtype)"
  if $G compute instances create gamst-hf-bench --zone "$z" --machine-type g2-standard-8 \
      --accelerator type=nvidia-l4,count=1 --maintenance-policy TERMINATE --no-restart-on-failure \
      --provisioning-model STANDARD --max-run-duration 7h --instance-termination-action STOP \
      --service-account 611216126368-compute@developer.gserviceaccount.com --scopes cloud-platform \
      --image-family pytorch-2-9-cu129-ubuntu-2204-nvidia-580 --image-project deeplearning-platform-release \
      --boot-disk-size 400GB --boot-disk-type "$dtype" --metadata install-nvidia-driver=True 2>&1 | tail -3; then
    if $G compute instances describe gamst-hf-bench --zone "$z" --format='value(status)' 2>/dev/null | grep -q RUNNING; then
      echo "OK $z"; exit 0
    fi
  fi
done
echo "NO_CAPACITY"; exit 1
