# Conectar tu repo existente a Arc One

Guía para equipos que **ya tienen un repositorio de agente** y quieren mantenerlo sincronizado con Arc One Assurance.

No hace falta crear un repo nuevo ni copiar scripts Python. Solo agregás un manifest, dos workflows cortos y (opcional) un script de infra para resolver la URL del endpoint.

**Motor de validación/registro:** [arc-one-manifest-tools](https://github.com/arc-one-assurance/arc-one-manifest-tools) — lo mantiene Arc One, vos lo consumís con pin semver (`@v1.0.1`).

**Repo de referencia (PoC BBVA):** [arc-one-demo-nova-aws](https://github.com/arc-one-assurance/arc-one-demo-nova-aws)

---

## Resumen en 30 segundos

```
Tu repo (sin cambiar el código del agente)
  + arc-one.agent.yaml          ← contrato con Arc One (exportado del wizard)
  + 2 workflows GitHub          ← ~15 líneas cada uno
  + patch connector (opcional)  ← tu URL de deploy (AWS/GCP/etc.)
  + secrets en GitHub           ← token arc1_… del workspace
        │
        ▼
   PR → validate + gate + dry-run
   merge → nueva versión en Arc One
```

---

## Checklist — qué agregar a un repo existente

| # | Acción | Obligatorio |
|---|--------|-------------|
| 1 | Agregar `arc-one.agent.yaml` en la raíz | Sí |
| 2 | Crear environment `arc-one-registration` + secrets | Sí |
| 3 | Agregar workflow **Manifest PR Preview** | Sí |
| 4 | Agregar workflow **Register with Arc One** | Sí |
| 5 | Script `patch-manifest-connector.sh` (si la URL del endpoint no va fija en el YAML) | Recomendado |
| 6 | Pin `arc-one-manifest-tools@v1.0.1` en ambos workflows | Sí |

**No agregues:** `validate_manifest.py`, `ci_manifest_gate.py`, `register_arc_one_manifest.py`, carpeta `manifests/` con versiones viejas — todo eso vive en `arc-one-manifest-tools`.

---

## Paso 1 — `arc-one.agent.yaml`

Un solo archivo en la raíz del repo. Exportalo desde Arc One (wizard de registro) o copialo del agente ya registrado.

Convenciones:

| Campo | Regla |
|-------|-------|
| `manifest_version` | `"1.1"` (MADRE v1.1) |
| `agent_id` | Lo asigna Arc One en el primer registro; después pegarlo acá para CI Gate |
| `agent_version` | Semver (`1.0.0`, `1.0.1`…) — **obligatorio bump** si cambia contenido material |
| `connector.endpointUrl` | Placeholder en CI, p. ej. `__AWS_SERVICE_URL__/api/v1/chat` |

Qué puede editar el equipo:

- **Sí:** contenido de `system_prompt`, `declared_capabilities`, guardrails, versión, etc.
- **No:** eliminar campos obligatorios (el CI falla con mensaje claro)

Campos obligatorios: ver [SCHEMA.md](./SCHEMA.md) y la validación automática en PR.

---

## Paso 2 — Secrets en GitHub

Creá un **Environment** llamado `arc-one-registration` (Settings → Environments) y agregá:

| Secret | Descripción |
|--------|-------------|
| `ARC_ONE_API_BASE_URL` | URL base de la API Arc One (ej. `https://arc-one-sandbox.web.app`) |
| `ARC_ONE_BEARER_TOKEN` | Token `arc1_…` creado en Arc One → Configuración → API Keys |
| `ARC_ONE_AGENT_ID` | Opcional si `agent_id` ya está en el YAML |
| `ARC_ONE_REGISTRATION_OWNER_USER_ID` | Opcional · UID del owner técnico |
| `AWS_SERVICE_URL` | Base URL de tu deploy **sin path** (solo si usás patch de connector) |

El token debe crearse en el **mismo workspace** donde está el agente. Un token de otro entorno no funciona.

---

## Paso 3 — Script de connector (infra específica)

Si la URL del agente cambia por entorno (ALB, Cloud Run, etc.), no la hardcodees en el YAML. Usá un placeholder y un script mínimo.

**`.github/scripts/patch-manifest-connector.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail
SRC="${1:-arc-one.agent.yaml}"
OUT="${2:-arc-one.agent.resolved.yaml}"
BASE="${AWS_SERVICE_URL:-}"
if [ -z "${BASE}" ]; then
  cp "${SRC}" "${OUT}"
  exit 0
fi
BASE="${BASE%/}"
sed "s|__AWS_SERVICE_URL__/api/v1/chat|${BASE}/api/v1/chat|g" "${SRC}" > "${OUT}"
```

Adaptá el `sed` si tu path de chat no es `/api/v1/chat` o tu placeholder es distinto.

---

## Paso 4 — Workflow: Manifest PR Preview

**`.github/workflows/manifest-pr-preview.yml`:**

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
    uses: arc-one-assurance/arc-one-manifest-tools/.github/workflows/manifest-pr-preview.yml@v1.0.1
    with:
      tools_ref: v1.0.1
      connector_patch_script: .github/scripts/patch-manifest-connector.sh
      arc_one_ui_url: https://arc-one-sandbox.web.app
      workspace_label: tu-workspace-id
    secrets: inherit
```

En cada PR que toque el manifest:

1. Valida estructura MADRE v1.1  
2. Resuelve connector (si configuraste el script)  
3. Compara drift vs Arc One + exige semver bump  
4. Dry-run de registro  
5. Comentario automático en el PR  

---

## Paso 5 — Workflow: Register on merge

**`.github/workflows/register-with-arc-one.yml`:**

```yaml
name: Register with Arc One

on:
  workflow_dispatch:
    inputs:
      dry_run_only:
        description: "Solo validar + gate + dry-run"
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
    uses: arc-one-assurance/arc-one-manifest-tools/.github/workflows/manifest-register.yml@v1.0.1
    with:
      tools_ref: v1.0.1
      connector_patch_script: .github/scripts/patch-manifest-connector.sh
      apply_on_push: ${{ github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && !inputs.dry_run_only) }}
      arc_one_ui_url: https://arc-one-sandbox.web.app
      workspace_label: tu-workspace-id
    secrets: inherit
```

Al mergear a `main`, se publica la nueva versión en Arc One (si hubo drift y semver correcto).

---

## Primera vez vs versiones siguientes

| Situación | Qué pasa |
|-----------|----------|
| **Primer registro** (sin `agent_id` en YAML) | Merge o registro manual vía Arc One wizard; luego pegar `agent_id` en el YAML |
| **Nueva versión** (con `agent_id`) | PR → preview → merge → CI publica versión automáticamente |
| **Sin cambios de contenido** | CI detecta “no drift” y no republica |

---

## Validación local (opcional)

```bash
pip install git+https://github.com/arc-one-assurance/arc-one-manifest-tools@v1.0.1

export ARC_ONE_API_BASE_URL=https://...
export ARC_ONE_BEARER_TOKEN=arc1_...
export AWS_SERVICE_URL=https://tu-alb.ejemplo.com

arc-one-manifest validate arc-one.agent.yaml
chmod +x .github/scripts/patch-manifest-connector.sh
.github/scripts/patch-manifest-connector.sh arc-one.agent.yaml arc-one.agent.resolved.yaml
arc-one-manifest validate arc-one.agent.resolved.yaml --no-placeholder
arc-one-manifest gate arc-one.agent.resolved.yaml
arc-one-manifest register arc-one.agent.resolved.yaml --dry-run
```

---

## Actualizar versión de tools

Cuando Arc One publique una nueva versión (ej. `v1.0.2`):

1. Cambiá `@v1.0.1` → `@v1.0.2` en ambos workflows  
2. Cambiá `tools_ref: v1.0.1` → `v1.0.2`  
3. Abrí PR de prueba  

**No uses `@main` en producción.**

Si cambia la **estructura** del manifest (nueva MADRE), Arc One publicará una guía de migración — ver [SCHEMA.md](./SCHEMA.md).

---

## Preguntas frecuentes

**¿Tengo que mover mi código del agente?**  
No. El manifest es un archivo aparte; tu app sigue igual.

**¿Puedo tener varios agentes en un monorepo?**  
Hoy: un `arc-one.agent.yaml` por repo (bulk multi-agente es roadmap).

**¿Qué pasa si borro un campo del YAML?**  
El PR falla en `validate` con el path del campo faltante.

**¿Quién controla la estructura del manifest?**  
Arc One (via `arc-one-manifest-tools` + API). El cliente edita **contenido**, no el schema.

**¿PR desde fork?**  
Solo validación estructural; dry-run completo requiere PR desde rama del mismo repo (secrets).

---

## Soporte

- Issues en [arc-one-manifest-tools](https://github.com/arc-one-assurance/arc-one-manifest-tools/issues)
- Ejemplo vivo: [arc-one-demo-nova-aws](https://github.com/arc-one-assurance/arc-one-demo-nova-aws)
