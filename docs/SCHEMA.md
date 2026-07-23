# Evolución del schema del manifest

## `infra_binding` — dónde opera el agente (v1.3)

Bloque **opcional**, **top-level**, junto a `deployment_target`. Declara en qué cuenta de
nube vive el agente y cuáles de los recursos de esa cuenta son suyos.

> Declarar la infraestructura vinculada **no cambia la criticidad del agente**: cambia la
> precisión con la que Arc One valida lo declarado contra lo que realmente existe en tu
> nube (sin el bloque, los recursos se identifican por similitud de nombre).

```yaml
manifest_version: "1.3"
deployment_target: cloud-run/google   # en qué plataforma corre

infra_binding:                        # opcional · dónde vive y qué es suyo
  - account: acme-prod                # projectId (GCP) / accountId (AWS)
    scope:
      resource_prefixes: [nova-]
      regions: [europe-west1]
      labels: { app: nova }           # se acepta, todavía NO recorta (ver abajo)
```

Si la cuenta es **dedicada** al agente (un proyecto exclusivo, el caso de Nova), el
scope se declara entero de una:

```yaml
infra_binding:
  - account: acme-nova-prod
    scope:
      all: true                       # la cuenta entera es de este agente
```

**Reglas:**

- **`all: true` es excluyente con el recorte.** "La cuenta es dedicada pero sólo estos
  prefijos" es contradictorio: se rechaza combinar `all` con `resource_prefixes`,
  `regions` o `labels`. `all: false` también se rechaza (no significa nada — omitilo).

- **Nunca lleva credenciales.** El `account` es una coordenada, no un secreto — la
  credencial de la nube se carga una sola vez en Arc One, por cuenta y por workspace.
  Es lo que hace que este bloque sea seguro de commitear al repo.
- **El proveedor no se declara, se deriva** de la cuenta conectada en Arc One.
- **`scope` es obligatorio** en cada binding: `all: true` (cuenta dedicada) o al menos
  `resource_prefixes` o `regions`. Un scope de solo `labels` se rechaza: los escaneos
  todavía no traen etiquetas, así que no recortaría nada — declaración muerta
  silenciosa, jamás.
- **Una nube por agente.** El bloque es una lista, pero hoy se declara **un solo
  binding**: el de la cuenta donde corre el agente, la de su `deployment_target` (que el
  wizard también declara de a uno). Declarar dos cuentas se **rechaza** en la validación
  — Arc One analizaría una sola y el cliente creería que mira las dos. Si el agente usa
  varios grupos de recursos de esa cuenta, van todos en el mismo `scope`. El día que
  Arc One soporte multi-nube por agente, la lista ya está lista para recibirlo y no hay
  que migrar ningún archivo.
- **Efecto sobre el bump de versión** (lo que sugiere `gate`): cambiar de plataforma
  (`deployment_target`) o de `account` → **minor** (otra credencial, otra frontera de
  seguridad). Reacomodar el `scope` dentro de la misma cuenta → **patch**.
- 🔴 **Un `account` de AWS son 12 dígitos: escribilo ENTRE COMILLAS.** Sin comillas,
  YAML lo lee como número. El CLI lo normaliza igual que Arc One antes de comparar, así
  que el gate no se rompe — pero el bloque se lee mejor y evita sorpresas con otras
  herramientas que toquen el archivo.
- **El orden de la lista no significa nada** (queda como garantía del `gate`, hoy sin
  efecto práctico con un único binding).
- **Sólo `account` y `scope`.** Cualquier otra clave (por ejemplo `provider`) se
  **rechaza** en la validación, igual que un `infra_bindings` en plural: un bloque que
  se ignora en silencio es peor que uno inválido, porque nadie se entera.

## Hoy (MADRE v1.1)

| Qué puede cambiar el cliente | Dónde |
|------------------------------|-------|
| **Contenido** de campos (prompt, capabilities, versión, etc.) | `arc-one.agent.yaml` en su repo |
| Metadatos operativos en UI | Centro de control Arc One |
| **Estructura** (campos obligatorios, tipos, enums) | **No** — fijada por MADRE v1.1 + este paquete |

Si el cliente **elimina** un campo obligatorio, el PR falla en `arc-one-manifest validate` con un mensaje explícito antes de llegar a Arc One.

---

## Capas de validación

```
arc-one.agent.yaml
       │
       ▼
┌──────────────────────────┐
│ arc-one-manifest audit    │  ← [v1.2] código ↔ manifest (drift guard)
│   --report-to-platform    │  ← [v1.5] + reporta a Arc One → triangulación
└──────────────────────────┘
       │
       ▼
┌──────────────────────────┐
│ arc-one-manifest validate │  ← reglas MADRE v1.1/v1.2 (este repo, tag v1.x)
└──────────────────────────┘
       │
       ▼
┌──────────────────────────┐
│ arc-one-manifest gate     │  ← drift + semver vs versión registrada
└──────────────────────────┘
       │
       ▼
┌──────────────────────────┐
│ Arc One API               │  ← Pydantic RegistroManifestV2Body (sandbox)
└──────────────────────────┘
```

Ver diseño de la capa `audit` / `generate`: [`MANIFEST_INTELLIGENCE.md`](MANIFEST_INTELLIGENCE.md).

### `audit --report-to-platform` (v1.5.0)

`POST /api/agentes/{id}/manifest-intelligence/audit-result` · Bearer `arc1_…`

**Body:**

| Campo | Tipo | Nota |
|---|---|---|
| `manifestSummary` | objeto \| `null` | resumen del YAML del repo. `null` = no se pudo leer → las patas 1 y 2 quedan **sin evaluar** (que no es "limpias") |
| `codeSignals` | lista | las señales que extrajo el CLI, tal cual |
| `scope` | `"diff"` \| `"full"` | **obligatorio y honesto** · `full` sólo con `--scan-all` |
| `commitSha` | string \| `null` | del CI (`GITHUB_SHA`) o del git local |
| `manifestChangedInPr` | bool | si el cambio tocó el propio Manifiesto |

El repositorio y la corrida viajan en los headers `X-Arc-One-Repo` / `X-Arc-One-Run`, que
son la única señal de vida de la conexión de repos (Arc One nunca entra al repo del cliente).

**Respuesta (201):** la triangulación completa — `legs[]` (las 3 patas, cada una con
`available` y sus diferencias), `arcOneSummary`, `catalog`, `totals`, `context`,
`reconcile` (**qué se archivó y qué no**) y los `findings` materializados. El CLI la
renderiza en `--format pr-comment`.

⚠️ **Que la entrega falle no rompe el CI** — pero el motivo va al log y al comment. Nunca
en silencio.

### `audit --exclude GLOB` (v1.5.0)

Saca rutas del escaneo, además de las que ya se excluyen por default (repetible). Es para
**código que está en el repo pero no describe lo que el agente hace**: tooling de CI,
scripts de integración, fixtures.

```bash
arc-one-manifest audit --scan-all --exclude 'scripts/**' --exclude 'examples/**'
```

⚠️ **Lo excluido no se mira.** Es un recorte del alcance, no un silenciador de hallazgos:
si algo real vive ahí, Arc One deja de verlo. El default incluye `scripts/**` a propósito
—en la mayoría de los repos ahí aparece comportamiento real del agente— y el recorte es
una decisión del cliente, repo por repo.

### Qué pasa cuando el extractor no puede identificar algo

Un secreto o un servidor MCP que se detecta pero **no se puede nombrar** viaja con un id
reservado (`runtime-secret`, `custom-mcp`). Arc One no lo presenta como si fuera el nombre
del recurso: el Hallazgo dice que **no se pudo identificar**, apunta al archivo y la línea
—que es lo accionable— y va con la **certeza más baja**. Es el hueco reservado al juez LLM.

---

## Si Arc One cambia la estructura (futuro)

### Escenario A — Nueva versión MADRE global (ej. v1.2)

1. Arc One publica spec MADRE v1.2 en sandbox
2. Release `arc-one-manifest-tools` **v1.2.0** con validadores nuevos
3. Guía de migración para clientes
4. Clientes actualizan pin `@v1.2.0` cuando estén listos
5. Campo `manifest_version: "1.2"` en YAML

### Escenario B — Perfil por workspace (futuro)

Algunos bancos pueden exigir campos extra o relajar otros:

```
GET /api/workspace/manifest-schema
Authorization: Bearer arc1_…
→ JSON Schema del workspace (base MADRE + overrides)
```

El CLI, con token del workspace:

1. Descarga schema (cacheable en CI)
2. Valida YAML contra perfil del workspace
3. Registro en API re-valida con el mismo perfil

**Hoy no está implementado** — la PoC usa MADRE v1.1 global fija.

### Escenario C — Solo contenido (hoy)

Centro de control permite editar **valores** exportados al manifest, no agregar/quitar campos del schema. Los cambios estructurales siguen siendo responsabilidad de Arc One + release de tools.

---

## Matriz de versiones

| `manifest_version` en YAML | Tools tag | API sandbox |
|----------------------------|-----------|-------------|
| `1.1` | `v1.x` | RegistroManifestV2Body actual |
| `1.2` | `v1.x` | RegistroManifestV2Body actual |
| `1.3` | `v1.4.x+` | + `identidad.infraBinding` (opcional) |
| `1.3` | `v1.5.x+` | + `audit --report-to-platform` (no cambia el YAML) |

> ⚠️ **`v1.3.2` NO sirve para `manifest_version: "1.3"`.** Esa versión se publicó antes
> del bloque: ni lo valida ni lo manda al registrar. Un cliente que pinee `@v1.3.2` y
> declare `infra_binding` tiene un CLI que ignora el bloque en silencio. El soporte
> entra en **`v1.4.0`**.

Regla para clientes: **`manifest_version` en YAML debe coincidir con la major del tools tag** (`1.1` → `v1.x`).

---

## Bulk registration (futuro)

Múltiples agentes sin wizard:

- Carpeta `manifests/*.yaml` + matrix CI, o
- `POST /api/agentes/registro-completo/bulk`

Cada item se valida con el mismo perfil de workspace. Encaja con este paquete como orquestador CLI/Action.
