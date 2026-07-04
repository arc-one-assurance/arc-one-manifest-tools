# Evolución del schema del manifest

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
│ arc-one-manifest validate │  ← reglas MADRE v1.1 (este repo, tag v1.x)
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

Regla para clientes: **`manifest_version` en YAML debe coincidir con la major del tools tag** (`1.1` → `v1.x`).

---

## Bulk registration (futuro)

Múltiples agentes sin wizard:

- Carpeta `manifests/*.yaml` + matrix CI, o
- `POST /api/agentes/registro-completo/bulk`

Cada item se valida con el mismo perfil de workspace. Encaja con este paquete como orquestador CLI/Action.
