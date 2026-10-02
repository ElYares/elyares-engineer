# Catálogos de seguridad de `elyares-auditor`

388 reglas en cuatro catálogos. Cada regla tiene un identificador único
(`SEC-<área>-<número>`), un enunciado con *siempre* o *nunca*, la consecuencia
(*Si no*), cómo comprobarla (*Verificación*), su severidad y la fuente.

`install.sh` copia esta carpeta a `~/.claude/elyares/seguridad`, que es donde
la busca el agente. Nunca se lee un catálogo entero: se cargan las reglas de un
área buscando su prefijo, por ejemplo `rg -n -A6 '^### SEC-LW-'`.

| Área | Qué cubre | Reglas | Catálogo |
|---|---|---|---|
| `AUTH` | Autenticación: contraseñas, recuperación, JWT | 12 | `01-owasp-web.md` |
| `SES` | Gestión de sesión | 5 | `01-owasp-web.md` |
| `AC` | Control de acceso, IDOR y multi-tenant | 10 | `01-owasp-web.md` |
| `VAL` · `INJ` | Validación de entrada e inyección | 2 · 8 | `01-owasp-web.md` |
| `XSS` | XSS y codificación de salida | 6 | `01-owasp-web.md` |
| `CSRF` | CSRF y peticiones entre orígenes | 4 | `01-owasp-web.md` |
| `SSRF` | Peticiones salientes a URL del usuario | 3 | `01-owasp-web.md` |
| `FILE` | Subida y descarga de archivos | 6 | `01-owasp-web.md` |
| `CRY` | Criptografía | 7 | `01-owasp-web.md` |
| `SECR` | Secretos en código y en el cliente | 5 | `01-owasp-web.md` |
| `ERR` | Manejo de errores y fuga de información | 4 | `01-owasp-web.md` |
| `LOG` | Logging y auditoría de la aplicación | 6 | `01-owasp-web.md` |
| `DES` | Deserialización e integridad de datos | 2 | `01-owasp-web.md` |
| `RED` | Redirecciones | 1 | `01-owasp-web.md` |
| `BIZ` | Lógica de negocio: precios, pagos, webhooks, carreras | 11 | `01-owasp-web.md` |
| `CFG` | Configuración insegura | 5 | `01-owasp-web.md` |
| `DEP` | Componentes vulnerables | 3 | `01-owasp-web.md` |
| `API` | OWASP API Security Top 10 2023 | 14 | `02-api-movil-stacks.md` |
| `MOV` | Flutter, según MASVS | 16 | `02-api-movil-stacks.md` |
| `LAR` | Laravel, Eloquent, Sanctum, Fortify, spatie | 32 | `02-api-movil-stacks.md` |
| `LW` | Livewire 3 y 4 | 13 | `02-api-movil-stacks.md` |
| `GO` | Go: net/http y contrato OpenAPI | 12 | `02-api-movil-stacks.md` |
| `JS` | Nuxt, Vue, React, Node, TypeScript | 12 | `02-api-movil-stacks.md` |
| `PY` | FastAPI, Pydantic, SQLAlchemy | 10 | `02-api-movil-stacks.md` |
| `INT` | Integraciones: Stripe, S3/MinIO, OneSignal, Sentry, correo | 11 | `02-api-movil-stacks.md` |
| `IAC` | Código escrito por un agente de IA | 30 | `03-ia.md` |
| `AGT` | El agente de programación y su entorno | 22 | `03-ia.md` |
| `LLM` | Aplicaciones que integran un modelo | 26 | `03-ia.md` |
| `HDR` | Cabeceras y navegador | 13 | `04-protecciones.md` |
| `AUT` | Autenticación y abuso, del lado de la plataforma | 11 | `04-protecciones.md` |
| `NET` | TLS y red | 11 | `04-protecciones.md` |
| `CNT` | Contenedores | 9 | `04-protecciones.md` |
| `SCR` | Secretos en servidor, repositorio e imágenes | 8 | `04-protecciones.md` |
| `DAT` | Datos: respaldos, cifrado, buckets | 10 | `04-protecciones.md` |
| `OBS` | Observabilidad de seguridad | 9 | `04-protecciones.md` |
| `SUP` | Cadena de suministro y CI | 11 | `04-protecciones.md` |
| `LEG` | Legal, México (LFPDPPP) | 8 | `04-protecciones.md` |

Además de las reglas:

- `03-ia.md` §7: lista de comprobación para auditar un diff escrito por un agente.
- `04-protecciones.md` §0.1 y §10: niveles de impacto de las herramientas
  (N0 estático local, N1 remoto pasivo, N2 activo) y la tabla de herramientas
  con su comando en solo lectura.

## Lo que hay que saber antes de fiarse

- **Sin calibrar.** Los patrones de `rg` no se han corrido contra ningún
  repositorio: una coincidencia es un sitio que revisar, no un hallazgo.
- **Sin verificar.** Lo que no se confirmó en fuente primaria lleva esa marca
  en el texto, y cada catálogo cierra con su sección de dudas y huecos.
- **Con fecha.** Versiones y avisos son del 2026-10-02.

## Cambio respecto a la investigación original

En `04-protecciones.md`, `SEC-LOG-01…09` pasó a `SEC-OBS-01…09` y
`SEC-RED-01…11` a `SEC-NET-01…11`: los mismos identificadores existían en
`01-owasp-web.md` con otro significado (logging de la aplicación y
redirecciones). No cambió ningún texto.
