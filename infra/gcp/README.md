# GCP execution preparation

Status: **not provisioned**. Aside access was rejected by the session's computer-use approval layer. This directory is a reviewable plan, not evidence that a VM exists. Local commands may build/test the website; inference and dataset acquisition run exclusively on GCP.

## Provisioning through Aside

1. Use the Google account specified privately by the owner. In Cloud Console verify the active account and project display name `gamst`; record its unique project ID. Do not silently substitute another project or create a new billing account.
2. Verify billing, Compute Engine API, region and GPU quota. Select a region with capacity and inspect its live price estimate. Candidate smoke machine: `g2-standard-8` with one NVIDIA L4; model precision/context and VRAM fit must be checked before final selection.
3. Select a pinned supported GPU image, least-privilege existing service account, no public inference port, and owner-approved storage. Start with a 200 GiB boot disk; large datasets require separate sizing. Restrict benchmark artifacts and licensed videos to private storage.
4. Set a four-hour maximum runtime with STOP, disable automatic restart, and record the stop policy. Stopped VMs may still incur disk/storage charges. Avoid unattended restart schedules. Confirm GPU visibility and driver/runtime versions before downloading weights.
5. Pin this repo, Gamst, plugins and benchmark runners. Acquire only the smoke-set data first. Record the VM/image/configuration and prices in private run metadata. Validate accounting and official scoring before a full run.
6. Export traces, full configuration and scored artifacts. Confirm the VM is stopped when the run ends. Do not publish account credentials or private dataset content in this repository.

The account, actual project ID, zone, image, quota, cost estimate and VM ID remain **unverified**. This plan intentionally contains no fabricated cloud identifiers.

Official references: [GPU VM documentation](https://cloud.google.com/compute/docs/gpus/about-gpus), [VM creation flags](https://cloud.google.com/sdk/gcloud/reference/compute/instances/create).
