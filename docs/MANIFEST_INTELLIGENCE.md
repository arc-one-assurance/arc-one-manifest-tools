# Manifest Intelligence — EPIC de diseño

> **Estado:** diseño aprobado · implementación pendiente  
> **Versión objetivo del paquete:** `v1.2.0` (audit) → `v1.3.0` (bootstrap)  
> **Tagline:** *Tu código ya sabe a qué se conecta. Ahora el manifest también.*

---

## 1. Problema

Hoy `arc-one-manifest-tools` responde una pregunta:

> ¿Este YAML es **válido** y **coincide** con lo registrado en Arc One?

Eso deja un hueco crítico:

| Situación | Qué pasa hoy |
|-----------|--------------|
| Cambiás `arc-one.agent.yaml` sin bump semver | ❌ Gate falla |
| Cambiás el **código** (nuevo datastore, MCP, endpoint) sin tocar el manifest | ✅ CI verde — **drift silencioso** |
| Arrancás un repo agente desde cero | Manifest a mano o wizard en UI — **alto friction** |

El manifest debería ser el **contrato declarativo** del agente. Si el código evoluciona y el contrato no, Arc One pierde trazabilidad de assurance.

---

## 2. Visión

Agregar una capa **Manifest Intelligence** encima del pipeline existente:

```
Repo del agente
      │
      ├─► [NUEVO] audit     — código ↔ manifest (drift guard)
      ├─► [NUEVO] generate  — repo → manifest propuesto (bootstrap)
      │
      ▼
 validate ──► gate ──► register   (sin cambios de contrato)
```

Dos capacidades nuevas, un solo principio: **evidencia estructurada + juicio LLM acotado**, nunca magia opaca.

---

## 3. Feature A — `audit` (Manifest Drift Guard)

### 3.1 Objetivo

En cada PR (o push), detectar si los cambios de **código** implican cambios **materiales** en el manifest que no ocurrieron.

**Ejemplo:**

```python
# src/storage.py — NUEVO en el PR
client = boto3.client("dynamodb", region_name="eu-west-1")
```

Si `arc-one.agent.yaml` no agrega `dynamodb` bajo `data_stores` (o `integration_endpoints`) → **alerta con evidencia**.

### 3.2 Arquitectura (3 capas)

```
┌─────────────────────────────────────────────────────────────┐
│  Capa 0 — Scope                                             │
│  git diff base..head · filtrar paths relevantes             │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Capa 1 — Extractores estáticos ($0)                        │
│  AST · regex · parsers de config · env example              │
│  → CodeSignal[]                                             │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Capa 2 — LLM Judge (solo si hay señales)                  │
│  señales + manifest actual + MATERIAL_PATHS + diff resumido │
│  → AuditFinding[]                                           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Capa 3 — Reporter                                          │
│  stdout JSON · exit code · PR comment · suggested YAML patch│
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Scope de archivos (Capa 0)

Paths por defecto (configurables vía `--include` / `.arc-one-audit.yaml`):

| Glob | Por qué |
|------|---------|
| `src/**`, `app/**`, `lib/**`, `services/**` | Código del agente |
| `infra/**`, `terraform/**`, `cdk/**`, `serverless.yml` | Despliegue y recursos |
| `requirements*.txt`, `pyproject.toml`, `package.json`, `Pipfile` | Stack y deps |
| `Dockerfile`, `docker-compose*.yml` | Runtime |
| `.env.example`, `config/**`, `*.config.*` | Endpoints, secrets, stores |
| `prompts/**`, `*prompt*`, `system*.md` | Comportamiento |
| `arc-one.agent.yaml` | Manifest (siempre incluido) |

**Excluidos:** `tests/**`, `node_modules/**`, `.venv/**`, `dist/**`, lockfiles binarios.

Trigger de CI ampliado (futuro en agent repos):

```yaml
on:
  pull_request:
    paths:
      - 'arc-one.agent.yaml'
      - 'src/**'
      - 'infra/**'
      - 'requirements*.txt'
      - 'pyproject.toml'
      - 'Dockerfile'
```

### 3.4 Extractores estáticos (Capa 1)

Módulo propuesto: `arc_one_manifest/intelligence/extractors/`

| Extractor | Señales | Evidencia |
|-----------|---------|-----------|
| `python_deps.py` | `openai`, `anthropic`, `boto3`, `pinecone`, … | `requirements.txt:12` |
| `python_ast.py` | `boto3.client("dynamodb")`, `httpx.post(url)`, env reads | `src/foo.py:42` |
| `js_ts.py` | `@aws-sdk/*`, fetch URLs, process.env | `src/agent.ts:88` |
| `infra.py` | RDS, S3, Lambda, ECS, Secrets Manager ARNs | `infra/main.tf:120` |
| `env_example.py` | `DATABASE_URL`, `OPENAI_API_KEY`, MCP URLs | `.env.example:5` |
| `prompt_files.py` | archivos con contenido de system prompt | `prompts/system.md` |
| `mcp_config.py` | servidores MCP en JSON/YAML de config | `mcp.json:servers.core-banking` |

**Tipo `CodeSignal`:**

```python
@dataclass
class CodeSignal:
    kind: str           # e.g. "data_store", "integration_endpoint", "mcp_server", "secret", "model_hint"
    inferred_id: str    # slug canónico o raw (ej. "dynamodb", "core-banking-mcp")
    confidence: float   # 0.0–1.0 heurístico del extractor
    evidence: Evidence  # file, line_start, line_end, snippet
    manifest_section: str  # sugerencia: "data_stores" | "mcp_servers" | ...
```

### 3.5 Alineación con `_MATERIAL_PATHS`

El gate actual (`arc_one_manifest/gate.py`) ya define campos materiales:

```python
_MATERIAL_PATHS = frozenset({
    "system_prompt", "declared_capabilities", "required_guardrails",
    "agent_skills", "agent_model", "autonomy_level",
    "integration_endpoints", "data_stores", "secrets_required",
    "knowledge_bases", "agent_dependencies", "mcp_servers",
    "purpose", "regulated_context", "network_exposure", "connector",
})
```

El judge mapea cada `CodeSignal` → una o más rutas en este set. Si el manifest no refleja la señal → finding `MANIFEST_STALE`.

### 3.6 LLM Judge (Capa 2)

**Entrada al judge** (JSON, no repo completo):

```json
{
  "manifest_path": "arc-one.agent.yaml",
  "manifest_summary": {
    "data_stores": ["postgres-core", "redis-cache"],
    "mcp_servers": [],
    "integration_endpoints": ["stripe-api"],
    "agent_model": "anthropic/claude-sonnet-4-7"
  },
  "code_signals": [
    {
      "kind": "data_store",
      "inferred_id": "dynamodb",
      "confidence": 0.92,
      "evidence": {"file": "src/storage.py", "line": 42, "snippet": "boto3.client('dynamodb')"}
    }
  ],
  "manifest_changed_in_pr": false,
  "material_paths": ["data_stores", "mcp_servers", "..."]
}
```

**Salida del judge (`AuditReport`):**

```json
{
  "findings": [
    {
      "code": "MANIFEST_STALE",
      "severity": "high",
      "confidence": 0.88,
      "title": "Nuevo datastore DynamoDB no declarado",
      "detail": "El PR introduce uso de DynamoDB pero data_stores no incluye dynamodb.",
      "manifest_section": "data_stores",
      "suggested_catalog_id": "dynamodb",
      "evidence": [{"file": "src/storage.py", "line": 42}],
      "suggested_patch": {
        "op": "add",
        "path": "data_stores",
        "value": {"id": "dynamodb", "relation_types": ["READ", "WRITE"]}
      }
    }
  ],
  "clean": false,
  "judge_model": "claude-sonnet-4-20250514",
  "tokens_used": 1840
}
```

**Códigos de finding:**

| Código | Significado |
|--------|-------------|
| `MANIFEST_STALE` | Código cambió; manifest debería haber cambiado y no lo hizo |
| `MANIFEST_OVER_DECLARED` | Manifest declara recurso que el código ya no usa (fase 2) |
| `MANIFEST_MISMATCH` | Manifest cambió pero de forma inconsistente con el código |
| `UNCERTAIN` | Señal ambigua — requiere revisión humana, no falla gate |
| `CATALOG_UNKNOWN` | Recurso detectado pero sin ID en catálogo Arc One conocido |

**Reglas del judge (system prompt, resumen):**

1. Solo emitir `MANIFEST_STALE` con confidence ≥ 0.7 si hay evidencia directa.
2. Proponer IDs solo del catálogo embebido o marcar `CATALOG_UNKNOWN`.
3. Nunca inventar owners, regulatory context ni purpose — esos son humanos.
4. Preferir `UNCERTAIN` ante duda.

**Modo sin LLM:** `--static-only` usa heurística: si `inferred_id` no aparece en manifest summary y confidence ≥ 0.85 → finding automático.

### 3.7 CLI — `audit`

```bash
# Local / CI
arc-one-manifest audit arc-one.agent.yaml \
  --base origin/main \
  --repo . \
  --format json \
  --output audit-report.json

# Solo extractores (sin API key)
arc-one-manifest audit arc-one.agent.yaml --static-only

# Modo estricto (falla CI)
arc-one-manifest audit arc-one.agent.yaml --fail-on finding:MANIFEST_STALE

# Modo permisivo (default en v1.2)
arc-one-manifest audit arc-one.agent.yaml --warn-only
```

| Flag | Default | Descripción |
|------|---------|-------------|
| `--base` | `origin/main` | Ref git para diff |
| `--repo` | `.` | Raíz del repo |
| `--static-only` | false | Sin LLM |
| `--warn-only` | true | Exit 0 con findings (comentario en PR) |
| `--fail-on` | — | Códigos que hacen exit 1 |
| `--min-confidence` | 0.7 | Umbral para findings |
| `--include` / `--exclude` | ver §3.3 | Override de scope |
| `--llm-provider` | `anthropic` | Proveedor del judge |
| `--llm-model` | env | Modelo (ej. `claude-sonnet-4-20250514`) |

**Variables de entorno:**

| Var | Uso |
|-----|-----|
| `ARC_ONE_LLM_API_KEY` | API key para judge (opcional si `--static-only`) |
| `ARC_ONE_CATALOG_URL` | Futuro: catálogo dinámico del workspace |

**Exit codes:**

| Code | Significado |
|------|-------------|
| 0 | Sin findings bloqueantes (o `--warn-only`) |
| 1 | Findings que matchean `--fail-on` |
| 2 | Error de configuración / git / LLM |

### 3.8 Integración CI

Nuevo step en `manifest-pr-preview.yml` (después de checkout, **antes** de validate):

```yaml
- name: Manifest Intelligence — audit código ↔ manifest
  env:
    ARC_ONE_LLM_API_KEY: ${{ secrets.ARC_ONE_LLM_API_KEY }}
  run: |
    arc-one-manifest audit "${{ inputs.manifest_path }}" \
      --base "origin/${{ github.base_ref }}" \
      --format json \
      --output audit-report.json \
      --warn-only
    # v1.3+: --fail-on MANIFEST_STALE con opt-in del repo

- name: Comentario drift en PR
  if: github.event_name == 'pull_request' && always()
  uses: actions/github-script@v7
  with:
    script: |
      // Render audit-report.json → markdown con findings + suggested patches
```

Comentario de PR (ejemplo):

```markdown
## ⚠️ Manifest Drift Guard

| Severidad | Finding | Evidencia |
|-----------|---------|-----------|
| 🔴 high | Nuevo DynamoDB no en `data_stores` | `src/storage.py:42` |

**Sugerencia:** agregar bajo `data_stores`:
```yaml
- id: dynamodb
  relation_types: [READ, WRITE]
```

[Ver reporte completo](link-to-artifact)
```

---

## 4. Feature B — `generate` (Manifest Bootstrap)

### 4.1 Objetivo

Generar un `arc-one.agent.yaml` **propuesto** leyendo el repo, para repos nuevos o legacy sin manifest.

```bash
arc-one-manifest generate --repo . --output arc-one.agent.yaml --dry-run
```

**No registra en Arc One.** Siempre pasa por `validate` + revisión humana.

### 4.2 Pipeline

```
Repo scan
    ├── StackProfile      → agent_model, framework, deployment_target
    ├── ContextProfile    → integration_endpoints, data_stores, secrets, mcp_servers
    ├── BehaviorProfile   → system_prompt, capabilities, guardrails, skills
    └── IdentityProfile   → purpose, target_users, regulated_context (parcial)
              │
              ▼
    LLM Synthesizer (narrativa + mapeo a catálogo)
              │
              ▼
    MADRE v1.2 Template + TODO markers
              │
              ▼
    validate_madre_manifest()  ← reusa validador existente
              │
              ▼
    arc-one.agent.yaml + generation-report.json
```

### 4.3 Profiles por stack (v1.3)

Empezar con un profile; extender después.

| Profile ID | Detectado por | Repo referencia |
|------------|---------------|-----------------|
| `python-aws-ecs` | `Dockerfile` + `boto3` + ECS en infra | `arc-one-demo-nova-aws` |
| `python-fastapi-local` | `fastapi` + sin cloud infra | futuro |
| `node-lambda` | `serverless.yml` / `@aws-sdk` | futuro |
| `generic` | fallback mínimo | cualquier repo |

Archivo: `arc_one_manifest/intelligence/profiles/python_aws_ecs.yaml`

### 4.4 Output honesto

El YAML generado incluye header:

```yaml
# GENERATED by arc-one-manifest generate · 2026-07-05
# Confidence: 72% · Revisar campos marcados TODO antes de registrar
# Report: manifest-generation-report.json

manifest_version: "1.2"
name: TODO  # inferido del README o nombre del repo
agent_version: "0.1.0"  # bootstrap semver — bump en primer registro real
...
technical_owner: TODO  # no encontrado en repo
```

**Sidecar `manifest-generation-report.json`:**

```json
{
  "generated_at": "2026-07-05T12:00:00Z",
  "profile": "python-aws-ecs",
  "confidence": 0.72,
  "fields": {
    "agent_model": {"value": "anthropic/claude-sonnet-4-7", "confidence": 0.9, "evidence": "requirements.txt"},
    "technical_owner": {"value": null, "confidence": 0, "status": "TODO"}
  },
  "validation": {"ok": false, "errors": ["technical_owner: required"]}
}
```

Campos con `TODO` obligan revisión antes de `register`.

### 4.5 CLI — `generate`

```bash
arc-one-manifest generate \
  --repo . \
  --output arc-one.agent.yaml \
  --report generation-report.json \
  --profile auto \
  --dry-run

# Interactivo (futuro v1.4)
arc-one-manifest generate --repo . --interactive
```

| Flag | Default | Descripción |
|------|---------|-------------|
| `--repo` | `.` | Raíz del repo |
| `--output` | `arc-one.agent.yaml` | Path de salida |
| `--report` | `manifest-generation-report.json` | Sidecar de confianza |
| `--profile` | `auto` | Profile de stack |
| `--dry-run` | false | Escribe a stdout, no archivos |
| `--skip-llm` | false | Solo template + extractores (campos mínimos) |

### 4.6 Catálogo embebido

Para mapear señales → IDs Arc One (`active-directory-azure-ad`, `anthropic/claude-sonnet-4-7`):

- **v1.3:** JSON embebido en tools, sincronizado manualmente desde sandbox (`manifest_v2_catalogs.py`)
- **Futuro:** `GET /api/workspace/manifest-catalog` con token del workspace

Módulo: `arc_one_manifest/intelligence/catalog.py`

---

## 5. Estructura de paquete (propuesta)

```
arc_one_manifest/
├── cli.py                    ← + audit, generate
├── gate.py                   ← sin cambios (reusa _MATERIAL_PATHS exportado)
├── register.py
├── validation/
│   └── madre_v11.py
└── intelligence/             ← NUEVO
    ├── __init__.py
    ├── audit.py              ← orquestador audit
    ├── generate.py           ← orquestador bootstrap
    ├── git_diff.py           ← Capa 0
    ├── judge.py              ← Capa 2 LLM
    ├── catalog.py            ← IDs canónicos
    ├── models.py             ← CodeSignal, AuditFinding, GenerationReport
    ├── reporter.py           ← stdout, JSON, markdown PR comment
    ├── extractors/
    │   ├── __init__.py
    │   ├── python_ast.py
    │   ├── python_deps.py
    │   ├── env_example.py
    │   ├── infra.py
    │   ├── mcp_config.py
    │   └── prompt_files.py
    ├── profiles/
    │   ├── python_aws_ecs.yaml
    │   └── generic.yaml
    └── templates/
        └── madre_v12_bootstrap.yaml.j2
```

**Dependencias nuevas (pyproject.toml):**

| Dep | Uso | Fase |
|-----|-----|------|
| `anthropic` o `httpx` | LLM judge | 1.2 |
| (opcional) `tree-sitter` | AST más robusto | 1.3 |

Mantener el paquete liviano: LLM es opt-in vía env var.

---

## 6. Roadmap de implementación

### Fase 1 — Fundación estática (`v1.2.0-alpha`)

**Objetivo:** `audit --static-only` funcional, sin LLM.

| Task | Entregable |
|------|------------|
| M1.1 | `intelligence/models.py` — tipos CodeSignal, AuditFinding |
| M1.2 | `git_diff.py` — diff scoped |
| M1.3 | Extractores Python deps + env example |
| M1.4 | Extractor Python AST (boto3, httpx, os.environ) |
| M1.5 | `audit.py` — orquestador static-only |
| M1.6 | CLI `audit` + tests con fixtures |
| M1.7 | Exportar `_MATERIAL_PATHS` desde gate (o shared constants) |

**Criterio de done:** contra `arc-one-demo-nova-aws`, agregar `boto3.client("dynamodb")` en un branch de prueba → `audit --static-only` emite finding.

### Fase 2 — LLM Judge + CI (`v1.2.0`)

| Task | Entregable |
|------|------------|
| M2.1 | `judge.py` + prompts versionados |
| M2.2 | `catalog.py` embebido (top 50 assets/models MCP) |
| M2.3 | `reporter.py` — markdown para PR |
| M2.4 | Step en `manifest-pr-preview.yml` |
| M2.5 | Doc + secret `ARC_ONE_LLM_API_KEY` en INTEGRATION.md |
| M2.6 | Tests con judge mockeado |

**Criterio de done:** PR en demo-nova-aws con drift → comentario automático en GitHub.

### Fase 3 — Bootstrap (`v1.3.0`)

| Task | Entregable |
|------|------------|
| M3.1 | Profile `python-aws-ecs` |
| M3.2 | `generate.py` + template Jinja |
| M3.3 | CLI `generate` |
| M3.4 | `generation-report.json` sidecar |
| M3.5 | Guía "Primer manifest en 5 minutos" en CONECTAR_TU_REPO.md |
| M3.6 | E2E: repo sin manifest → generate → validate (con TODOs) → humano completa → register |

### Fase 4 — Pulido enterprise (`v1.4.0`)

| Task | Entregable |
|------|------------|
| M4.1 | `MANIFEST_OVER_DECLARED` (manifest declara más de lo que usa el código) |
| M4.2 | `.arc-one-audit.yaml` config por repo |
| M4.3 | `--fail-on` opt-in en workflows |
| M4.4 | Catálogo dinámico desde API Arc One |
| M4.5 | Profile `node-lambda` |
| M4.6 | `generate --interactive` (TUI mínimo) |

---

## 7. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Falsos positivos en CI | Fatiga del dev | `--warn-only` default; `--min-confidence`; allowlist en `.arc-one-audit.yaml` |
| LLM alucina IDs | Manifest inválido | Catálogo embebido; `CATALOG_UNKNOWN` si no hay match |
| Costo LLM por PR | Presupuesto | Capa estática filtra; judge solo si signals > 0 |
| Divergencia schema | Register falla | Siempre `validate` post-generate; sync con sandbox |
| Repos monorepo | Ruido | `--repo-subpath apps/agent/` |
| Secret en snippet | Leak en PR comment | Redactar env values en reporter |

---

## 8. Métricas de éxito

| Métrica | Target (6 meses post-launch) |
|---------|------------------------------|
| PRs con drift detectado antes de merge | > 80% de casos reales en PoC |
| Falsos positivos `--static-only` | < 15% |
| Tiempo a primer manifest (bootstrap) | < 30 min (vs horas hoy) |
| Adopción en repos cliente | ≥ 2 bancos en audit warn-only |

---

## 9. Relación con Arc One Assurance

```
Código del agente ──audit──► Manifest (YAML) ──gate──► Arc One registry
                                    │                        │
                                    │                        ▼
                                    │              Risk Surface · Assurance
                                    │                        │
                                    └──── generate ◄─────────┘
                                         (bootstrap / re-sync)
```

Manifest Intelligence **no reemplaza** assurance en Obsydian/Arc One. Cierra el loop **declaración → registro** para que assurance evalúe un contrato que refleje la realidad del código.

---

## 10. Referencias internas

| Recurso | Path |
|---------|------|
| Gate + material paths | `arc_one_manifest/gate.py` |
| Validación MADRE | `arc_one_manifest/validation/madre_v11.py` |
| Registro API | `arc_one_manifest/register.py` |
| Workflow PR | `.github/workflows/manifest-pr-preview.yml` |
| Template canónico | `arc-one-sandbox/.../manifest-template.arc-one.agent.yaml` |
| Catálogos API | `arc-one-sandbox/.../manifest_v2_catalogs.py` |
| Export YAML (inverso) | `arc-one-sandbox/.../manifest_export.py` |
| Demo agent repo | `arc-one-demo-nova-aws/arc-one.agent.yaml` |

---

## 11. Decisiones abiertas (para cerrar en implementación)

1. **¿Judge en CI obligatorio o opt-in por repo?** → Propuesta: opt-in warn-only en v1.2, fail-on en v1.4.
2. **¿Qué LLM por defecto?** → Anthropic (alineado con stack Arc One); abstraction para OpenAI/Azure.
3. **¿Versionar prompts del judge en repo?** → Sí, `intelligence/prompts/audit_judge_v1.txt`.
4. **¿Publicar catálogo como artifact separado?** → Embebido en v1.2; API fetch en v1.4.

---

## 12. Próximo paso inmediato

Abrir branch `feat/manifest-intelligence-m1` e implementar **Fase 1** (M1.1–M1.7):

1. Scaffolding `intelligence/`
2. `audit --static-only` contra demo-nova-aws
3. Test: drift DynamoDB simulado → finding esperado

Cuando Fase 1 esté verde → release `v1.2.0-alpha` para dogfooding interno.
