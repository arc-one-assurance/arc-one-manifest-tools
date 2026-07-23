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
| **CLI** `arc-one-manifest` | `validate` · `gate` · `register` · `audit` *(v1.2 · reporta a Arc One desde v1.5)* · `generate` *(v1.3)* |
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
arc-one-manifest audit arc-one.agent.yaml --scan-all --report-to-platform   # v1.5
arc-one-manifest generate --repo . --dry-run
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

### Manifest Intelligence

Cierra el loop **código ↔ manifiesto ↔ Arc One**:

- **`audit`** — detecta cuándo el código cambia y el YAML no ([diseño completo](docs/MANIFEST_INTELLIGENCE.md))
- **`generate`** — propone un manifiesto desde cero leyendo el repo

**`--report-to-platform` (v1.5.0)** manda el resultado del audit a Arc One, que triangula
server-side y devuelve las tres comparaciones para el comment del PR:

| Pata | Compara | Lo que te dice |
|---|---|---|
| 1 | código ↔ tu Manifiesto | *"el código hace algo que tu YAML no declara"* |
| 2 | tu Manifiesto ↔ Arc One | *"lo cambiaste y no lo registraste"* |
| 3 | **código ↔ Arc One** | *"lo que Arc One gobierna no es lo que el agente hace"* |

Dos cosas que conviene saber:

- **El alcance viaja honesto.** Con `--scan-all` se reporta `full`; sin él, `diff`. Del lado
  de Arc One ese dato decide si el audit puede **cerrar** diferencias anteriores: un `diff`
  informa lo que ve y no cierra nada. *Lo que no se miró no es lo que dejó de existir.*
- **Si el reporte no se puede entregar, el CLI lo dice fuerte — y el CI sigue.** Arc One
  detecta y avisa, no frena merges. Pero nunca en silencio: el motivo aparece en el log y en
  el comment del PR, porque "todo en orden" y "no pude reportar" no pueden verse igual.

El repositorio se resuelve a su agente por `--agent-id` (o `ARC_ONE_AGENT_ID`) y, si no,
por el `nombre_canonico` del Manifiesto.

---

## Mantenimiento (solo Arc One)

1. Cambios en validación/registro → PR en este repo
2. Release semver (`v1.0.1`, `v1.1.0`, …) + tag
3. Clientes actualizan el pin en sus workflows cuando quieran adoptar

Repo **público** (código legible), **write** restringido al equipo Arc One — mismo modelo que `actions/checkout`.
