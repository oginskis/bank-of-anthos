# StatefulSet worload with HPA

Run command in GCP CloudShell env.

## Prerequisites

Create GKE Autopilot

```bash
REGION=us-central1
gcloud beta container clusters create-auto bank-of-anthos --region="$REGION"
gcloud beta container clusters update bank-of-anthos --disable-managed-prometheus --region="$REGION"
gcloud beta container clusters get-credentials bank-of-anthos --region="$REGION"
```

## Setup Service Accounts with Workload Identity

```bash
GSA_NAME="bank-of-anthos"

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member "serviceAccount:$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/cloudtrace.agent

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member "serviceAccount:$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/monitoring.metricWriter

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member "serviceAccount:$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/monitoring.viewer

kubectl annotate serviceaccount "default" \
    "iam.gke.io/gcp-service-account=$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"

gcloud iam service-accounts add-iam-policy-binding \
    "$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$GOOGLE_CLOUD_PROJECT.svc.id.goog[default/default]"

gcloud iam service-accounts add-iam-policy-binding \
    "$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$GOOGLE_CLOUD_PROJECT.svc.id.goog[custom-metrics/custom-metrics-stackdriver-adapter]"
```

## Deploy Custom Metrics Adapter

```bash
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/k8s-stackdriver/master/custom-metrics-stackdriver-adapter/deploy/production/adapter.yaml

kubectl annotate serviceaccount -n custom-metrics "custom-metrics-stackdriver-adapter" \
    "iam.gke.io/gcp-service-account=$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"
```

Restart custom metrics adapter pod if you see errors related to permissions (403)

## Clone Bank of Anthos

```bash
git clone https://github.com/GoogleCloudPlatform/bank-of-anthos.git
cd bank-of-anthos/
```

## ConfigMap for database init scripts

```bash
kubectl create configmap initdb \
  --from-file=src/accounts-db/initdb/0-accounts-schema.sql \
  --from-file=src/accounts-db/initdb/1-load-testdata.sql
```

## Deploy Postgresql with helm

```bash
helm install accounts-db bitnami/postgresql-ha --values extras/gke-autopilot/helm-postgres-ha/values.yaml
```

## Deploy Bank of Anthos

```bash
kubectl apply -f extras/jwt/jwt-secret.yaml
kubectl apply -f extras/gke-autopilot/kubernetes-manifests
```

## Run loadgenerator

```bash
cd src/loadgenerator
python3 -m venv .venv
source .venv/bin/activate
locust --host="http://$(kubectl get ingress frontend -o=jsonpath='{.status.loadBalancer.ingress[0].ip}')" --loglevel INFO --users="100"
```

Visit <http://localhost:8089> and run load generator.
