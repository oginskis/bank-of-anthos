# StatefulSet worload with HPA

Run command in GCP CloudShell env.

## Prerequisites

Create GKE Autopilot. Change `REGION` or `GKE_NAME` to your values if you like.

```bash
REGION="us-central1"
GKE_NAME="bank-of-anthos"
gcloud beta container clusters create-auto "$GKE_NAME" --region="$REGION"
gcloud beta container clusters update "$GKE_NAME" --disable-managed-prometheus --region="$REGION"
```

Execution of these commands take some time.

If needed obtain access to GKE

```bash
gcloud beta container clusters get-credentials "$GKE_NAME" --region="$REGION"
```

## Setup Service Accounts with Workload Identity

```bash
GSA_NAME="bank-of-anthos"

gcloud iam service-accounts create "$GSA_NAME"

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member "serviceAccount:$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/cloudtrace.agent

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member "serviceAccount:$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/monitoring.metricWriter

gcloud iam service-accounts add-iam-policy-binding \
    "$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$GOOGLE_CLOUD_PROJECT.svc.id.goog[default/default]"

kubectl annotate serviceaccount "default" \
    "iam.gke.io/gcp-service-account=$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com"
```

## Deploy Custom Metrics Adapter

Use legacy model because of `prometheus-to-sd` tool used in postgresql helm chart configuration.

```bash
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member "serviceAccount:$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/monitoring.viewer

gcloud iam service-accounts add-iam-policy-binding \
    "$GSA_NAME@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$GOOGLE_CLOUD_PROJECT.svc.id.goog[custom-metrics/custom-metrics-stackdriver-adapter]"

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
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install accounts-db bitnami/postgresql-ha --values extras/gke-autopilot/helm-postgres-ha/values.yaml
```

## Deploy PGPool operator

```bash
kubectl create configmap pgpool-operator-script --from-file=extras/gke-autopilot/helm-postgres-ha/pgpool-operator/pgpool.py
kubectl apply -f extras/gke-autopilot/helm-postgres-ha/pgpool-operator/pgpool-operator.yaml
```

## Deploy Bank of Anthos

```bash
kubectl apply -f extras/jwt/jwt-secret.yaml
kubectl apply -f extras/gke-autopilot/kubernetes-manifests
```

## Configure Frontedn HPA resource

Wait while Bank of Anothos spinup.

Discover an exact name of frontend’s ingress LoadBalancer using the following command:

```bash
gcloud compute forwarding-rules list --filter='name~^.*default-frontend.*$' --format='value(name)'
```

Edit `extras/gke-autopilot/hpa/frontend.yaml` and replace `<default-frontend>` to result of previous command

## Apply HPA

```bash
kubectl apply -f extras/gke-autopilot/hpa
```

## Run loadgenerator

Wait when application will be available on IP address of load balancer and start this process.

```bash
kubectl get ingress frontend -o=jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

Edit `extras/gke-autopilot/loadgenerator.yaml` and replace `<frontend-ip-address>` to result of previous command

Apply kubernetes deployment manifest

```bash
kubectl apply -f extras/gke-autopilot/loadgenerator.yaml
```

Observe logs of loadgenerator pod.

Or manually

```bash
cd src/loadgenerator
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
locust --host "http://$(kubectl get ingress frontend -o=jsonpath='{.status.loadBalancer.ingress[0].ip}')" --loglevel INFO --users "250" --spawn-rate "5"
```

Visit <http://localhost:8089> and run load generator.

## Clean up

```bash
kubectl delete -f extras/gke-autopilot/loadgenerator.yaml
kubectl delete -f extras/gke-autopilot/hpa
kubectl delete -f extras/gke-autopilot/kubernetes-manifests
kubectl delete -f extras/gke-autopilot/helm-postgres-ha/pgpool-operator/pgpool-operator.yaml
helm uninstall accounts-db
kubectl delete pvc --selector="app.kubernetes.io/instance=accounts-db"
kubectl delete -f https://raw.githubusercontent.com/GoogleCloudPlatform/k8s-stackdriver/master/custom-metrics-stackdriver-adapter/deploy/production/adapter.yaml
gcloud beta container clusters delete "$GKE_NAME" --region="$REGION"

# Optional
gcloud iam service-accounts delete "$GSA_NAME"
```
