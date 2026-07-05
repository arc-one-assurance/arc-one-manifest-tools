# Arc One Manifest Tools

Puente oficial entre el **repositorio del agente** y **Arc One Assurance**.

Los equipos de cliente (p. ej. BBVA) mantienen solo:

- `arc-one.agent.yaml` — contrato del agente (MADRE v1.1)
- Workflows mínimos que llaman a este repo
- Secrets de su workspace (`ARC_ONE_BEARER_TOKEN`, etc.)

Toda la lógica de **validación**, **CI Gate** (drift + semver) y **registro** vive acá — mantenida por el equipo Arc One.

---

## Qué incluye

| Componente | Descripción |
|------------|-------------|
| **CLI** `arc-one-manifest` | `validate` · `gate` · `register` · `audit` *(v1.2)* · `generate` *(v1.3)* |
| **Composite action** `setup@v1.0.0` | Instala el CLI en GitHub Actions |
| **Reusable workflows** | `manifest-pr-preview.yml` · `manifest-register.yml` |

---

## CLI (local)

```bash
pip install git+https://github.com/arc-one-assurance/arc-one-manifest-tools@v1.0.0

export ARC_ONE_API_BASE_URL=https://...
export ARC_ONE_BEARER_TOKEN=arc1_...

arc-one-manifest validate arc-one.agent.yaml
arc-one-manifest audit arc-one.agent.yaml --scan-all --warn-only
arc-one-manifest gate arc-one.agent.yaml
arc-one-manifest register arc-one.agent.yaml --dry-run
```

---

## Integración en repos existentes

Guía compartible (checklist + archivos a agregar): **[CONECTAR_TU_REPO.md](docs/CONECTAR_TU_REPO.md)**

Repo de ejemplo: [arc-one-demo-nova-aws](https://github.com/arc-one-assurance/arc-one-demo-nova-aws)

Workflow de PR (ejemplo mínimo):

```yaml
jobs:
  preview:
    uses: arc-one-assurance/arc-one-manifest-tools/.github/workflows/manifest-pr-preview.yml@v1.0.0
    with:
      connector_resolve_command: |
        ./patch-connector.sh arc-one.agent.yaml arc-one.agent.resolved.yaml
    secrets: inherit
```

**Importante:** fijá siempre un **tag semver** (`@v1.0.0`), no `@main`.

---

## Versionado y evolución del schema

| Capa | Quién controla | Cómo evoluciona |
|------|----------------|-----------------|
| **Contenido** de campos | Cliente (YAML + Centro de control) | PR al manifest |
| **Estructura** MADRE | Arc One (este repo + API) | Nueva versión de tools + migración |
| **Perfil por workspace** (futuro) | Arc One API | Token del workspace → schema dinámico |

Detalle: [`docs/SCHEMA.md`](docs/SCHEMA.md).

### Manifest Intelligence (roadmap)

Capa futura que cierra el loop **código ↔ manifest**:

- **`audit`** — detecta drift cuando el código cambia pero el YAML no ([diseño completo](docs/MANIFEST_INTELLIGENCE.md))
- **`generate`** — propone un manifest desde cero leyendo el repo

Estado: diseño aprobado · Fase 1 (extractores estáticos) pendiente de implementación.

---

## Mantenimiento (solo Arc One)

1. Cambios en validación/registro → PR en este repo
2. Release semver (`v1.0.1`, `v1.1.0`, …) + tag
3. Clientes actualizan el pin en sus workflows cuando quieran adoptar

Repo **público** (código legible), **write** restringido al equipo Arc One — mismo modelo que `actions/checkout`.
