# Integración — repo de agente + Arc One

Guía para equipos que mantienen un agente bajo assurance (como BBVA PoC).

---

## Qué va en el repo del agente

```
mi-agente/
├── arc-one.agent.yaml              ← único archivo de contrato con Arc One
├── .github/
│   ├── workflows/
│   │   ├── manifest-pr-preview.yml   ← ~15 líneas
│   │   └── register-with-arc-one.yml ← ~20 líneas
│   └── scripts/
│       └── patch-manifest-connector.sh  ← específico de tu infra (URL del endpoint)
└── docs/
    └── GUIA.md                       ← cómo editar el manifest
```

**No copies** `validate_manifest.py`, `ci_manifest_gate.py` ni `register_arc_one_manifest.py` — usá el paquete de este repo.

---

## Secrets (GitHub Environment recomendado)

| Secret | Uso |
|--------|-----|
| `ARC_ONE_API_BASE_URL` | URL de la API Arc One |
| `ARC_ONE_BEARER_TOKEN` | Token `arc1_…` del workspace |
| `ARC_ONE_AGENT_ID` | Opcional si `agent_id` está en el YAML |
| `ARC_ONE_REGISTRATION_OWNER_USER_ID` | User id interno para owners |
| `AWS_SERVICE_URL` (o equivalente) | Base URL para resolver `connector` en CI |

---

## Workflow: Manifest PR Preview

```yaml
name: Manifest PR Preview

on:
  pull_request:
    branches: [main]
    paths: [arc-one.agent.yaml]

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: manifest-pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  preview:
    uses: arc-one-assurance/arc-one-manifest-tools/.github/workflows/manifest-pr-preview.yml@v1.0.0
    with:
      tools_ref: v1.0.0
      connector_resolve_command: |
        chmod +x .github/scripts/patch-manifest-connector.sh
        AWS_SERVICE_URL="${{ secrets.AWS_SERVICE_URL }}" \
          .github/scripts/patch-manifest-connector.sh \
          arc-one.agent.yaml arc-one.agent.resolved.yaml
      arc_one_ui_url: https://arc-one-sandbox.web.app
      workspace_label: ws_bbva_poc
    secrets: inherit
```

Flujo automático en cada PR:

1. **validate** — campos obligatorios MADRE v1.1
2. **patch connector** — tu script (infra específica)
3. **validate** — connector con URL real
4. **gate** — drift vs Arc One + semver bump
5. **register --dry-run** — preview API
6. Comentario en el PR

---

## Workflow: Register on merge

```yaml
name: Register with Arc One

on:
  workflow_dispatch:
    inputs:
      dry_run_only:
        type: boolean
        default: false
  push:
    branches: [main]
    paths: [arc-one.agent.yaml]

concurrency:
  group: register-arc-one-main
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  register:
    uses: arc-one-assurance/arc-one-manifest-tools/.github/workflows/manifest-register.yml@v1.0.0
    with:
      tools_ref: v1.0.0
      connector_resolve_command: |
        chmod +x .github/scripts/patch-manifest-connector.sh
        AWS_SERVICE_URL="${{ secrets.AWS_SERVICE_URL }}" \
          .github/scripts/patch-manifest-connector.sh \
          arc-one.agent.yaml arc-one.agent.resolved.yaml
      apply_on_push: ${{ github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && !inputs.dry_run_only) }}
      workspace_label: ws_bbva_poc
    secrets: inherit
```

---

## Validación local (antes del PR)

```bash
pip install git+https://github.com/arc-one-assurance/arc-one-manifest-tools@v1.0.0
source .env.ci.local   # ARC_ONE_* y AWS_SERVICE_URL

arc-one-manifest validate arc-one.agent.yaml
arc-one-manifest gate arc-one.agent.resolved.yaml
arc-one-manifest register arc-one.agent.resolved.yaml --dry-run
```

---

## Actualizar versión de tools

Cuando Arc One publique `v1.0.1` o `v1.1.0`:

1. Cambiá `@v1.0.0` → `@v1.0.1` en ambos workflows
2. Cambiá `tools_ref: v1.0.0` → `v1.0.1`
3. Abrí PR, verificá que CI pasa

No uses `@main` en producción — siempre pin semver.

---

## Referencia

Repo de ejemplo (PoC BBVA): [arc-one-demo-nova-aws](https://github.com/arc-one-assurance/arc-one-demo-nova-aws)
