# Kubernetes

Manifests for running the whole stack on a cluster (kind/minikube for local tests).

```bash
docker build -t financasia:latest ..                      # Python app
docker build -t financasia-alerts:latest ../alerts-service # Java service
kind load docker-image financasia:latest financasia-alerts:latest   # if using kind
kubectl apply -k .
kubectl -n financasia port-forward svc/financasia-app 8000:80
```

`config.yaml` contains a **template** Secret with placeholder values; create the real one with
`kubectl create secret` (command in the file) instead of committing keys.

| Object | Why |
|---|---|
| `financasia-app` Deployment, 1 replica, `Recreate` | SQLite on a ReadWriteOnce volume: never two writers |
| `alerts-service` Deployment, 2 replicas | stateless consumer; RabbitMQ splits the queue between replicas |
| readiness/liveness probes | Spring Boot Actuator `/actuator/health/{readiness,liveness}`, FastAPI `/api/health` |
| ConfigMap + Secret via `envFrom` | config outside the image (12-factor) |
| RabbitMQ/MongoDB StatefulSets | dev only; use managed services/operators in production |

CI validates these files against the Kubernetes schemas with `kubeconform`.
