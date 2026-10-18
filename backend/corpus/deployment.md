source: https://olake.io/docs/install/kubernetes/
# OLake Kubernetes Deployment

The official Kubernetes guide deploys OLake UI with the OLake Helm chart.
Prerequisites include Kubernetes 1.19 or newer, Helm 3.2.0 or newer, kubectl,
and a StorageClass for persistent volumes.

Add the chart repository with `helm repo add olake
https://datazip-inc.github.io/olake-helm`, then install it with
`helm install olake olake/olake`. The guide describes OLake UI, workers,
PostgreSQL, and Temporal as deployment components. It documents default UI
credentials `admin` / `password`; change them before exposing a deployment.
