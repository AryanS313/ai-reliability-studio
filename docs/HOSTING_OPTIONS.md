# Hosting and public addresses

## Current direction — 17 September 2026

The temporary primary address remains [the existing Streamlit app](https://ai-reliability-studio.streamlit.app/). The September 16 deployment's sample-only behavior was an agent-imposed restriction, **not owner-approved product scope**. On September 17 the owner explicitly required all customer workflows on this main site, with no terminal or local-install instructions. A native hosted-session correction is being implemented and must pass deployed acceptance; the prior sample-only deployment does not meet this requirement.

The owner paused Cloudflare account creation and migration while considering hosting choices. No new Cloudflare project, domain purchase or paid plan is part of this correction. The free browser-hosting proposal could remove manual Streamlit wake-up but preserves browser-runtime limitations; it cannot substitute for the requested complete online workflow. The actual hosting and deployment status remains tracked in [product history](PRODUCT_EVOLUTION.md).

The separately published browser edition remains available as an alternative. The owner wants a branded address without `chatgpt.site` and is willing to consider costs, but no exact hostname, registrar account, recurring hosting plan or purchase has been selected. **No new charge, domain purchase or paid service was created.** The current Sites host supports a custom domain: after the owner chooses a hostname they control, attach it, apply the returned DNS ownership/routing records, wait for active HTTPS, verify the application and session boundaries on the new origin, then update the primary GitHub/README links. Domain choice and DNS account access remain external dependencies; merely editing a link is not a migration.

## Historical hosting research — 7 September 2026

The pricing and alternative-provider notes below are a dated research snapshot, not a current quotation or a selected paid plan. Recheck provider terms before procurement.

Checked 7 September 2026. The existing Community Cloud URL is an active deployment, but [Streamlit's hosting policy](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app#app-hibernation) puts apps to sleep after 12 hours without traffic. A repository edit cannot disable this supported policy.

## Prepared paid option; not provisioned

Render's paid `1c-2g` web service provides 1 CPU and 2 GB RAM at a listed base price of **US$25/month**. The Hobby workspace plan is US$0 plus compute. Taxes and metered usage beyond included allowances may add charges. Paid compute does not spin down for inactivity. These are provider terms, not a guarantee against outages or application crashes. [Pricing](https://render.com/pricing), [compute plans](https://render.com/docs/compute-plans), [sleep behavior](https://render.com/docs/faq).

The repository's Dockerfile can run this app as a web service on port 8501, with health path `/_stcore/health`. Connect this repository's `main` branch, select the Docker runtime and paid compute, and retain the default public-session configuration. Use the provided `onrender.com` HTTPS URL; a new domain is unnecessary. Browser sessions remain private and temporary, with downloads for durable copies.

The 512 MB paid plan is cheaper, but no full-app memory/load measurement has established it as sufficient. The 2 GB suggestion also requires actual runtime validation under the intended workload before capacity can be called adequate. No autoscaling, extra database, persistent disk, model endpoint or paid workspace upgrade is part of this prepared option.

No Render account or service has been created. The owner has since expressed willingness to cover necessary costs, but an exact service/budget and account access have not been selected. Do not infer purchase of this historical example plan. The previously tested local HHEM model is not included: it consumed about 1.67 GB in its isolated trial and did not establish reliable automatic decisions.

## Why the checked free alternatives do not meet this requirement

- [Render Free](https://render.com/docs/free) spins down after 15 minutes.
- [Koyeb Free](https://www.koyeb.com/docs/run-and-scale/scale-to-zero) scales to zero after an hour and cannot disable it on that tier.
- [Hugging Face CPU Basic](https://huggingface.co/docs/hub/en/spaces-gpus#set-a-custom-sleep-time) sleeps after 48 hours; disabling sleep requires paid hardware.
- [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) can reclaim idle compute and has regional capacity constraints.

A pre-existing continuously running server could avoid a new hosting bill, but the owner has confirmed that no such server or paid plan is available. Artificial traffic is not a verified removal of an inactivity policy.

## Deployment acceptance

For the main native hosted site, verify the exact deployed release, HTTPS/WebSockets, first visit, sample, custom project, upload/recovery, cases, saved-answer review, provider/key states, public HTTPS assistant setup/checks, consent, evaluation, calibration, baseline comparison, report redaction, project download/resume, simultaneous visitor isolation and reset. A health page or passing sample is insufficient. Missing approved provider/customer credentials must remain an explicit acceptance limitation, not a reason to hide the online connection flow.

Capacity tests must include the application and extraction subprocess together. A child address-space limit is not a total process-tree memory guarantee. The prior 512 MiB sample container check does not validate custom-upload capacity or adversarial load. Hosted parser concurrency is one; Linux enforces a 512 MiB parser address-space ceiling alongside CPU/wall-time bounds. Start a managed host with sufficient memory for the parent, parser, session databases and evaluation workload, then measure actual usage before admitting a larger cohort.

For browser hosting, verify cross-origin isolation and restricted worker/provider transport on the final origin. If an always-on paid plan is selected later, verify its inactivity policy and capacity. Keep the existing public URL while evaluating alternatives; no URL migration is currently selected.
