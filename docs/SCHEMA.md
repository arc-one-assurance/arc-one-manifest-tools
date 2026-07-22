# Evolución del schema del manifest

## `infra_binding` — dónde opera el agente (v1.3)

Bloque **opcional**, **top-level**, junto a `deployment_target`. Declara en qué cuenta de
nube vive el agente y cuáles de los recursos de esa cuenta son suyos.

```yaml
manifest_version: "1.3"
deployment_target: cloud-run/google   # en qué plataforma corre

infra_binding:                        # opcional · lista · dónde vive y qué es suyo
  - account: acme-prod                # projectId (GCP) / accountId (AWS)
    scope:
      resource_prefixes: [nova-]
      regions: [europe-west1]
      labels: { app: nova }           # se acepta, todavía NO recorta (ver abajo)
  - account: "112233445566"           # un agente puede vivir en más de una nube
    scope:
      resource_prefixes: [nova-events-]
```

**Reglas:**

- **Nunca lleva credenciales.** El `account` es una coordenada, no un secreto — la
  credencial de la nube se carga una sola vez en Arc One, por cuenta y por workspace.
  Es lo que hace que este bloque sea seguro de commitear al repo.
- **El proveedor no se declara, se deriva** de la cuenta conectada en Arc One.
- **`scope` es obligatorio** en cada binding, con al menos `resource_prefixes` o
  `regions`. Un scope de solo `labels` se rechaza: los escaneos todavía no traen
  etiquetas, así que no recortaría nada — declaración muerta silenciosa, jamás.
- **Una cuenta, un binding**: si el agente usa varios grupos de recursos de la misma
  cuenta, van todos en el mismo `scope`.
- **Efecto sobre el bump de versión** (lo que sugiere `gate`): cambiar de plataforma
  (`deployment_target`) o de `account` → **minor** (otra credencial, otra frontera de
  seguridad). Reacomodar el `scope` dentro de la misma cuenta → **patch**.

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
| `1.3` | `v1.3.x+` | + `identidad.infraBinding` (opcional) |

Regla para clientes: **`manifest_version` en YAML debe coincidir con la major del tools tag** (`1.1` → `v1.x`).

---

## Bulk registration (futuro)

Múltiples agentes sin wizard:

- Carpeta `manifests/*.yaml` + matrix CI, o
- `POST /api/agentes/registro-completo/bulk`

Cada item se valida con el mismo perfil de workspace. Encaja con este paquete como orquestador CLI/Action.
