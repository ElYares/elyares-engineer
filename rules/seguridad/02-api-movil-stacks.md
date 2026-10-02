# 02 — Seguridad de APIs, móvil y reglas por stack (catálogo para `elyares-auditor`)

Fecha de la investigación: 2026-10-02. Versiones, textos citados y avisos de seguridad se leyeron ese día en la fuente primaria. Algunas fuentes de apoyo solo se comprobó que existen y responden, sin releer el pasaje (lista en "Dudas y huecos"). Lo que no se pudo confirmar lleva la marca **sin verificar**.

## Versiones y ediciones confirmadas

| Elemento | Vigente al 2026-10-02 | Dónde se confirmó |
|---|---|---|
| OWASP API Security Top 10 | **2023** (el repo solo tiene `editions/2019` y `editions/2023`; último commit 2026-09-21, sin rama ni RC de una edición nueva) | https://api-security.owasp.org/ · https://github.com/OWASP/API-Security |
| OWASP MASVS | **v2.1.0** (2024-01-18); 8 grupos, 24 controles, sin niveles L1/L2/R | https://github.com/OWASP/owasp-masvs/releases |
| OWASP MASTG | **v2.0.0** (2026-06-30): cierra el refactor a componentes atómicos (MASTG-TEST/TECH/BEST/KNOW) | https://github.com/OWASP/owasp-mastg/releases |
| OWASP MASWE | MASWE-0001…0078. La numeración publicada hoy (0005 = logs, 0004 = datos sensibles en el paquete, 0028 = pinning) no coincide con la que circulaba en 2024–2025; el cambio no se localizó en notas de versión (**sin verificar**) | https://mas.owasp.org/MASWE/ |
| Laravel | **13.x** (13.34.0; salió 2026-03-17; PHP ≥ 8.3). **Laravel 11 dejó de recibir parches de seguridad el 2026-03-12**; Laravel 12 los recibe hasta 2027-02-24 | https://laravel.com/docs/13.x/releases |
| Livewire | **4.4.7** (2026-09-28); rama 3.x aún parcheada (3.8.3) | https://livewire.laravel.com/docs/4.x/upgrading |
| Sanctum / Fortify / Jetstream | 4.3.3 / 1.40.0 / 5.5.3 | packagist.org |
| spatie/laravel-permission / medialibrary | 8.3.0 / 11.23.8 | packagist.org |
| wire-elements/modal / livewire-dropzone | 3.0.4 (acepta Livewire ^3.2.3 y ^4) / 3.0.1 (solo Livewire ^4) | packagist.org |
| Go | **1.27** (2026-08-19); soportadas 1.27 y 1.26 | https://go.dev/doc/devel/release |
| Nuxt | **4.5.2** (2026-08-05); existe documentación `5.x`, estado **sin verificar** | https://github.com/nuxt/nuxt/releases |
| FastAPI / Pydantic / PyJWT / SQLAlchemy | 0.142.2 / 2.13.5 / 2.15.1 / 2.1.2 | pypi.org |
| Flutter / Dart | **3.47.6 / 3.13.5** (estable, 2026-10-01) | https://docs.flutter.dev/security |
| flutter_secure_storage / dio / drift | 11.2.0 / 5.11.1 / 2.35.1. `sqlcipher_flutter_libs` está en fin de vida (`0.7.0+eol`) | pub.dev |

### Qué cambió en Livewire 4 respecto a la 3 en materia de seguridad

La página de seguridad de la 4.x es, salvo `Route::livewire()` y la firma de `setUpdateRoute`, idéntica a la de la 3.x (se compararon ambas con `diff`). El modelo de amenaza no cambió: propiedades públicas y métodos públicos siguen siendo entrada del cliente. Lo que sí cambió:

1. **Componentes de archivo único (SFC) y multi-archivo.** La clase PHP vive en `resources/views/**/⚡*.blade.php` (o sin emoji). Cualquier grep, Larastan o test de arquitectura que solo mire `app/Livewire` deja de ver los componentes. Todas las verificaciones LW de este catálogo incluyen `resources/views`; hay que revisar también `paths` en `phpstan.neon` y los `arch()` de Pest (que Larastan analice el PHP embebido en un SFC está **sin verificar**).
2. **Endpoints con hash.** `/livewire/update` pasó a `/livewire-{hash}/update` (hash derivado de `APP_KEY`). Un `setUpdateRoute` que no use el parámetro `$path` rompe o desvía el endpoint.
3. **Payload guards** nuevos en `config/livewire.php`: `payload.max_size` (1 MB), `max_nesting_depth` (10), `max_calls` (50), `max_components` (200).
4. **`csp_safe`** como opción de configuración (build de Alpine sin `unsafe-eval`).
5. **Islands, `#[Async]`, `#[Defer]`, `wire:model` sin burbujeo**: no alteran el modelo de confianza. `#[Async]` y las islas siguen invocando métodos públicos.
6. Avisos vigentes: CVE-2025-54068 (RCE en hidratación, 3.x < 3.6.4), CVE-2026-81887 (XSS DOM, ≤ 3.8.2 y ≤ 4.3.3), CVE-2024-47823 (RCE en subidas, < 3.5.2).

Fuentes: https://livewire.laravel.com/docs/4.x/security · https://livewire.laravel.com/docs/3.x/security · https://livewire.laravel.com/docs/4.x/upgrading · https://github.com/livewire/livewire/blob/main/config/livewire.php · https://github.com/advisories?query=livewire%2Flivewire

### Convenciones

- Los patrones son para `ripgrep` (`rg`). Un resultado no es un hallazgo: es un candidato que el auditor confirma leyendo el contexto. Donde dice "solo revisión manual" no existe patrón fiable.
- `PHPSRC` = `app routes resources/views database config bootstrap` · `DARTSRC` = `lib` · `JSSRC` = `app components composables pages plugins server src` (excluye `node_modules`, `.nuxt`, `.output`, `dist`).
- Las severidades suponen datos reales de usuarios en producción.
- Este documento no repite el núcleo OWASP agnóstico, el código generado por IA ni el hardening de infraestructura; las reglas de aquí concretan esos temas por stack.

---

## API — OWASP API Security Top 10 2023

### SEC-API-01 — Todo endpoint que recibe un identificador de objeto siempre comprueba que el usuario autenticado puede acceder a ese objeto concreto
La comprobación va en el servidor y contra el objeto ya cargado, no contra el ID. Usar UUID en vez de enteros no sustituye la autorización.
*Si no:* BOLA/IDOR: cambiando el ID de la ruta o del cuerpo se leen, modifican o borran recursos de otro usuario o de otro tenant.
*Verificación:* por cada ruta con parámetro (`rg -n "\{[a-zA-Z_]+\}" routes/` · `rg -n "r\.PathValue\(|chi\.URLParam\(" -g '*.go'` · `rg -n "@(router|app)\.(get|put|patch|delete|post)\(.*\{" -g '*.py'`) debe existir un test que pida el recurso de otro usuario y espere 403/404. Sin ese test, hallazgo.
*Severidad:* crítica
*Fuente:* OWASP API Security Top 10 2023, API1:2023 — https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/

### SEC-API-02 — Una ruta solo queda sin autenticación si figura en una lista explícita de rutas públicas
La autenticación se aplica por grupo o router (denegar por defecto) y las excepciones se enumeran en un único sitio revisable.
*Si no:* un endpoint nuevo, típicamente escrito por un agente, nace público y expone datos o acciones sin sesión.
*Verificación:* Laravel: `php artisan route:list --json | jq -r '.[] | select((.middleware|tostring|test("auth")|not)) | .uri'` y comparar contra la lista pública. Go/FastAPI: ver SEC-GO-11 y SEC-PY-01. Con contrato OpenAPI: toda operación sin `security` debe estar en la lista.
*Severidad:* crítica
*Fuente:* OWASP API Security Top 10 2023, API2:2023 — https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/

### SEC-API-03 — Login, registro, recuperación de contraseña, verificación de OTP y emisión de tokens siempre llevan un límite de intentos más estricto que el resto de la API
OWASP trata la recuperación de credenciales como un endpoint de login a efectos de fuerza bruta.
*Si no:* credential stuffing, fuerza bruta de OTP de 6 dígitos y enumeración de cuentas.
*Verificación:* `rg -n "login|password|forgot|reset|otp|verify|two-factor|sanctum/token" routes/` y confirmar `throttle:` o limitador con nombre en cada una; test que dispare N+1 intentos y espere 429.
*Severidad:* alta
*Fuente:* OWASP API Security Top 10 2023, API2:2023 — https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/

### SEC-API-04 — Las respuestas nunca serializan el modelo completo; siempre pasan por un esquema de salida con lista explícita de campos
Resource de Laravel, `response_model` de FastAPI o struct de respuesta en Go, distinto del modelo de persistencia.
*Si no:* exposición excesiva de datos: hashes, tokens, banderas internas, PII de terceros y columnas añadidas después salen por la API sin que nadie lo decida.
*Verificación:* `rg -n "return \\$\w+(->fresh\(\)|->load\(.*\))?;|response\(\)->json\(\\$\w+\)|->toArray\(\)" app/Http` · `rg -n "json\.NewEncoder\(w\)\.Encode\(" -g '*.go'` y revisar el tipo codificado · en Laravel, `$hidden` / `#[Hidden]` debe cubrir `password`, `remember_token`, `two_factor_secret` y `two_factor_recovery_codes`: `rg -n -U "(hidden\s*=\s*\[|Hidden\(\[)[^\]]*\]" app/Models`.
*Severidad:* alta
*Fuente:* OWASP API Security Top 10 2023, API3:2023 — https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/

### SEC-API-05 — Los campos que el cliente puede escribir siempre salen de una lista blanca por endpoint y rol
La lista se define en el validador del endpoint, no en el modelo. Los campos desconocidos se rechazan o se descartan antes de tocar la persistencia.
*Si no:* asignación masiva a nivel de propiedad: el cliente añade `role`, `is_admin`, `tenant_id`, `price` o `verified_at` al JSON y escala privilegios.
*Verificación:* por stack: SEC-LAR-01/02, SEC-GO-03, SEC-PY-03. Test genérico: enviar un campo privilegiado extra y comprobar que no se persiste.
*Severidad:* crítica
*Fuente:* OWASP API Security Top 10 2023, API3:2023 — https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/ · OWASP Mass Assignment Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html

### SEC-API-06 — Todo listado siempre pagina con un tope impuesto por el servidor, y toda entrada lleva siempre un tamaño máximo
El cliente puede pedir menos filas, nunca más. El tope de tamaño cubre cuerpo, cadenas, elementos de arreglo y archivos.
*Si no:* `?per_page=1000000` o un cuerpo gigante agotan memoria y base de datos y permiten volcar la tabla entera; si la entrada alimenta servicios de pago por uso (SMS, correo, almacenamiento), además cuesta dinero.
*Verificación:* `rg -n "->get\(\)|->all\(\)|::all\(\)" app/Http` · `rg -n "per_page|limit" app/Http` y confirmar `min(…, MAX)` o `max:` · reglas sin tope: `rg -n "'(string|array)'" app/Http/Requests | rg -v "max:"` · Go: SEC-GO-03 · Python: `Field(max_length=` y `conlist(max_length=`.
*Severidad:* media
*Fuente:* OWASP API Security Top 10 2023, API4:2023 — https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/

### SEC-API-07 — Las rutas administrativas siempre comprueban el rol o permiso en el servidor; ocultar el botón o la URL no cuenta
Aplica también al método HTTP: que un rol pueda hacer `GET` no implica que pueda hacer `DELETE` sobre la misma ruta.
*Si no:* BFLA: un usuario normal llama directamente a `/admin/...` o cambia `GET` por `DELETE` y ejecuta funciones de administrador.
*Verificación:* `rg -n "admin|manage|export|impersonat" routes/` y confirmar middleware `can:`/`role:`/`permission:` en el grupo; test con usuario sin rol que espere 403 por cada verbo.
*Severidad:* crítica
*Fuente:* OWASP API Security Top 10 2023, API5:2023 — https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/

### SEC-API-08 — Los flujos de negocio abusables (cupones, reservas, compras, invitaciones, envío de SMS o correo) siempre tienen un límite por usuario y por recurso además del límite por IP
*Si no:* automatización del flujo: acaparar inventario, agotar cupones, usar el endpoint como pasarela de spam o de SMS con cargo al proyecto.
*Verificación:* solo revisión manual: inventariar los flujos con el dueño del producto y comprobar que cada uno tiene limitador con clave de usuario (`Limit::perMinute()->by($request->user()->id)`).
*Severidad:* alta
*Fuente:* OWASP API Security Top 10 2023, API6:2023 — https://api-security.owasp.org/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/

### SEC-API-09 — El servidor nunca solicita una URL aportada por el cliente sin validarla contra una lista blanca de esquema y host, y sin seguir redirecciones
Incluye webhooks configurables, importación por URL, avatares remotos y generadores de vista previa o PDF. medialibrary < 11.23.0 tiene un SSRF propio en `addMediaFromUrl` (CVE-2026-48555).
*Si no:* SSRF: lectura de metadatos de la nube (`169.254.169.254`), escaneo de la red interna, acceso a Redis, MinIO o paneles sin autenticación.
*Verificación:* `rg -n "Http::(get|post|head)\(\\$|file_get_contents\(\\$|addMediaFromUrl\(|curl_setopt\(.*CURLOPT_URL" PHPSRC` · `rg -n "http\.(Get|Post)\(\w+|NewRequest(WithContext)?\(.*,\s*\w+URL" -g '*.go'` · `rg -n "(httpx|requests)\.(get|post)\(\w+" -g '*.py'`.
*Severidad:* alta
*Fuente:* OWASP API Security Top 10 2023, API7:2023 — https://api-security.owasp.org/editions/2023/en/0xa7-server-side-request-forgery/ · OWASP SSRF Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

### SEC-API-10 — CORS nunca refleja el `Origin` recibido ni usa comodín cuando la API acepta credenciales
Orígenes exactos y enumerados por entorno.
*Si no:* cualquier sitio que visite el usuario lee sus datos y ejecuta acciones con su sesión.
*Verificación:* `rg -n "allowed_origins'?\s*=>\s*\[\s*'\*'|allowed_origins_patterns|supports_credentials" config/cors.php` · `rg -n "Access-Control-Allow-Origin.*(\*|r\.Header\.Get\(\"Origin\"\))" -g '*.go'` · `rg -n "allow_origins=\[\"\*\"\]|allow_origin_regex" -g '*.py'`.
*Severidad:* alta
*Fuente:* OWASP API Security Top 10 2023, API8:2023 — https://api-security.owasp.org/editions/2023/en/0xa8-security-misconfiguration/ · OWASP REST Security Cheat Sheet (CORS) — https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html

### SEC-API-11 — El contrato OpenAPI y las rutas reales siempre coinciden; no existen rutas fuera del contrato ni versiones antiguas vivas sin dueño
La documentación interactiva solo es accesible para quien está autorizado a usar la API.
*Si no:* endpoints sombra (`/v1` olvidado, `/debug`, `/internal`) sin los controles de la versión actual; es el vector típico de fuga masiva.
*Verificación:* script que compare las rutas del router con `paths` del OpenAPI y falle en CI si difieren (`php artisan route:list --json` contra `jq '.paths|keys' openapi.json`; en Go, test que recorra el mux); `rg -n "v1|legacy|deprecated|debug|internal" routes/ -g '*.go' -g '*.py'`.
*Severidad:* media
*Fuente:* OWASP API Security Top 10 2023, API9:2023 — https://api-security.owasp.org/editions/2023/en/0xa9-improper-inventory-management/

### SEC-API-12 — Los datos que llegan de APIs de terceros siempre se validan como entrada no confiable y toda llamada saliente lleva timeout
Incluye respuestas de Stripe, OneSignal, proveedores de correo y servicios internos. No se siguen redirecciones a ciegas.
*Si no:* inyección de segundo orden (SQL o XSS con datos del tercero) y agotamiento de workers cuando el tercero no responde.
*Verificación:* `rg -n "Http::(get|post)" PHPSRC | rg -v "timeout\("` · Go: SEC-GO-02 · Python: `rg -n "(httpx|requests)\.(get|post)\(" -g '*.py' | rg -v "timeout="`.
*Severidad:* media
*Fuente:* OWASP API Security Top 10 2023, API10:2023 — https://api-security.owasp.org/editions/2023/en/0xaa-unsafe-consumption-of-apis/

### SEC-API-13 — Los JWT siempre se validan con un algoritmo fijado por el servidor y con `exp`, `iss` y `aud` comprobados; nunca se acepta `alg: none` ni el algoritmo que declare el token
*Si no:* falsificación de tokens por confusión de algoritmo (clave pública RS256 usada como secreto HS256) o por `none`; tokens eternos si falta `exp`.
*Verificación:* por stack: SEC-GO-09 y SEC-PY-05. Genérico: `rg -n "verify_signature.*False|alg.*none|UnsafeAllowNoneSignatureType|decode\([^)]*verify\s*=\s*False" .`
*Severidad:* crítica
*Fuente:* RFC 8725, JSON Web Token Best Current Practices, §3.1–3.2 y §3.8–3.9 — https://www.rfc-editor.org/rfc/rfc8725 · OWASP REST Security Cheat Sheet (JWT) — https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html

### SEC-API-14 — Tokens, contraseñas y llaves de API nunca viajan en la URL
Van en la cabecera `Authorization` o en el cuerpo.
*Si no:* quedan en logs del servidor web, del proxy, del CDN, en el historial del navegador y en la cabecera `Referer`.
*Verificación:* `rg -n "[?&](token|api_key|apikey|access_token|password|secret)=" . -g '!*.lock' -g '!node_modules'`; revisar los logs de acceso de staging.
*Severidad:* alta
*Fuente:* OWASP REST Security Cheat Sheet, "Sensitive information in HTTP requests" — https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html

---

## MOV — Flutter según MASVS v2.1.0 / MASTG v2.0.0

Nota de base, confirmada en MASTG: Flutter usa el `HttpClient` de Dart sobre BoringSSL, con su propio almacén de certificados, no pasa por ATS en iOS ni respeta el proxy del sistema. Consecuencia: `network_security_config.xml` y `NSAppTransportSecurity` **no gobiernan** el tráfico de Dio; el pinning y la prohibición de texto claro se implementan y se auditan en Dart (MASTG-KNOW-0015, MASTG-KNOW-0072, MASTG-TECH-0109/0110).

### SEC-MOV-01 — Los tokens de sesión y credenciales siempre se guardan en `flutter_secure_storage`; nunca en SharedPreferences, GetStorage, Hive sin cifrar, archivos ni Drift en claro
Desde la v10, `flutter_secure_storage` usa RSA-OAEP + AES-GCM en Android y Keychain en iOS; `EncryptedSharedPreferences` de Jetpack quedó desaconsejado. En web solo funciona sobre HTTPS y no ofrece la misma garantía.
*Si no:* cualquier respaldo, dispositivo rooteado o extracción forense obtiene el token de Sanctum en texto claro y suplanta al usuario.
*Verificación:* `rg -n "(SharedPreferences|GetStorage|Hive\.box|box\.write|prefs\.set\w+)\b.*" lib | rg -i "token|password|secret|pin|session|bearer"` · `rg -n "GetStorage\(\)|SharedPreferences\.getInstance" lib` y revisar cada clave escrita.
*Severidad:* crítica
*Fuente:* MASVS-STORAGE-1; MASWE-0001 (Sensitive Data Stored Unencrypted in Private Storage) — https://mas.owasp.org/MASVS/controls/MASVS-STORAGE-1/ · https://pub.dev/packages/flutter_secure_storage

### SEC-MOV-02 — El binario de la app nunca contiene secretos: ni en `--dart-define`, ni en `.env` empaquetado, ni en flavors, ni en constantes
Solo se admiten identificadores públicos (URL base, App ID de OneSignal, DSN de Sentry, llave publicable de Stripe). `flutter_dotenv` lo dice en su propia documentación: los assets se extraen del build. La ofuscación no protege cadenas.
*Si no:* cualquiera descomprime el APK/IPA, ejecuta `strings` o `blutter` y obtiene la llave; con una llave de servidor de Stripe, OneSignal o S3 el daño es total.
*Verificación:* `rg -n "sk_(live|test)_|rk_live_|os_v2_(app|org)_|AKIA[0-9A-Z]{16}|sntrys_|whsec_|-----BEGIN" lib assets android ios` · `rg -n "String\.fromEnvironment\(|dotenv\.(env|get)" lib` y clasificar cada valor como público o secreto · sobre el artefacto: `unzip -o app-release.apk -d out && strings out/lib/*/libapp.so | rg -i "secret|api[_-]?key|sk_live"`.
*Severidad:* crítica
*Fuente:* MASVS-STORAGE-1 y MASVS-CRYPTO-2; MASWE-0004 (Sensitive Data Hardcoded in the App Package) — https://mas.owasp.org/MASWE/ · https://docs.flutter.dev/deployment/obfuscate · https://pub.dev/packages/flutter_dotenv

### SEC-MOV-03 — La validación de certificados TLS nunca se desactiva: no existe `badCertificateCallback` que devuelva `true` ni `HttpOverrides` permisivo
Suele aparecer "temporalmente" para un servidor de pruebas con certificado autofirmado y llega a producción.
*Si no:* cualquier red hostil (Wi-Fi público, proxy) intercepta y modifica todo el tráfico, token incluido.
*Verificación:* `rg -n "badCertificateCallback|HttpOverrides\.global|validateCertificate|onBadCertificate" lib` — todo resultado se revisa; cualquier `=> true` es hallazgo.
*Severidad:* crítica
*Fuente:* MASVS-NETWORK-1; MASWE-0027 (Insecure Certificate Validation) — https://mas.owasp.org/MASVS/controls/MASVS-NETWORK-1/ · https://api.flutter.dev/flutter/dart-io/HttpClient/badCertificateCallback.html

### SEC-MOV-04 — Las URL base de todos los flavors de distribución usan siempre `https://`; no hay tráfico en texto claro
Como Dart ignora la política de red de la plataforma, la garantía tiene que estar en el código y en la configuración del flavor.
*Si no:* credenciales y datos viajan legibles; el flavor de pruebas con `http://` termina publicado.
*Verificación:* `rg -n "http://" lib android/app/src ios/Runner -g '!*.md'` · `rg -n "usesCleartextTraffic|cleartextTrafficPermitted|NSAllowsArbitraryLoads" android ios`.
*Severidad:* alta
*Fuente:* MASVS-NETWORK-1; MASWE-0026 (Network Traffic Not Encrypted); MASTG-TEST-0237 (Cross-Platform Framework Configurations Allowing Cleartext Traffic) — https://mas.owasp.org/MASVS/controls/MASVS-NETWORK-1/

### SEC-MOV-05 — Si la app maneja datos sensibles, el pinning hacia los endpoints propios se implementa siempre en Dart, con al menos un pin de respaldo
El pinning de `network_security_config.xml` o de ATS no cubre las conexiones de Dio. Se fija la llave pública (SPKI), no el certificado hoja, y se prevé la rotación.
*Si no:* una CA comprometida o instalada en el dispositivo permite MITM sobre un canal que parece seguro; sin pin de respaldo, una rotación de certificado deja la app inservible.
*Verificación:* `rg -n "http_certificate_pinning|SecurityContext\(withTrustedRoots:\s*false|fingerprint|sha256/" lib`; sin resultados en una app con datos sensibles, hallazgo. Prueba dinámica: MASTG-TECH-0109 (interceptar con proxy y comprobar que la conexión falla).
*Severidad:* media
*Fuente:* MASVS-NETWORK-2; MASWE-0028 (Insecure Identity Pinning); MASTG-KNOW-0015 — https://mas.owasp.org/MASVS/controls/MASVS-NETWORK-2/ · OWASP Pinning Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Pinning_Cheat_Sheet.html

### SEC-MOV-06 — Los builds de distribución nunca registran cabeceras, cuerpos de petición, tokens ni PII
`LogInterceptor` de Dio imprime cabeceras (incluida `Authorization`) y cuerpos; su documentación dice que no se use en producción. `print` y `debugPrint` escriben en logcat y en la consola del sistema.
*Si no:* el token queda en logcat, legible por `adb`, por reportes de fallos y por herramientas de soporte.
*Verificación:* `rg -n "LogInterceptor|PrettyDioLogger|\bprint\(|debugPrint\(|log\(" lib` y confirmar que cada uso está tras `kDebugMode`; regla de lint `avoid_print` activa en `analysis_options.yaml`.
*Severidad:* alta
*Fuente:* MASVS-STORAGE-2; MASWE-0005 (Insertion of Sensitive Data into Logs); MASTG-BEST-0002 — https://mas.owasp.org/MASVS/controls/MASVS-STORAGE-2/ · https://pub.dev/packages/dio

### SEC-MOV-07 — Una base Drift con datos personales o de negocio sensibles siempre se cifra con SQLite3MultipleCiphers y la llave vive en `flutter_secure_storage`, nunca en el código
`sqlcipher_flutter_libs` está en fin de vida; Drift documenta `sqlite3` 3.x con `source: sqlite3mc` y recomienda comprobar `PRAGMA cipher` para no abrir sin cifrado por error.
*Si no:* el archivo `.sqlite` se copia de un respaldo o de un dispositivo rooteado y se lee completo.
*Verificación:* `rg -n "PRAGMA key|sqlite3mc|PRAGMA cipher" lib pubspec.yaml`; sin resultados y con tablas sensibles, hallazgo · `rg -n "PRAGMA key\s*=\s*'[^$]" lib` detecta la frase en duro.
*Severidad:* alta
*Fuente:* MASVS-STORAGE-1; MASWE-0001; MASTG-KNOW-0037 — https://mas.owasp.org/MASVS/controls/MASVS-STORAGE-1/ · https://drift.simonbinder.eu/platforms/encryption/

### SEC-MOV-08 — La cola offline nunca persiste contraseñas ni tokens, y el servidor siempre revalida autorización, estado e idempotencia de cada operación al sincronizar
La cola guarda la intención (operación, payload, llave de idempotencia), no las credenciales. Lo encolado pudo editarse en el dispositivo y pudo quedar obsoleto.
*Si no:* operaciones manipuladas en la base local se aplican en el servidor; reintentos duplican cobros o registros; un permiso revocado sigue surtiendo efecto.
*Verificación:* leer el esquema de la tabla de cola (`rg -n "class \w*(Queue|Outbox|Pending)\w* extends Table" lib`) y buscar columnas con credenciales; en el backend, test que reenvíe dos veces la misma operación y que sincronice con un usuario sin permiso.
*Severidad:* alta
*Fuente:* MASVS-AUTH-1 y MASVS-CODE-4 — https://mas.owasp.org/MASVS/controls/MASVS-AUTH-1/ · OWASP API Security Top 10 2023, API1:2023 — https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/

### SEC-MOV-09 — Cerrar sesión siempre revoca el token en el servidor y borra del dispositivo token, base local, caché y cola
En iOS el Keychain sobrevive a la desinstalación (**sin verificar** en fuente primaria); conviene limpiar en el primer arranque tras instalar.
*Si no:* el siguiente usuario del dispositivo, o quien obtenga un respaldo, accede a los datos del anterior; el token sigue válido en el servidor.
*Verificación:* leer el método de logout (`rg -n "logout|signOut" lib`) y confirmar: llamada al endpoint de revocación, `deleteAll()` del almacén seguro, borrado de la base Drift y de la cola.
*Severidad:* alta
*Fuente:* MASVS-AUTH-3; MASWE-0024 (Sensitive Data Accessible After Session Termination) — https://mas.owasp.org/MASVS/controls/MASVS-AUTH-3/

### SEC-MOV-10 — Los datos sensibles nunca entran en los respaldos automáticos del sistema
Android respalda en Google Drive por defecto; `flutter_secure_storage` recomienda desactivarlo.
*Si no:* la base local y las preferencias se restauran en otro dispositivo o se extraen con `adb backup`.
*Verificación:* `rg -n "allowBackup|fullBackupContent|dataExtractionRules" android/app/src/main/AndroidManifest.xml`; debe ser `android:allowBackup="false"` o reglas de exclusión explícitas.
*Severidad:* media
*Fuente:* MASVS-STORAGE-2; MASWE-0006 (Sensitive Data Not Excluded From Backup); MASTG-TEST-0262 — https://mas.owasp.org/MASVS/controls/MASVS-STORAGE-2/

### SEC-MOV-11 — Los enlaces profundos que abren flujos autenticados usan solo App Links / Universal Links verificados; un esquema propio nunca transporta tokens ni dispara acciones
Un esquema `miapp://` puede registrarlo cualquier otra app. Con `android:autoVerify="true"` y `assetlinks.json` el sistema entrega el enlace solo a la app legítima.
*Si no:* una app maliciosa captura el enlace de restablecimiento de contraseña o el callback de OAuth, o invoca pantallas internas con parámetros manipulados.
*Verificación:* `rg -n "android:scheme=|autoVerify|CFBundleURLSchemes|associated-domains" android ios` · `curl -s https://<dominio>/.well-known/assetlinks.json` y `apple-app-site-association`.
*Severidad:* alta
*Fuente:* MASVS-PLATFORM-1; MASWE-0029 (Insecure Deep Links); MASTG-BEST-0070; MASTG-TEST-0393 — https://mas.owasp.org/MASVS/controls/MASVS-PLATFORM-1/ · https://docs.flutter.dev/cookbook/navigation/set-up-app-links

### SEC-MOV-12 — Los parámetros de un enlace profundo o de una notificación push siempre se validan como entrada no confiable antes de navegar o llamar a la API
Con GetX, `Get.parameters` y `Get.arguments` llegan tal cual desde el enlace.
*Si no:* navegación forzada a pantallas internas, IDs ajenos inyectados en peticiones, o carga de URL arbitrarias en un WebView.
*Verificación:* `rg -n "Get\.parameters|Get\.arguments|uriLinkStream|getInitialLink|onNotificationOpened|addClickListener" lib` y seguir cada valor hasta su uso.
*Severidad:* media
*Fuente:* MASVS-CODE-4 y MASVS-PLATFORM-1; MASTG-BEST-0071 — https://mas.owasp.org/MASVS/controls/MASVS-CODE-4/

### SEC-MOV-13 — Un WebView solo carga orígenes de una lista blanca, y nunca expone canales JavaScript ni el token a contenido que no sea propio
`JavaScriptMode.unrestricted` se usa solo si hace falta, con `NavigationDelegate.onNavigationRequest` que bloquee todo lo demás.
*Si no:* contenido remoto o inyectado ejecuta JavaScript con acceso al puente nativo y roba la sesión.
*Verificación:* `rg -n "JavaScriptMode\.unrestricted|addJavaScriptChannel|loadRequest\(|loadHtmlString\(|InAppWebView" lib`; cada WebView debe tener `onNavigationRequest` con lista blanca.
*Severidad:* alta
*Fuente:* MASVS-PLATFORM-2; MASWE-0033 y MASWE-0035; MASTG-BEST-0058 — https://mas.owasp.org/MASVS/controls/MASVS-PLATFORM-2/ · https://pub.dev/packages/webview_flutter

### SEC-MOV-14 — Los builds de tienda siempre se compilan con `--obfuscate --split-debug-info`, y la ofuscación nunca se cuenta como protección de secretos
Flutter es explícito: ofuscar solo renombra símbolos, no cifra recursos ni impide la ingeniería inversa.
*Si no:* el binario conserva nombres de clases y métodos, lo que abarata el análisis de la lógica de licencias, pagos y validaciones.
*Verificación:* `rg -n "flutter build (apk|appbundle|ipa)" . -g '*.yml' -g '*.yaml' -g '*.sh' -g 'Makefile' -g 'Fastfile' | rg -v "obfuscate"`.
*Severidad:* baja
*Fuente:* MASVS-RESILIENCE-3; MASWE-0059 (Code Obfuscation Not Implemented) — https://mas.owasp.org/MASVS/controls/MASVS-RESILIENCE-3/ · https://docs.flutter.dev/deployment/obfuscate

### SEC-MOV-15 — El artefacto publicado nunca es depurable ni incluye endpoints, credenciales o menús del flavor de desarrollo
*Si no:* un build con `debuggable` permite adjuntar un depurador y leer memoria; un menú oculto de desarrollo permite cambiar de servidor o saltarse el login.
*Verificación:* `rg -n "android:debuggable|signingConfigs\.debug" android/app` (el `build.gradle` de plantilla firma `release` con llaves de depuración) · `rg -n "kDebugMode|kReleaseMode|isDev|devMenu|staging" lib` y revisar que nada sensible dependa de una bandera mutable en tiempo de ejecución.
*Severidad:* alta
*Fuente:* MASVS-RESILIENCE-4 y MASVS-RESILIENCE-3; MASWE-0063 y MASWE-0061; MASTG-TEST-0226 — https://mas.owasp.org/MASVS/controls/MASVS-RESILIENCE-4/

### SEC-MOV-16 — La autorización nunca se decide en el cliente; los roles y permisos guardados en la app solo sirven para pintar la interfaz
Un controlador GetX con `isAdmin` es un dato que el usuario puede cambiar.
*Si no:* con Frida o editando el almacenamiento local se habilitan pantallas y botones de administrador; si el backend confía, la escalada es real.
*Verificación:* por cada pantalla condicionada por rol (`rg -n "isAdmin|hasRole|hasPermission|can\(" lib`), confirmar que el endpoint que consume aplica el mismo permiso en el servidor (SEC-API-07).
*Severidad:* crítica
*Fuente:* MASVS-AUTH-1 — https://mas.owasp.org/MASVS/controls/MASVS-AUTH-1/

---

## LAR — Laravel 12/13, Eloquent, Sanctum, Fortify, spatie

Nota: desde Laravel 13 la documentación usa atributos PHP (`#[Fillable]`, `#[Guarded]`, `#[Unguarded]`, `#[Hidden]`, `#[ScopedBy]`, `#[Authorize]`) además de las propiedades clásicas. Los patrones cubren ambas formas. El middleware CSRF se llama `PreventRequestForgery` y se configura con `$middleware->preventRequestForgery(...)`.

### SEC-LAR-01 — Ningún modelo desactiva la protección de asignación masiva: no hay `$guarded = []`, `#[Unguarded]`, ni `Model::unguard()` fuera de seeders
*Si no:* cualquier `create()`/`update()`/`fill()` con datos de la petición acepta `is_admin`, `role`, `tenant_id` o `user_id`.
*Verificación:* `rg -n "guarded\s*=\s*\[\s*\]|#\[Unguarded\]|::unguard\(|Guarded\(\[\s*\]\)" app resources/views database -g '!database/seeders/*'`.
*Severidad:* crítica
*Fuente:* Laravel 13, Eloquent › Mass Assignment — https://laravel.com/docs/13.x/eloquent#mass-assignment · OWASP Laravel Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html

### SEC-LAR-02 — A Eloquent nunca le llega `$request->all()`, `->input()` sin clave, `->except()` ni `->post()`; solo `validated()` o `safe()->only()`
`except()` es lista negra: todo campo nuevo queda permitido. `forceFill()` y `forceCreate()` se saltan `$fillable` por completo: solo admiten arreglos escritos a mano o ya validados.
*Si no:* asignación masiva, y con `$fillable` amplio, modificación de columnas que el formulario no muestra.
*Verificación:* `rg -n "(create|update|fill|forceFill|forceCreate|updateOrCreate|firstOrCreate|insert|upsert)\(\s*\\$request->(all|input|except|post|json)\(\s*\)?" PHPSRC` · `rg -n "\\$request->all\(\)" app resources/views`.
*Severidad:* crítica
*Fuente:* OWASP Laravel Cheat Sheet, Mass Assignment — https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html · Laravel 13, Validation — https://laravel.com/docs/13.x/validation#working-with-validated-input

### SEC-LAR-03 — `$fillable` nunca incluye atributos de privilegio, propiedad o estado financiero
`role`, `is_admin`, `permissions`, `tenant_id`, `team_id`, `user_id`, `email_verified_at`, `balance`, `price`, `status` de pago se asignan explícitamente en código.
*Si no:* un endpoint legítimo que use `validated()` con una regla demasiado laxa, o un arreglo de Livewire, basta para escalar.
*Verificación:* `rg -n -U "(fillable\s*=\s*\[|Fillable\(\[)[^\]]*'(role|is_admin|admin|tenant_id|team_id|user_id|email_verified_at|balance|credits|permissions)'" app`.
*Severidad:* alta
*Fuente:* Laravel 13, Eloquent › Mass Assignment — https://laravel.com/docs/13.x/eloquent#mass-assignment

### SEC-LAR-04 — Las expresiones crudas nunca interpolan ni concatenan variables; los valores van siempre como bindings
Aplica a `DB::raw`, `selectRaw`, `whereRaw`, `orWhereRaw`, `havingRaw`, `orderByRaw`, `groupByRaw`, `DB::select/statement/unprepared`.
*Si no:* inyección SQL: lectura y escritura de toda la base, en todos los tenants.
*Verificación:* `rg -n "(DB::(raw|select|statement|unprepared|insert|update|delete)|(select|where|orWhere|having|orHaving|orderBy|groupBy)Raw)\(\s*(\"[^\"]*(\\$|\{)|'[^']*'\s*\.|\\$)" PHPSRC`.
*Severidad:* crítica
*Fuente:* Laravel 13, Query Builder › Raw Expressions ("Laravel cannot guarantee that any query using raw expressions is protected against SQL injection") — https://laravel.com/docs/13.x/queries#raw-expressions

### SEC-LAR-05 — Los nombres de columna, la dirección de orden y los nombres de relación nunca vienen de la petición sin pasar por una lista blanca
PDO no admite bindings para nombres de columna. Afecta a `orderBy`, `groupBy`, `select`, `pluck`, `with`, `where($columna, …)`.
*Si no:* inyección SQL por nombre de columna, o extracción de columnas ocultas ordenando por ellas (oráculo sobre `password`, `remember_token`).
*Verificación:* `rg -n "(orderBy|orderByDesc|groupBy|select|pluck|with|where|latest|oldest)\(\s*\\$?(request|this->(sort|order|column|field|sortBy|sortField))" PHPSRC` · `rg -n "(orderBy|groupBy)\(\s*\\$" PHPSRC`.
*Severidad:* alta
*Fuente:* Laravel 13, Query Builder › Introduction ("you should never allow user input to dictate the column names referenced by your queries, including order by columns") — https://laravel.com/docs/13.x/queries#introduction

### SEC-LAR-06 — `Rule::unique()->ignore()` nunca recibe un valor controlado por el usuario
Solo el ID de un modelo ya cargado por el servidor.
*Si no:* inyección SQL, documentada por Laravel en la propia regla.
*Verificación:* `rg -n "->ignore\(\s*\\$?(request|this->\w+Id|input)" PHPSRC` · `rg -n "unique:[^'\"]*,\s*'\s*\.\s*\\$request" PHPSRC`.
*Severidad:* alta
*Fuente:* Laravel 13, Validation › unique ("You should never pass any user controlled request input into the ignore method") — https://laravel.com/docs/13.x/validation#rule-unique

### SEC-LAR-07 — `{!! !!}` nunca imprime datos que haya escrito un usuario o que vengan de fuera sin sanear
Para pasar datos a JavaScript se usa `Js::from()` / `@js`, no `{!! json_encode() !!}`. Tener una Markdown renderizada no la hace confiable.
*Si no:* XSS almacenado; con sesión de administrador, toma de la aplicación.
*Verificación:* `rg -n "\{!!" resources/views` — cada resultado se justifica (HTML generado por el servidor, o saneado con una librería tipo HTMLPurifier) · `rg -n "\{!!\s*json_encode|@json\(" resources/views`.
*Severidad:* alta
*Fuente:* Laravel 13, Blade › Displaying Unescaped Data — https://laravel.com/docs/13.x/blade#displaying-unescaped-data · OWASP Laravel Cheat Sheet, XSS — https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html

### SEC-LAR-08 — Toda acción de controlador que lee o modifica un modelo siempre lo autoriza con Policy o Gate
Formas válidas: `Gate::authorize`, `$this->authorize`, `#[Authorize]`, middleware `can:`, `authorizeResource`, o `authorize()` real en el FormRequest. El middleware `auth` solo prueba que hay sesión.
*Si no:* IDOR: cualquier usuario autenticado opera sobre registros ajenos.
*Verificación:* modelos sin Policy: comparar `ls app/Models` con `ls app/Policies` · controladores sin autorización: `rg -L "authorize|Gate::|can\(|#\[Authorize" app/Http/Controllers -g '*.php'` · test por recurso con un segundo usuario que espere 403/404.
*Severidad:* crítica
*Fuente:* Laravel 13, Authorization — https://laravel.com/docs/13.x/authorization · OWASP API1:2023 — https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/

### SEC-LAR-09 — `authorize()` de un FormRequest nunca devuelve `true` si la ruta no tiene otra comprobación de autorización
`return true;` es lo que genera `make:request` y lo que dejan los agentes.
*Si no:* el FormRequest da apariencia de control y la acción queda abierta a cualquier usuario autenticado.
*Verificación:* `rg -n -U "function authorize\(\)[^{]*\{\s*return true;" app/Http/Requests` y cruzar cada request con su ruta y su controlador.
*Severidad:* alta
*Fuente:* Laravel 13, Validation › Authorizing Form Requests — https://laravel.com/docs/13.x/validation#authorizing-form-requests

### SEC-LAR-10 — Las rutas anidadas siempre acotan el modelo hijo al padre con `scopeBindings()` o consultando a través de la relación
Sin clave personalizada, Laravel no acota el hijo: `/teams/{team}/posts/{post}` resuelve cualquier `post`.
*Si no:* IDOR: se autoriza el padre y se opera sobre un hijo de otro dueño.
*Verificación:* `rg -n "\{\w+\}[^'\"]*\{\w+\}" routes/` y comprobar `->scopeBindings()` o `Route::scopeBindings()->group` · `rg -n "withoutScopedBindings" routes/`.
*Severidad:* alta
*Fuente:* Laravel 13, Routing › Implicit Binding › Scoping — https://laravel.com/docs/13.x/routing#implicit-model-binding-scoping

### SEC-LAR-11 — El scope global de tenant nunca se retira con `withoutGlobalScope(s)` sin un comentario que explique por qué y qué filtro lo sustituye
*Si no:* fuga entre tenants: la consulta devuelve o modifica filas de todos los clientes.
*Verificación:* `rg -n "withoutGlobalScopes?\(" app resources/views` — cada resultado necesita justificación y filtro explícito por tenant.
*Severidad:* crítica
*Fuente:* Laravel 13, Eloquent › Removing Global Scopes — https://laravel.com/docs/13.x/eloquent#removing-global-scopes · OWASP Multi-Tenant Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html

### SEC-LAR-12 — Las consultas sobre tablas con tenant nunca pasan por caminos que esquivan el scope global: `DB::table()`, SQL crudo, `exists`/`unique` en validación, y relaciones hacia modelos sin scope
Un scope global solo actúa sobre consultas Eloquent del modelo que lo declara. `Rule::exists('orders','id')` consulta la tabla sin scope.
*Si no:* un usuario referencia por ID un registro de otro tenant y la validación lo da por bueno; o un reporte en SQL crudo mezcla clientes.
*Verificación:* `rg -n "DB::table\(" app resources/views` · `rg -n "(exists|unique):\w+|Rule::(exists|unique)\(" app resources/views` y comprobar `->where('tenant_id', …)` en cada una.
*Severidad:* crítica
*Fuente:* OWASP Multi-Tenant Security Cheat Sheet, §3 Preventing Cross-Tenant Data Access — https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html · Laravel 13, Eloquent › Global Scopes — https://laravel.com/docs/13.x/eloquent#global-scopes

### SEC-LAR-13 — Jobs, comandos de consola, listeners y tareas programadas siempre fijan el tenant de forma explícita; nunca dependen de `auth()` ni de la sesión
En cola y en consola no hay usuario: un scope del tipo `where('tenant_id', auth()->user()->tenant_id)` no filtra o revienta. Con spatie/laravel-permission en modo teams, `setPermissionsTeamId()` también debe fijarse dentro del job.
*Si no:* el job procesa datos de todos los tenants, o de un tenant equivocado que quedó en memoria del worker.
*Verificación:* `rg -n "auth\(\)|Auth::|session\(" app/Jobs app/Console app/Listeners app/Scopes app/Models/Scopes` · test de aislamiento: despachar el job de un tenant y comprobar que no toca filas de otro.
*Severidad:* crítica
*Fuente:* OWASP Multi-Tenant Security Cheat Sheet, §5 API, Asynchronous Work & Resource Controls — https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html · spatie/laravel-permission v8, Teams permissions — https://spatie.be/docs/laravel-permission/v8/basic-usage/teams-permissions

### SEC-LAR-14 — Toda subida de archivo se valida siempre por contenido (`mimes` o `mimetypes`) y por tamaño (`max`); nunca solo por extensión
`extensions:` mira el nombre que eligió el usuario; `mimes:` lee el contenido. `image` excluye SVG por defecto porque puede llevar script. Parche relevante: CVE-2025-27515 (bypass de validación de archivos, corregido en 11.44.1 y 12.1.1).
*Si no:* subida de PHP, HTML o SVG con script; DoS por archivos gigantes.
*Verificación:* `rg -n "'(file|image)'|File::(types|image)\(" app resources/views` y comprobar `mimes`/`mimetypes` y `max` · `rg -n "extensions:" app resources/views | rg -v "mimes|mimetypes"` · `rg -n "allow_svg|image/svg" app resources/views config`.
*Severidad:* alta
*Fuente:* Laravel 13, Validation › extensions / mimes / image — https://laravel.com/docs/13.x/validation#rule-extensions · OWASP File Upload Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

### SEC-LAR-15 — El nombre y la ruta con que se guarda un archivo nunca salen de `getClientOriginalName()` ni `getClientOriginalExtension()`
Se guarda con `store()`/`hashName()`; el nombre original va, si acaso, a una columna para mostrarlo escapado.
*Si no:* path traversal (`../../`), sobrescritura de archivos y doble extensión ejecutable.
*Verificación:* `rg -n "getClientOriginal(Name|Extension)\(" app resources/views` y revisar si el valor llega a `storeAs`, `move`, `putFileAs` o a una ruta.
*Severidad:* alta
*Fuente:* Laravel 13, File Storage › File Uploads ("considered unsafe, as the file name and extension may be tampered with by a malicious user") — https://laravel.com/docs/13.x/filesystem#other-uploaded-file-information

### SEC-LAR-16 — Los archivos privados nunca se guardan en el disco `public` ni con visibilidad pública; se sirven solo por un controlador que autoriza o por URL temporal
`storage:link` publica todo `storage/app/public`. Con medialibrary, la colección declara un disco privado.
*Si no:* documentos, identificaciones o facturas accesibles por URL directa y enumerables.
*Verificación:* `rg -n "disk\('public'\)|store(As|Publicly)?\([^)]*'public'|storePublicly|'visibility'\s*=>\s*'public'|useDisk\('public'\)|toMediaCollection\(" app resources/views config` y clasificar cada archivo como público o privado.
*Severidad:* alta
*Fuente:* Laravel 13, File Storage › The Public Disk — https://laravel.com/docs/13.x/filesystem#the-public-disk · Temporary URLs — https://laravel.com/docs/13.x/filesystem#temporary-urls

### SEC-LAR-17 — Las descargas nunca construyen la ruta con entrada del usuario; el archivo se localiza siempre por ID de registro y se autoriza antes de responder
*Si no:* path traversal: `?file=../../.env` entrega `APP_KEY` y credenciales.
*Verificación:* `rg -n "(Storage::(download|get|path|url|readStream)|response\(\)->(download|file)|file_get_contents|readfile|fopen)\([^)]*\\$(request|this->\w+)" app resources/views`.
*Severidad:* crítica
*Fuente:* OWASP Laravel Cheat Sheet, Path Traversal — https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html

### SEC-LAR-18 — Las rutas a las que se llega por URL firmada siempre llevan el middleware `signed`; los enlaces con efecto sensible usan `temporarySignedRoute`
`hasValidSignatureWhileIgnoring` deja libres los parámetros ignorados. Parche relevante: confusión de ruta en URL firmadas temporales (GHSA-crmm-hgp2-wgrp), corregido en 12.61.1 y 13.12.0.
*Si no:* el enlace de baja, de descarga o de invitación funciona para cualquier ID sin firma, o para siempre.
*Verificación:* por cada `rg -n "URL::(temporary)?[sS]ignedRoute\(" app resources/views`, la ruta nombrada debe tener `->middleware('signed')` o `hasValidSignature()`; `rg -n "hasValidSignatureWhileIgnoring" app`.
*Severidad:* alta
*Fuente:* Laravel 13, URL Generation › Signed URLs — https://laravel.com/docs/13.x/urls#signed-urls · https://github.com/advisories/GHSA-crmm-hgp2-wgrp

### SEC-LAR-19 — En producción `APP_DEBUG` siempre es `false` y `APP_ENV` siempre es `production`
Parche relevante: XSS en la página de depuración (CVE-2026-102279, corregido en 12.69.0 y 13.30.0).
*Si no:* la página de error muestra variables de entorno, credenciales, consultas y código fuente.
*Verificación:* en el servidor: `php artisan about --only=environment` · en el repo: `rg -n "APP_DEBUG=true|'debug'\s*=>\s*true" .env.example .env.production config deploy* docker* 2>/dev/null` · petición a una ruta que falle y revisar el cuerpo.
*Severidad:* crítica
*Fuente:* Laravel 13, Configuration › Debug Mode ("In your production environment, this value should always be false") — https://laravel.com/docs/13.x/configuration#debug-mode

### SEC-LAR-20 — `APP_KEY` y los archivos `.env` nunca se suben al repositorio sin cifrar, y una llave expuesta siempre se rota
La llave firma cookies, sesiones, URL firmadas, snapshots de Livewire y, desde Livewire 4, deriva el hash de sus endpoints. Para rotar sin cerrar sesiones existe `APP_PREVIOUS_KEYS`.
*Si no:* con `APP_KEY` se falsifican cookies y URL firmadas y, si hay deserialización PHP de datos firmados, se llega a ejecución remota de código (por eso Laravel 13 endureció caché y sesión, ver SEC-LAR-26).
*Verificación:* `git log --all --diff-filter=A --name-only --pretty=format: | rg "^\.env($|\.)" | rg -v "example|encrypted"` · `git grep -n "APP_KEY=base64:" $(git rev-list --all) -- . | head` · `rg -n "^\.env" .gitignore`.
*Severidad:* crítica
*Fuente:* Laravel 13, Configuration › Environment File Security — https://laravel.com/docs/13.x/configuration#environment-file-security · Encryption › Gracefully Rotating Encryption Keys — https://laravel.com/docs/13.x/encryption#gracefully-rotating-encryption-keys

### SEC-LAR-21 — La cookie de sesión siempre lleva `secure`, `http_only` y `same_site` (`lax` o `strict`) en producción
*Si no:* robo de sesión por XSS (`http_only`), por red sin TLS (`secure`), y CSRF en navegadores sin `Sec-Fetch-Site` (`same_site`).
*Verificación:* `rg -n "'(secure|http_only|same_site|encrypt)'" config/session.php` · `rg -n "SESSION_SECURE_COOKIE|SESSION_SAME_SITE|SESSION_ENCRYPT" .env.example` · `curl -sI https://<host>/login | rg -i set-cookie`.
*Severidad:* alta
*Fuente:* OWASP Laravel Cheat Sheet, Cookie Security and Session Management — https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html

### SEC-LAR-22 — El límite de intentos de login nunca se desactiva, y toda ruta de autenticación propia lleva siempre su `throttle`
Fortify limita por usuario+IP con `EnsureLoginIsNotThrottled`, salvo que `fortify.limiters.login` apunte a un limitador inexistente o demasiado amplio. El endpoint de token para móvil (`/sanctum/token` del ejemplo oficial) no trae límite.
*Si no:* fuerza bruta y credential stuffing sin freno, sobre todo por el endpoint de la app móvil.
*Verificación:* `rg -n "limiters" config/fortify.php` · `rg -n "RateLimiter::for\('(login|two-factor|passkeys)'" app` · `rg -n "sanctum/token|login|createToken" routes app/Http` y confirmar `throttle:`.
*Severidad:* alta
*Fuente:* Laravel 13, Fortify › Authentication Throttling — https://laravel.com/docs/13.x/fortify#customizing-the-authentication-pipeline · Authentication › Login Throttling — https://laravel.com/docs/13.x/authentication#login-throttling

### SEC-LAR-23 — Los tokens de Sanctum siempre tienen caducidad configurada y poda programada
Por defecto no caducan nunca. Se fija `sanctum.expiration` o el tercer argumento de `createToken`, y se agenda `sanctum:prune-expired`.
*Si no:* un token filtrado de un teléfono perdido o de un log vale para siempre.
*Verificación:* `rg -n "'expiration'\s*=>\s*null" config/sanctum.php` · `rg -n "createToken\(" app` · `rg -n "sanctum:prune-expired" routes bootstrap app`.
*Severidad:* alta
*Fuente:* Laravel 13, Sanctum › Token Expiration ("By default, Sanctum tokens never expire") — https://laravel.com/docs/13.x/sanctum#token-expiration

### SEC-LAR-24 — Los tokens de Sanctum nunca se emiten con la habilidad `*` cuando la API tiene operaciones de distinto privilegio, y las rutas sensibles siempre comprueban la habilidad
`createToken($nombre)` sin segundo argumento otorga `['*']`. `tokenCan()` devuelve siempre `true` para peticiones del SPA propio: la habilidad no sustituye a la Policy.
*Si no:* el token de la app móvil sirve también para operaciones administrativas o de terceros.
*Verificación:* `rg -n "createToken\(\s*[^,)]+\)" app` (sin habilidades) · `rg -n "abilities:|ability:|tokenCan\(" routes app`.
*Severidad:* media
*Fuente:* Laravel 13, Sanctum › Token Abilities — https://laravel.com/docs/13.x/sanctum#token-abilities

### SEC-LAR-25 — El SPA propio nunca se autentica con tokens de API; usa siempre la sesión por cookie de Sanctum con dominios `stateful` exactos
Laravel lo indica de forma expresa. Los tokens son para móvil y terceros.
*Si no:* el token acaba en `localStorage` y cualquier XSS lo exfiltra; con `stateful` o CORS con comodín, otro origen usa la sesión.
*Verificación:* `rg -n "stateful" config/sanctum.php` · `rg -n "SANCTUM_STATEFUL_DOMAINS" .env.example` · en el frontend: `rg -n "localStorage\.(set|get)Item\(['\"](token|access_token|auth)" JSSRC`.
*Severidad:* alta
*Fuente:* Laravel 13, Sanctum › API Token Authentication ("You should not use API tokens to authenticate your own first-party SPA") y SPA Authentication — https://laravel.com/docs/13.x/sanctum#api-token-authentication

### SEC-LAR-26 — Nunca se llama a `unserialize()` sobre datos que el usuario pueda alterar, y la caché y la sesión siempre restringen las clases deserializables
PHP advierte que `allowed_classes` no basta frente a entrada no confiable. Laravel 13 trae `cache.serializable_classes => false` y `session.serialization => 'json'` para cortar cadenas de gadgets si se filtra `APP_KEY`; una app migrada desde la 12 conserva los valores antiguos.
*Si no:* inyección de objetos PHP y ejecución remota de código.
*Verificación:* `rg -n "\bunserialize\(" app resources/views` · `rg -n "serializable_classes" config/cache.php` · `rg -n "'serialization'" config/session.php`.
*Severidad:* crítica
*Fuente:* PHP Manual, unserialize — https://www.php.net/manual/en/function.unserialize.php · Laravel 13, Upgrade Guide › Cache `serializable_classes` y Session `serialization` — https://laravel.com/docs/13.x/upgrade

### SEC-LAR-27 — Un job nunca lleva secretos ni datos sensibles en claro en su payload; si los necesita implementa siempre `ShouldBeEncrypted`
El payload se guarda en Redis o en la tabla `jobs`, y completo en `failed_jobs`. Lo normal es pasar el ID y releer.
*Si no:* contraseñas, tokens o datos de tarjeta legibles en la cola, en Horizon y en los respaldos de la base.
*Verificación:* `rg -n "(password|token|secret|card|cvv|ssn|curp|rfc)" app/Jobs app/Notifications app/Mail -i` y comprobar `ShouldBeEncrypted` en la clase · `rg -L "ShouldBeEncrypted" app/Jobs`.
*Severidad:* media
*Fuente:* Laravel 13, Queues › Encrypted Jobs — https://laravel.com/docs/13.x/queues#encrypted-jobs

### SEC-LAR-28 — Los logs nunca reciben la petición completa, contraseñas, tokens ni PII
*Si no:* credenciales y datos personales en `storage/logs`, en el agregador y en Sentry, con retención y accesos que nadie decidió.
*Verificación:* `rg -n "(Log::\w+|logger|info|report)\([^;]*(\\$request->(all|input)\(\)|password|token|authorization|->toArray\(\))" app resources/views -i` · `rg -n "send_default_pii" config/sentry.php` (debe ser `false`).
*Severidad:* media
*Fuente:* OWASP Logging Cheat Sheet, "Data to exclude" — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html · Sentry para Laravel, Scrubbing Sensitive Data — https://docs.sentry.io/platforms/php/guides/laravel/data-management/sensitive-data/

### SEC-LAR-29 — Telescope, Horizon, Pulse y Debugbar nunca son accesibles en producción sin un gate restrictivo; Debugbar y Telescope de uso local van siempre en `require-dev`
Telescope guarda peticiones completas, consultas y correos. El gate por defecto solo protege fuera de `local`: si `APP_ENV` está mal, queda abierto.
*Si no:* cualquiera lee peticiones con contraseñas, tokens y datos de todos los usuarios; desde Horizon se reintentan o borran jobs.
*Verificación:* `jq '.require | keys[]' composer.json | rg "debugbar|telescope"` · `rg -n "viewTelescope|viewHorizon|viewPulse" app/Providers` y leer el cierre · `curl -s -o /dev/null -w '%{http_code}' https://<host>/{telescope,horizon,pulse,_debugbar/open}` sin sesión debe dar 403/404.
*Severidad:* crítica
*Fuente:* Laravel 13, Telescope › Dashboard Authorization y Local Only Installation — https://laravel.com/docs/13.x/telescope#dashboard-authorization · Horizon › Dashboard Authorization — https://laravel.com/docs/13.x/horizon#dashboard-authorization

### SEC-LAR-30 — Las excepciones a la protección CSRF solo cubren webhooks que verifican firma; nunca un comodín amplio ni rutas con sesión
En Laravel 13 la verificación por origen (`Sec-Fetch-Site`) solo funciona sobre HTTPS; sin HTTPS se cae al token.
*Si no:* CSRF sobre las rutas excluidas; con `except: ['*']` o `api/*` bajo sesión, sobre toda la aplicación.
*Verificación:* `rg -n -U "(preventRequestForgery|validateCsrfTokens)\((.|\n){0,200}except" bootstrap/app.php` y comprobar que cada URI excluida tiene verificación de firma (SEC-INT-01) · `rg -n "originOnly|allowSameSite" bootstrap/app.php`.
*Severidad:* alta
*Fuente:* Laravel 13, CSRF Protection › Excluding URIs y Origin Verification — https://laravel.com/docs/13.x/csrf#csrf-excluding-uris

### SEC-LAR-31 — Con spatie/laravel-permission la autorización siempre se comprueba en el servidor por permiso (`can`, Policy, middleware); `@role` y `@can` en Blade solo deciden qué se pinta
Con teams activado, el middleware que llama a `setPermissionsTeamId()` debe ejecutarse antes de `SubstituteBindings`.
*Si no:* el botón no aparece pero la ruta o la acción de Livewire responde igual a quien la invoque; con el team mal fijado, permisos de otro equipo.
*Verificación:* por cada `rg -n "@(role|hasrole|hasanyrole|can)\b" resources/views`, la acción que protege debe tener su comprobación en servidor · `rg -n "setPermissionsTeamId" app`.
*Severidad:* alta
*Fuente:* spatie/laravel-permission v8, Teams permissions — https://spatie.be/docs/laravel-permission/v8/basic-usage/teams-permissions · OWASP API5:2023 — https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/

### SEC-LAR-32 — Un proyecto nunca corre en una versión de Laravel sin parches de seguridad ni con avisos abiertos en `composer audit`
Al 2026-10-02: Laravel 11 está fuera de soporte desde 2026-03-12 y no recibió los parches de 2026 (inyección CRLF en la regla `email`, GHSA-5vg9-5847-vvmq; URL firmadas, GHSA-crmm-hgp2-wgrp; XSS en página de depuración, CVE-2026-102279). Mínimos: Laravel ≥ 12.69.0 o ≥ 13.30.0; medialibrary ≥ 11.23.0 (CVE-2026-48557, CVE-2026-48555).
*Si no:* vulnerabilidades públicas explotables sin que exista parche para esa rama.
*Verificación:* `composer audit --locked` · `composer show laravel/framework livewire/livewire spatie/laravel-medialibrary | rg "^(name|versions)"` · Pest: `arch()->preset()->security();` en la suite.
*Severidad:* alta
*Fuente:* Laravel 13, Release Notes › Support Policy — https://laravel.com/docs/13.x/releases#support-policy · GitHub Advisory Database — https://github.com/advisories?query=laravel%2Fframework · Pest, Arch Testing › Presets — https://pestphp.com/docs/arch-testing

---

## LW — Livewire 3 y 4 (incluye componentes de archivo único)

Alcance de los patrones: `app/Livewire resources/views` (en adelante `LWSRC`). En Livewire 4 la clase puede estar dentro de un `.blade.php`.

### SEC-LW-01 — Una propiedad pública que guarda un ID u otro dato que el cliente no debe cambiar siempre lleva `#[Locked]`, o se sustituye por una propiedad tipada con el modelo
Las propiedades públicas se manipulan desde DevTools aunque no exista ningún `wire:model`. Livewire bloquea por sí solo las propiedades que son modelos Eloquent.
*Si no:* IDOR: el usuario cambia `postId`, `userId` o `tenantId` y la siguiente acción opera sobre el registro de otro.
*Verificación:* `rg -n "public\s+(\??int|\??string|\$)\s*\$?\w*(Id|_id|Uuid|uuid)\b" LWSRC` y comprobar `#[Locked]` en la línea anterior: `rg -n -B1 "public .*\\$\w*(Id|_id)\b" LWSRC | rg -v "Locked"`.
*Severidad:* crítica
*Fuente:* Livewire 4, Security › Authorizing public properties — https://livewire.laravel.com/docs/4.x/security · Locked — https://livewire.laravel.com/docs/4.x/attribute-locked

### SEC-LW-02 — Cada acción de un componente siempre autoriza por sí misma; la comprobación en `mount()` no cubre las llamadas posteriores
`mount()` corre una vez. Las acciones llegan después por el endpoint de actualización, con los permisos que el usuario tenga en ese momento. `#[Locked]` impide el cambio desde el cliente, no autoriza.
*Si no:* un usuario que perdió el permiso, o que nunca pasó por la interfaz prevista, ejecuta `delete`, `update` o `approve`.
*Verificación:* componentes con acciones de escritura sin autorización: `rg -l "->(delete|update|save|create|forceDelete|restore|attach|detach|sync)\(" LWSRC | xargs rg -L "authorize\(|Gate::|->can\(|abort_(if|unless)"` · test Livewire con otro usuario: `Livewire::actingAs($otro)->test(...)->call('delete')->assertForbidden()`.
*Severidad:* crítica
*Fuente:* Livewire 4, Actions › Security concerns ("Always authorize server-side") — https://livewire.laravel.com/docs/4.x/actions#security-concerns

### SEC-LW-03 — Los parámetros de una acción siempre se tratan como entrada del usuario y se autorizan contra el registro cargado
`wire:click="delete({{ $post->id }})"` no garantiza nada: el método se invoca desde la consola con cualquier argumento.
*Si no:* IDOR directo por parámetro.
*Verificación:* `rg -n "public function \w+\((int |string |\\$)\w*[iI]d\b" LWSRC` y leer el cuerpo de cada método.
*Severidad:* crítica
*Fuente:* Livewire 4, Actions › "Always authorize action parameters" — https://livewire.laravel.com/docs/4.x/actions#security-concerns · Security › Authorizing action parameters — https://livewire.laravel.com/docs/4.x/security

### SEC-LW-04 — Un método que no es una acción de interfaz nunca es `public`
Todo método público es invocable desde el navegador, esté o no en la plantilla.
*Si no:* el cliente llama a auxiliares internos (`deleteRecord`, `setRole`, `markAsPaid`) saltándose la acción que sí autorizaba.
*Verificación:* listar métodos públicos y cruzarlos con la plantilla: `rg -n "public function (?!mount|render|boot|booted|hydrate|dehydrate|updat|rules|messages|validationAttributes|placeholder|with|layout|title|paginationView)\w+" --pcre2 LWSRC`; los que no aparezcan en ningún `wire:` ni `$wire.` pasan a `protected`.
*Severidad:* alta
*Fuente:* Livewire 4, Actions › "Keep dangerous methods protected or private" — https://livewire.laravel.com/docs/4.x/actions#security-concerns

### SEC-LW-05 — Una propiedad pública nunca contiene secretos, datos de otros usuarios ni valores que el servidor deba decidir
Las propiedades se deshidratan y viajan al navegador en el snapshot, que va firmado pero no cifrado. Precio, total, descuento, rol y estado se recalculan en el servidor.
*Si no:* fuga de datos por el HTML de la página; manipulación de importes o de banderas si el valor se usa sin recalcular.
*Verificación:* `rg -n "public\s+[^;(]*\\$(\w*(password|secret|token|apiKey|api_key|price|total|amount|discount|role|isAdmin|is_admin)\w*)" -i LWSRC` · inspeccionar `wire:snapshot` en el HTML renderizado.
*Severidad:* alta
*Fuente:* Livewire 4, Properties › Security concerns ("always treat public properties as user input" y "Properties expose system information to the browser") — https://livewire.laravel.com/docs/4.x/properties#security-concerns

### SEC-LW-06 — Lo que se persiste desde un componente siempre es el resultado de `validate()`; nunca `$this->all()`, `$this->only()` sin validar ni un arreglo público completo
Un arreglo público (`public array $form`) acepta desde el cliente claves que la vista no tiene: `form.is_admin`, `form.tenant_id`.
*Si no:* asignación masiva a través de Livewire, aunque el controlador equivalente estuviera protegido.
*Verificación:* `rg -n "(create|update|fill|forceFill)\(\s*\\$this->(all\(\)|form|data|state|only\(|except\()" LWSRC` · `rg -n "->(create|update)\(\\$this->\w+\)" LWSRC`.
*Severidad:* crítica
*Fuente:* Livewire 4, Properties › "Don't trust property values" — https://livewire.laravel.com/docs/4.x/properties#security-concerns · OWASP API3:2023 — https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/

### SEC-LW-07 — `wire:model` nunca se enlaza directamente a atributos de privilegio ni a campos que el usuario no deba fijar
Rol, permisos, propietario, tenant, estado de verificación o de pago. Si un administrador los edita, la acción de guardado autoriza ese cambio en concreto.
*Si no:* escalada de privilegios desde el propio formulario de perfil.
*Verificación:* `rg -n "wire:model(\.\w+)*=\"[^\"]*(role|is_admin|permission|tenant_id|team_id|user_id|owner_id|verified|status)\w*\"" resources/views`.
*Severidad:* alta
*Fuente:* Livewire 4, Properties › Security concerns — https://livewire.laravel.com/docs/4.x/properties#security-concerns

### SEC-LW-08 — Toda propiedad de subida de archivos siempre se valida con `mimes`/`mimetypes` y `max` antes de guardarse, y el nombre final nunca sale de `getClientOriginalName()`
Las reglas globales por defecto son solo `file|max:12288`. El endpoint temporal trae `throttle:60,1`; no se elimina. Mínimo parcheado: Livewire ≥ 3.5.2 (CVE-2024-47823, RCE por subida).
*Si no:* subida de ejecutables o HTML al disco, path traversal en el nombre, saturación del almacenamiento.
*Verificación:* componentes con `WithFileUploads`: `rg -l "WithFileUploads" LWSRC | xargs rg -L "mimes|mimetypes|image"` · `rg -n "getClientOriginalName\(\)|storeAs\(" LWSRC` · `rg -n "temporary_file_upload" -A8 config/livewire.php`.
*Severidad:* alta
*Fuente:* Livewire 4, File Uploads › File validation y Global validation — https://livewire.laravel.com/docs/4.x/uploads · https://github.com/advisories/GHSA-f3cx-396f-7jqp

### SEC-LW-09 — Un modal de wire-elements siempre autoriza en `mount()` y otra vez en cada acción; sus argumentos nunca se dan por confiables
`openModal` se despacha desde el navegador con el nombre de cualquier componente modal registrado y con argumentos arbitrarios. El README usa `Gate::authorize` en `mount()` y en `update()`.
*Si no:* cualquier usuario abre `edit-user` con el ID de otro, ve sus datos y los guarda.
*Verificación:* `rg -l "extends ModalComponent" app resources/views | xargs rg -L "authorize\(|Gate::"` · por cada modal, test que lo monte con un registro ajeno y espere 403.
*Severidad:* crítica
*Fuente:* wire-elements/modal, README › Passing parameters y Security — https://github.com/wire-elements/modal#security

### SEC-LW-10 — Del arreglo que entrega livewire-dropzone nunca se usan `path`, `name` ni `extension` para leer o guardar; el archivo siempre se resuelve por `tmpFilename` y se revalida en el servidor
En el código del paquete (v3.0.1), `files` es `#[Modelable]` y no está bloqueada; cada elemento trae `tmpFilename`, `name`, `extension` y `path`. El cliente puede reescribirlos. No hay aviso de seguridad publicado: esta regla sale de leer el código fuente.
*Si no:* lectura arbitraria de archivos del servidor: se cambia `path` a `/var/www/.env` y el componente padre lo copia al disco público o lo adjunta.
*Verificación:* `rg -n "\\$(file|photo|document|attachment)\['(path|name|extension)'\]|\['path'\]" LWSRC app` y seguir el valor hasta `Storage::put`, `copy`, `file_get_contents`, `addMedia`, `attach`.
*Severidad:* crítica
*Fuente:* dasundev/livewire-dropzone, `src/Http/Livewire/Dropzone.php` — https://github.com/dasundev/livewire-dropzone/blob/main/src/Http/Livewire/Dropzone.php · Livewire 4, Properties › Security concerns — https://livewire.laravel.com/docs/4.x/properties#security-concerns

### SEC-LW-11 — Un listener (`#[On]`) y una propiedad `#[Url]` siempre se tratan como entrada del cliente
Los eventos se despachan desde la consola con cualquier payload; `#[Url]` se rellena desde la cadena de consulta.
*Si no:* IDOR o cambio de estado a través de un evento que se creía interno; filtros y ordenaciones inyectados por la URL (ver SEC-LAR-05).
*Verificación:* `rg -n -A6 "#\[On\(" LWSRC` y comprobar autorización en cada listener · `rg -n -A2 "#\[Url" LWSRC` y seguir el uso de la propiedad.
*Severidad:* alta
*Fuente:* Livewire 4, Actions › Security concerns — https://livewire.laravel.com/docs/4.x/actions#security-concerns · URL Query Parameters — https://livewire.laravel.com/docs/4.x/url

### SEC-LW-12 — Un middleware propio de autenticación, rol o tenant siempre se registra como persistente, y un `setUpdateRoute` personalizado nunca pierde el grupo `web` ni el parámetro `$path`
Livewire solo reaplica en las peticiones de actualización una lista fija de middleware; los propios hay que añadirlos con `addPersistentMiddleware` (sin argumentos: no se admiten). En Livewire 4 la ruta lleva hash y hay que usar `$path`.
*Si no:* la página inicial pasa por el middleware de tenant o de rol y las actualizaciones posteriores no: el contexto se pierde o se salta.
*Verificación:* `rg -n "addPersistentMiddleware|setUpdateRoute" app bootstrap routes` y comparar con los middleware propios aplicados a rutas Livewire (`rg -n "Route::livewire|Livewire\\\\" routes`).
*Severidad:* alta
*Fuente:* Livewire 4, Security › Middleware — https://livewire.laravel.com/docs/4.x/security#middleware · Upgrade Guide › Livewire Asset and Endpoint URL Changes — https://livewire.laravel.com/docs/4.x/upgrading

### SEC-LW-13 — Livewire nunca se queda por debajo de 3.8.3 (rama 3) ni de 4.3.4 (rama 4)
CVE-2025-54068: ejecución remota de comandos en la hidratación de propiedades, 3.x < 3.6.4, crítica. CVE-2026-81887: XSS basado en DOM, ≤ 3.8.2 y ≤ 4.3.3.
*Si no:* ejecución remota de comandos sin autenticación en ciertos componentes (< 3.6.4) y ejecución de JavaScript en el origen de la aplicación (≤ 3.8.2, ≤ 4.3.3).
*Verificación:* `composer show livewire/livewire | rg versions` · `composer audit --locked`.
*Severidad:* crítica
*Fuente:* GitHub Advisory Database — https://github.com/advisories/GHSA-29cq-5w36-x7w3 · https://github.com/advisories/GHSA-g3hc-697w-wm82

---

## GO — net/http o router ligero, contrato OpenAPI

### SEC-GO-01 — El servidor HTTP siempre se crea como `http.Server` con `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout` e `IdleTimeout`; nunca con `http.ListenAndServe` a secas
En `net/http` un timeout en cero significa "sin límite".
*Si no:* Slowloris: unas pocas conexiones lentas agotan los descriptores y tumban el servicio.
*Verificación:* `rg -n "http\.ListenAndServe(TLS)?\(" -g '*.go'` · `rg -n -A8 "&?http\.Server\{" -g '*.go'` y comprobar los cuatro campos · `gosec -include=G112,G114 ./...`.
*Severidad:* alta
*Fuente:* Go, `net/http` › type Server ("A zero or negative value means there will be no timeout") — https://pkg.go.dev/net/http#Server

### SEC-GO-02 — Toda llamada HTTP saliente usa siempre un `http.Client` con `Timeout` o un contexto con plazo; nunca `http.Get`, `http.Post` ni `http.DefaultClient`
`DefaultClient` no tiene timeout.
*Si no:* un tercero que no responde retiene goroutines y conexiones hasta agotar el proceso.
*Verificación:* `rg -n "http\.(Get|Post|PostForm|Head)\(|http\.DefaultClient|&http\.Client\{\s*\}" -g '*.go'`.
*Severidad:* media
*Fuente:* Go, `net/http` › type Client ("A Timeout of zero means no timeout") — https://pkg.go.dev/net/http#Client · OWASP API10:2023 — https://api-security.owasp.org/editions/2023/en/0xaa-unsafe-consumption-of-apis/

### SEC-GO-03 — Todo handler que lee el cuerpo siempre lo envuelve en `http.MaxBytesReader`, y el decodificador JSON rechaza campos desconocidos y decodifica sobre un struct de entrada propio
El struct de entrada nunca es el modelo de base de datos. `DisallowUnknownFields()` hace visible el intento de asignación masiva.
*Si no:* agotamiento de memoria con cuerpos de varios gigas; asignación masiva si se decodifica directo sobre el modelo (`Role`, `TenantID`).
*Verificación:* `rg -n "json\.NewDecoder\(r\.Body\)|io\.ReadAll\(r\.Body\)" -g '*.go'` y comprobar `MaxBytesReader` (o `http.MaxBytesHandler` global) antes · `rg -n "DisallowUnknownFields" -g '*.go'` · `rg -n "Decode\(&\w*(model|entity|db)\." -i -g '*.go'`.
*Severidad:* alta
*Fuente:* Go, `net/http` › MaxBytesReader — https://pkg.go.dev/net/http#MaxBytesReader · OWASP API4:2023 y API3:2023 — https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/

### SEC-GO-04 — El HTML siempre se genera con `html/template`; nunca con `text/template`, `fmt.Fprintf` ni convirtiendo entrada a `template.HTML`
`html/template` supone que el autor de la plantilla es de confianza y los datos no; `template.HTML`, `template.JS` y `template.URL` desactivan el escape.
*Si no:* XSS reflejado o almacenado.
*Verificación:* `rg -n "\"text/template\"" -g '*.go'` · `rg -n "template\.(HTML|JS|JSStr|URL|CSS|HTMLAttr)\(" -g '*.go'` · `rg -n "fmt\.Fp?rintf?\(w,.*<" -g '*.go'` · `gosec -include=G203 ./...`.
*Severidad:* alta
*Fuente:* Go, `html/template` › Security Model — https://pkg.go.dev/html/template#hdr-Security_Model

### SEC-GO-05 — Las consultas SQL nunca se arman con `fmt.Sprintf` ni con concatenación; los valores van siempre como parámetros
Para nombres de columna y orden, lista blanca en código.
*Si no:* inyección SQL.
*Verificación:* `rg -n "(Query|QueryRow|Exec|QueryContext|QueryRowContext|ExecContext|Raw)\(\s*(ctx,\s*)?(fmt\.Sprintf|\w+\s*\+|\"[^\"]*\"\s*\+)" -g '*.go'` · `rg -n "fmt\.Sprintf\(\"[^\"]*(SELECT|INSERT|UPDATE|DELETE|WHERE|ORDER BY)" -i -g '*.go'` · `gosec -include=G201,G202 ./...`.
*Severidad:* crítica
*Fuente:* Go, Avoiding SQL injection risk — https://go.dev/doc/database/sql-injection

### SEC-GO-06 — `os/exec` nunca invoca un shell con entrada del usuario; el programa es fijo y los argumentos van siempre separados
`exec.Command` no pasa por el shell, pero `exec.Command("sh", "-c", cadena)` sí.
*Si no:* inyección de comandos.
*Verificación:* `rg -n "exec\.Command(Context)?\(\s*(ctx,\s*)?\"(sh|bash|zsh|cmd|powershell)\"" -g '*.go'` · `rg -n "exec\.Command(Context)?\(" -g '*.go'` y revisar que el primer argumento sea literal · `gosec -include=G204 ./...`.
*Severidad:* crítica
*Fuente:* Go, `os/exec` ("intentionally does not invoke the system shell") — https://pkg.go.dev/os/exec · OWASP OS Command Injection Defense Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html

### SEC-GO-07 — Una ruta de archivo nunca se forma uniendo un directorio base con entrada del usuario; el acceso se confina siempre con `os.Root` o `fs.FS`
`filepath.Join(base, r.URL.Path)` no impide `..`. `http.Dir` sigue enlaces simbólicos y sirve archivos que empiezan por punto (`.git`, `.env`).
*Si no:* lectura o escritura de archivos fuera del directorio previsto; exposición de `.env` y del repositorio.
*Verificación:* `rg -n "filepath\.Join\([^)]*(r\.|req\.|c\.|param|name|file)" -i -g '*.go'` · `rg -n "http\.(Dir|FileServer|ServeFile)\(|os\.(Open|ReadFile|Create|WriteFile)\(" -g '*.go'` · `rg -n "os\.OpenRoot" -g '*.go'` · `gosec -include=G304,G305 ./...`.
*Severidad:* alta
*Fuente:* Go, `net/http` › type Dir ("Dir could expose sensitive files and directories") — https://pkg.go.dev/net/http#Dir · `os` › type Root — https://pkg.go.dev/os#Root

### SEC-GO-08 — La respuesta al cliente nunca contiene `err.Error()`; el error interno va siempre al log y al cliente un mensaje genérico
*Si no:* fuga de consultas SQL, rutas de archivos, nombres de host internos y mensajes del driver.
*Verificación:* `rg -n "http\.Error\(w,\s*(err\.Error\(\)|fmt\.Sprint)" -g '*.go'` · `rg -n "\"error\":\s*err\.Error\(\)|Message:\s*err\.Error\(\)" -g '*.go'`.
*Severidad:* media
*Fuente:* OWASP API8:2023 — https://api-security.owasp.org/editions/2023/en/0xa8-security-misconfiguration/ · OWASP Go Secure Coding Practices (Error Handling and Logging) — https://owasp.org/www-project-go-secure-coding-practices-guide/

### SEC-GO-09 — Al validar un JWT siempre se fija la lista de algoritmos con `jwt.WithValidMethods`, se exige `exp` y se comprueban emisor y audiencia; `UnsafeAllowNoneSignatureType` nunca aparece
La `Keyfunc` debe comprobar además el tipo del método antes de devolver la llave.
*Si no:* confusión de algoritmo o `alg: none`: tokens falsificados aceptados como válidos.
*Verificación:* `rg -n "jwt\.(Parse|ParseWithClaims)\(" -g '*.go' | rg -v "WithValidMethods"` · `rg -n "UnsafeAllowNoneSignatureType|SigningMethodNone|ParseUnverified" -g '*.go'` · `rg -n "WithExpirationRequired|WithIssuer|WithAudience" -g '*.go'`.
*Severidad:* crítica
*Fuente:* golang-jwt/jwt v5 ("SECURITY NOTICE: It's important that you validate the alg presented is what you expect") — https://pkg.go.dev/github.com/golang-jwt/jwt/v5 · RFC 8725 §3.1 — https://www.rfc-editor.org/rfc/rfc8725

### SEC-GO-10 — El middleware CORS nunca devuelve el `Origin` recibido junto con `Access-Control-Allow-Credentials: true`; solo orígenes de una lista exacta
La librería estándar no trae CORS: suele escribirse a mano, y mal. Para peticiones con cookie, Go ≥ 1.25 ofrece `http.CrossOriginProtection` contra CSRF.
*Si no:* cualquier sitio lee respuestas autenticadas de la API.
*Verificación:* `rg -n "Access-Control-Allow-(Origin|Credentials)|AllowAllOrigins|AllowOriginFunc|AllowedOrigins" -g '*.go'` y leer la lógica · prueba: `curl -sI -H 'Origin: https://evil.example' https://<api>/` no debe reflejarlo.
*Severidad:* alta
*Fuente:* OWASP REST Security Cheat Sheet (CORS) — https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html · Go, `net/http` › CrossOriginProtection — https://pkg.go.dev/net/http#CrossOriginProtection

### SEC-GO-11 — Las rutas se registran siempre bajo un grupo con middleware de autenticación; una ruta fuera del grupo solo existe si está en la lista pública y en el contrato OpenAPI sin `security`
*Si no:* el handler nuevo queda público por omisión: en `net/http` nada obliga a envolverlo.
*Verificación:* `rg -n "\.(HandleFunc|Handle|Get|Post|Put|Patch|Delete)\(\"" -g '*.go'` y clasificar cada registro como dentro o fuera del grupo autenticado; test que recorra todas las rutas sin credenciales y espere 401 salvo las de la lista.
*Severidad:* crítica
*Fuente:* OWASP API2:2023 y API5:2023 — https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/

### SEC-GO-12 — El estado compartido entre goroutines siempre se protege con mutex, canal o tipos atómicos, y la CI siempre ejecuta `go test -race`
Mapas globales, cachés en memoria, contadores de rate limit, sesiones. Un mapa escrito en concurrencia aborta el proceso. El detector solo ve carreras en rutas que se ejecutan.
*Si no:* corrupción de datos, comprobaciones de autorización o de saldo con carrera (TOCTOU), caída del proceso.
*Verificación:* `go test -race ./...` en CI (`rg -n "\-race" .github Makefile *.yml`) · `rg -n "^var \w+\s*=\s*(map\[|make\(map)" -g '*.go'` y buscar su mutex.
*Severidad:* alta
*Fuente:* Go, Security Best Practices › Check for race conditions — https://go.dev/doc/security/best-practices · Data Race Detector — https://go.dev/doc/articles/race_detector

---

## JS — Nuxt, Vue, React, Node, TypeScript

### SEC-JS-01 — `v-html`, `dangerouslySetInnerHTML` e `innerHTML` nunca reciben contenido de usuarios o de terceros sin sanear con una librería de lista blanca
Vue: el HTML de usuario "nunca puede considerarse 100 % seguro". React: es "trivial introducir un XSS" así.
*Si no:* XSS; con el token en `localStorage`, robo de sesión inmediato.
*Verificación:* `rg -n "v-html|dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write\(" JSSRC resources/js` — cada resultado necesita `DOMPurify.sanitize` (o equivalente) a la vista.
*Severidad:* alta
*Fuente:* Vue, Security › HTML Injection — https://vuejs.org/guide/best-practices/security · React, `dangerouslySetInnerHTML` — https://react.dev/reference/react-dom/components/common#dangerously-setting-the-inner-html

### SEC-JS-02 — Un secreto nunca va en variables que se empaquetan para el cliente: `runtimeConfig.public`, `NUXT_PUBLIC_*`, `VITE_*`, `NEXT_PUBLIC_*`
Nuxt añade `runtimeConfig.public` al payload de cada página; Vite y Next incrustan el valor en el bundle al compilar. Los secretos van en `runtimeConfig` privado y se usan solo en `server/`.
*Si no:* la llave se lee en el código fuente del navegador.
*Verificación:* `rg -n "(VITE_|NEXT_PUBLIC_|NUXT_PUBLIC_)\w*(SECRET|PRIVATE|PASSWORD|TOKEN|KEY)" . -g '!node_modules' -g '.env*'` · `rg -n -A15 "public:\s*\{" nuxt.config.*` · sobre el artefacto: `rg -n "sk_live|os_v2_|AKIA|sntrys_|whsec_" .output dist`.
*Severidad:* crítica
*Fuente:* Nuxt 4, Runtime Config ("Keys within public, will be also exposed to the client-side") — https://nuxt.com/docs/4.x/guide/going-further/runtime-config · Vite, Env Variables ("VITE_* variables should not contain sensitive information") — https://vite.dev/guide/env-and-mode · Next.js, Environment Variables — https://nextjs.org/docs/app/guides/environment-variables

### SEC-JS-03 — Una URL aportada por un usuario nunca se enlaza a `href`, `src` o a una navegación sin validar que su esquema es `http` o `https`
Vue lo deja al backend: la URL se sanea antes de guardarse.
*Si no:* XSS por `javascript:` al hacer clic; `data:` con contenido activo.
*Verificación:* `rg -n ":href=\"|:src=\"|href=\{|window\.open\(|location\.(href|assign|replace)" JSSRC` y seguir el origen del valor.
*Severidad:* media
*Fuente:* Vue, Security › URL Injection — https://vuejs.org/guide/best-practices/security

### SEC-JS-04 — Contenido de usuario nunca se usa como plantilla de Vue, y Vue nunca se monta sobre HTML renderizado por el servidor que contenga datos de usuario
Es la "regla n.º 1" de Vue. Caso típico: Blade imprime `{{ $comentario }}` dentro de un nodo donde luego se monta Vue o Alpine; el escape HTML no neutraliza `{{ }}` ni `x-data`.
*Si no:* ejecución de JavaScript arbitrario en el cliente, y en el servidor si ocurre durante SSR.
*Verificación:* `rg -n "template:\s*(\w+|\`)|compile\(|createApp\(\{[^}]*template" JSSRC resources/js` · en Blade, datos de usuario dentro de nodos con `v-`/`x-data`: solo revisión manual.
*Severidad:* alta
*Fuente:* Vue, Security › Rule No.1: Never Use Non-trusted Templates — https://vuejs.org/guide/best-practices/security

### SEC-JS-05 — En SSR el estado nunca se declara a nivel de módulo; siempre con `useState` o dentro de `setup`
Un `ref()` exportado desde un módulo se comparte entre todas las peticiones del servidor.
*Si no:* fuga de datos entre usuarios: la sesión o el carrito de uno aparece renderizado para otro.
*Verificación:* `rg -n "^export (const|let) \w+\s*=\s*(ref|reactive|shallowRef)\(" composables stores utils app` · `rg -n "^(const|let) \w+\s*=\s*(ref|reactive)\(" composables`.
*Severidad:* alta
*Fuente:* Nuxt 4, State Management ("Never define const state = ref() outside of <script setup> or setup() function") — https://nuxt.com/docs/4.x/getting-started/state-management

### SEC-JS-06 — El middleware de rutas de Nuxt nunca se cuenta como protección de la API; cada handler de `server/api` siempre autentica, autoriza y valida su entrada
El middleware de `app/middleware` corre en la parte Vue; las rutas de Nitro son independientes y se llaman directo con `curl`. Nuxt ofrece `readValidatedBody`, `getValidatedQuery` y `getValidatedRouterParams`.
*Si no:* la página exige login y el endpoint que la alimenta responde a cualquiera.
*Verificación:* handlers sin validación ni sesión: `rg -L "readValidatedBody|getValidatedQuery|getValidatedRouterParams|requireUserSession|getUserSession|verify" server/api -g '*.ts'` · `rg -n "readBody\(|getQuery\(" server`.
*Severidad:* crítica
*Fuente:* Nuxt 4, `middleware/` ("completely different from server middleware") — https://nuxt.com/docs/4.x/guide/directory-structure/app/middleware · `server/` — https://nuxt.com/docs/4.x/guide/directory-structure/server

### SEC-JS-07 — Un objeto construido con claves del usuario nunca se fusiona de forma recursiva sobre un objeto normal; se usa `Map`, `Object.create(null)` o validación de esquema que descarte `__proto__`, `constructor` y `prototype`
*Si no:* contaminación de prototipo: propiedades inyectadas en todos los objetos, que derivan en evasión de autorización, DoS o ejecución de código.
*Verificación:* `rg -n "(_|lodash)\.(merge|mergeWith|defaultsDeep|set|setWith)\(|deepmerge\(|Object\.assign\(\s*\w+,\s*(req\.|body|query|params)" JSSRC` · `rg -n "\[(\w+)\]\[(\w+)\]\s*=" JSSRC` · `npm audit`.
*Severidad:* alta
*Fuente:* OWASP Prototype Pollution Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.html · Node.js, Security Best Practices › Prototype Pollution Attacks (CWE-1321) — https://nodejs.org/en/learn/getting-started/security-best-practices

### SEC-JS-08 — `eval`, `new Function`, `setTimeout`/`setInterval` con cadena y `child_process.exec` nunca reciben entrada externa; para procesos se usa siempre `execFile`/`spawn` con arreglo de argumentos
*Si no:* ejecución de código en el navegador o de comandos en el servidor.
*Verificación:* `rg -n "\beval\(|new Function\(|set(Timeout|Interval)\(\s*['\"\`]|child_process|\bexec(Sync)?\(|shell:\s*true|vm\.runIn" JSSRC`.
*Severidad:* crítica
*Fuente:* OWASP NodeJS Security Cheat Sheet › Do not use dangerous functions — https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html · Node.js, `child_process.exec` — https://nodejs.org/api/child_process.html

### SEC-JS-09 — El token de sesión de una aplicación web nunca se guarda en `localStorage` ni `sessionStorage`; siempre en cookie `HttpOnly`, `Secure` y `SameSite`
Con backend Laravel, es la autenticación SPA de Sanctum (SEC-LAR-25).
*Si no:* cualquier XSS, propio o de una dependencia, exfiltra el token y la sesión completa.
*Verificación:* `rg -n "(localStorage|sessionStorage)\.(setItem|getItem)\(\s*['\"\`][^'\"\`]*(token|jwt|auth|session|bearer)" -i JSSRC resources/js` · `rg -n "persist|pinia-plugin-persistedstate" JSSRC` y revisar qué stores se persisten.
*Severidad:* alta
*Fuente:* OWASP HTML5 Security Cheat Sheet › Local Storage — https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html · Laravel 13, Sanctum › SPA Authentication — https://laravel.com/docs/13.x/sanctum#spa-authentication

### SEC-JS-10 — Una redirección nunca toma su destino de la URL sin comprobar que es una ruta interna
`navigateTo` de Nuxt rechaza URL externas salvo `external: true`; el riesgo aparece al activarlo con un valor de `route.query`, o con `window.location`.
*Si no:* redirección abierta tras el login: phishing con el dominio legítimo.
*Verificación:* `rg -n "navigateTo\([^)]*external:\s*true|route\.query\.(redirect|next|return|url|to)|location\.(href|replace|assign)\s*(=|\()\s*\w*(query|params|redirect)" JSSRC`.
*Severidad:* media
*Fuente:* Nuxt 4, `navigateTo` › Navigating to an External URL — https://nuxt.com/docs/4.x/api/utils/navigate-to · OWASP Unvalidated Redirects and Forwards Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

### SEC-JS-11 — La política CSP nunca incluye `unsafe-eval` ni `unsafe-inline` en `script-src` por comodidad del framework
Livewire y Alpine necesitan `unsafe-eval` salvo con `csp_safe => true` (que restringe las expresiones admitidas en directivas). Cómo emite Nuxt los nonces en SSR está **sin verificar** en fuente primaria.
*Si no:* la CSP deja de mitigar XSS: el script inyectado se ejecuta igual.
*Verificación:* `curl -sI https://<host>/ | rg -i content-security-policy` · `rg -n "unsafe-(eval|inline)" . -g '!node_modules'` · `rg -n "csp_safe" config/livewire.php`.
*Severidad:* media
*Fuente:* Livewire 4, CSP — https://livewire.laravel.com/docs/4.x/csp

### SEC-JS-12 — Las dependencias se instalan siempre desde el lockfile (`npm ci`) y el build nunca pasa con avisos altos o críticos sin excepción documentada
*Si no:* un paquete comprometido o un typosquat entra en el build y roba secretos de CI o inyecta código en el bundle.
*Verificación:* `git ls-files | rg "package-lock.json|pnpm-lock.yaml|yarn.lock|bun.lock"` · `rg -n "npm install|pnpm install(?! --frozen)|yarn install(?! --immutable)" --pcre2 .github Dockerfile* *.yml` · `npm audit --omit=dev --audit-level=high`.
*Severidad:* media
*Fuente:* OWASP NPM Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html · Node.js, Security Best Practices › Malicious Third-Party Modules (CWE-1357) — https://nodejs.org/en/learn/getting-started/security-best-practices

---

## PY — FastAPI, Pydantic, SQLAlchemy

### SEC-PY-01 — La dependencia de autenticación se declara siempre a nivel de `APIRouter` o de la aplicación; una ruta pública solo existe en un router aparte y explícito
Declararla ruta por ruta garantiza que alguna se quede sin ella.
*Si no:* un endpoint nuevo nace sin autenticación y nadie lo nota.
*Verificación:* `rg -n "APIRouter\(" -g '*.py' | rg -v "dependencies="` · `rg -n -A3 "@(router|app)\.(get|post|put|patch|delete)\(" -g '*.py' | rg -v "Depends|Security"` · test que recorra `app.routes` sin credenciales y espere 401 salvo la lista pública.
*Severidad:* crítica
*Fuente:* FastAPI, Global Dependencies — https://fastapi.tiangolo.com/tutorial/dependencies/global-dependencies/ · OWASP API2:2023 — https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/

### SEC-PY-02 — Toda consulta por ID filtra siempre por el propietario o el tenant del usuario autenticado
`session.get(Model, id)` no sabe de dueños.
*Si no:* IDOR.
*Verificación:* `rg -n "\.get\(\w+,\s*\w*id\)|filter\(\w+\.id\s*==|where\(\w+\.id\s*==" -g '*.py'` y comprobar el segundo filtro (`owner_id`, `tenant_id`) o una comprobación posterior.
*Severidad:* crítica
*Fuente:* OWASP API1:2023 — https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/

### SEC-PY-03 — Los modelos de entrada de Pydantic siempre son distintos de los de persistencia y de salida, rechazan campos extra, y toda ruta declara `response_model`
Por defecto Pydantic ignora los campos extra (`extra='ignore'`); con `model_config = ConfigDict(extra='forbid')` el intento se vuelve un 422. `response_model` filtra la salida.
*Si no:* asignación masiva (`setattr` en bucle sobre `model_dump()` con `is_admin`) y fuga de `hashed_password` al devolver el objeto ORM.
*Verificación:* `rg -n "for \w+,\s*\w+ in \w+\.(model_dump|dict)\(.*\)\.items\(\)|\*\*\w+\.(model_dump|dict)\(\)" -g '*.py'` · `rg -n "extra\s*=\s*['\"](allow|ignore)|from_attributes" -g '*.py'` · `rg -n "@(router|app)\.(get|post|put|patch)\(" -g '*.py' | rg -v "response_model"`.
*Severidad:* alta
*Fuente:* FastAPI, Response Model — https://fastapi.tiangolo.com/tutorial/response-model/ · Pydantic, Configuration (`extra`) — https://docs.pydantic.dev/latest/api/config/ · OWASP API3:2023 — https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/

### SEC-PY-04 — `CORSMiddleware` nunca combina `allow_credentials=True` con comodines ni con un `allow_origin_regex` amplio
FastAPI documenta que con credenciales ni orígenes ni métodos ni cabeceras pueden ser `["*"]`. Un regex como `.*` o `https://.*\.example\.com` mal anclado tiene el mismo efecto.
*Si no:* otro origen lee respuestas autenticadas.
*Verificación:* `rg -n -A8 "CORSMiddleware" -g '*.py'` y revisar `allow_origins`, `allow_origin_regex`, `allow_credentials`.
*Severidad:* alta
*Fuente:* FastAPI, CORS — https://fastapi.tiangolo.com/tutorial/cors/

### SEC-PY-05 — `jwt.decode` siempre recibe `algorithms=[...]` con la lista fija, nunca `verify_signature: False`, y la llave nunca está escrita en el código
El ejemplo de la documentación trae un `SECRET_KEY` literal que los agentes copian tal cual.
*Si no:* tokens falsificados; con la llave del tutorial, cualquiera firma tokens válidos.
*Verificación:* `rg -n "jwt\.decode\(" -g '*.py' | rg -v "algorithms="` · `rg -n "verify_signature.*False|verify=False" -g '*.py'` · `rg -n "SECRET_KEY\s*=\s*['\"]|09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" -g '*.py'`.
*Severidad:* crítica
*Fuente:* PyJWT, Usage — https://pyjwt.readthedocs.io/en/stable/usage.html · FastAPI, OAuth2 with Password (and hashing), Bearer with JWT tokens — https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ · RFC 8725 — https://www.rfc-editor.org/rfc/rfc8725

### SEC-PY-06 — El SQL crudo nunca se compone con f-strings, `%` ni `.format`; los valores van siempre como parámetros enlazados de `text()`
*Si no:* inyección SQL.
*Verificación:* `rg -n "(text|execute|exec_driver_sql)\(\s*f['\"]|(text|execute)\([^)]*(%\s*\(|\.format\(|\"\s*\+)" -g '*.py'` · `bandit -t B608 -r .`.
*Severidad:* crítica
*Fuente:* SQLAlchemy 2.0, `text()` y `bindparam()` — https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text

### SEC-PY-07 — Nunca se deserializan datos no confiables con `pickle`, `yaml.load`, `eval` ni `exec`; YAML siempre con `yaml.safe_load`
Python: "el módulo pickle no es seguro". PyYAML: `yaml.load` "es tan potente como `pickle.load`".
*Si no:* ejecución remota de código.
*Verificación:* `rg -n "pickle\.loads?\(|yaml\.(load|unsafe_load|full_load)\(|\beval\(|\bexec\(|marshal\.loads|shelve\.open|joblib\.load|torch\.load" -g '*.py'` · `bandit -t B301,B307,B506 -r .`.
*Severidad:* crítica
*Fuente:* Python, `pickle` — https://docs.python.org/3/library/pickle.html · PyYAML Documentation — https://pyyaml.org/wiki/PyYAMLDocumentation

### SEC-PY-08 — `subprocess` nunca se usa con `shell=True` ni con una cadena que incluya entrada externa; los argumentos van siempre en lista
*Si no:* inyección de comandos.
*Verificación:* `rg -n "shell\s*=\s*True|os\.system\(|os\.popen\(|subprocess\.(run|Popen|call|check_output)\(\s*f?['\"]" -g '*.py'` · `bandit -t B602,B604,B605 -r .`.
*Severidad:* crítica
*Fuente:* Python, `subprocess` › Security Considerations — https://docs.python.org/3/library/subprocess.html#security-considerations

### SEC-PY-09 — Una subida con `UploadFile` siempre impone tamaño máximo y valida el tipo por contenido, y `file.filename` nunca forma parte de la ruta de guardado
Que FastAPI no imponga un tamaño máximo por defecto está **sin verificar** en fuente primaria; la regla lo exige igualmente por API4.
*Si no:* llenado de disco o de memoria, path traversal por el nombre, y contenido activo servido desde el dominio.
*Verificación:* `rg -n "UploadFile" -g '*.py'` y por cada handler: `rg -n "file\.filename|\.filename\)" -g '*.py'` · `rg -n "open\([^)]*filename" -g '*.py'`.
*Severidad:* alta
*Fuente:* OWASP File Upload Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html · FastAPI, Request Files — https://fastapi.tiangolo.com/tutorial/request-files/

### SEC-PY-10 — En producción `/docs`, `/redoc` y `/openapi.json` solo son accesibles para usuarios autorizados o están desactivados, y el servidor nunca arranca con `--reload` ni `debug=True`
Matiz: FastAPI advierte que ocultar la documentación no protege la API (es seguridad por oscuridad). La regla reduce superficie, no sustituye a SEC-PY-01. OWASP API9 pide que la documentación esté disponible solo para quien puede usar la API.
*Si no:* inventario completo de endpoints, parámetros y esquemas para cualquier visitante; con `debug=True`, trazas en las respuestas.
*Verificación:* `curl -s -o /dev/null -w '%{http_code}' https://<api>/{docs,redoc,openapi.json}` · `rg -n "FastAPI\(" -A6 -g '*.py' | rg "docs_url|redoc_url|openapi_url|debug"` · `rg -n "\-\-reload|debug=True" Dockerfile* *.yml *.sh -g '*.py'`.
*Severidad:* baja
*Fuente:* FastAPI, Conditional OpenAPI — https://fastapi.tiangolo.com/how-to/conditional-openapi/ · OWASP API9:2023 — https://api-security.owasp.org/editions/2023/en/0xa9-improper-inventory-management/

---

## INT — Integraciones: Stripe, S3/MinIO, OneSignal, Sentry, correo

### SEC-INT-01 — Todo endpoint de webhook siempre verifica la firma sobre el cuerpo crudo antes de leer el contenido
Stripe exige el cuerpo sin modificar: si el framework lo parsea y reserializa, la verificación falla, y la "solución" habitual es quitarla. La marca de tiempo va dentro de la firma: la tolerancia temporal de la librería no se desactiva ni se amplía, porque es la defensa contra la repetición de eventos capturados. Con Cashier, el middleware de firma solo actúa si `STRIPE_WEBHOOK_SECRET` está definido.
*Si no:* cualquiera envía un `checkout.session.completed` falso y obtiene el producto, la suscripción o el saldo sin pagar.
*Verificación:* `rg -n "webhook" routes app server -i -l` y por cada handler: `rg -n "constructEvent|construct_event|ConstructEvent|VerifyWebhookSignature|Stripe-Signature|hash_hmac|hmac\.(new|compare)" <archivo>` · `rg -n "STRIPE_WEBHOOK_SECRET" .env.example config` · prueba: POST sin firma debe dar 400/403.
*Severidad:* crítica
*Fuente:* Stripe, Webhooks › Verificar firmas y Prevenir ataques de repetición — https://docs.stripe.com/webhooks#verify-events · https://docs.stripe.com/webhooks#replay-attacks · Laravel 13, Cashier › Verifying Webhook Signatures — https://laravel.com/docs/13.x/billing#verifying-webhook-signatures · OWASP Webhook Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html

### SEC-INT-02 — El procesamiento de un webhook siempre es idempotente: registra el ID del evento y no repite efectos, ni depende del orden de llegada
Stripe puede entregar el mismo evento más de una vez y fuera de orden; pide no usar `created` para ordenar ni para deduplicar.
*Si no:* doble entrega de producto, doble abono de saldo, o un estado antiguo que pisa a uno nuevo.
*Verificación:* buscar tabla o índice único de eventos (`rg -n "event_id|stripe_event|processed_events|webhook_calls" database app`) · test que envíe dos veces el mismo evento y compruebe un solo efecto.
*Severidad:* alta
*Fuente:* Stripe, Webhooks › Maneja los eventos duplicados y orden de eventos — https://docs.stripe.com/webhooks#handle-duplicate-events

### SEC-INT-03 — Un pedido nunca se da por pagado por la redirección del cliente a la URL de éxito; solo por el webhook o consultando el objeto en la API de Stripe, y el cumplimiento se hace una sola vez
Stripe: no se puede depender de la página de retorno, y la función de cumplimiento puede ejecutarse varias veces, incluso en paralelo.
*Si no:* visitar `/checkout/success?session_id=…` (o una URL inventada) marca el pedido como pagado; o se entrega dos veces.
*Verificación:* leer el handler de `success_url` (`rg -n "success_url|return_url|checkout/success" app routes server lib`) y confirmar que consulta `payment_status` en Stripe y usa un bloqueo o una transición de estado atómica.
*Severidad:* crítica
*Fuente:* Stripe, Fulfill orders ("Webhooks are required for fulfillment") — https://docs.stripe.com/payments/checkout/fulfill-orders

### SEC-INT-04 — El importe, la moneda y el producto de un cobro siempre los calcula el servidor a partir de su catálogo; nunca se toman del cliente
*Si no:* el cliente paga 0.01 por cualquier producto cambiando el JSON.
*Verificación:* `rg -n "(amount|unit_amount|price|total)['\"]?\s*(=>|:|=)\s*\\$?(request|req\.|body|input|this->)" app server -g '*.php' -g '*.ts' -g '*.go' -g '*.py'`.
*Severidad:* crítica
*Fuente:* OWASP Third Party Payment Gateway Integration Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.html · OWASP API3:2023 — https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/

### SEC-INT-05 — Toda petición `POST` a Stripe que crea un cobro, un reembolso o una transferencia lleva siempre una llave de idempotencia estable entre reintentos
La llave se genera una vez por intento de negocio (no por petición HTTP) y no contiene datos personales. Stripe la conserva al menos 24 horas.
*Si no:* un reintento por timeout, un job que se repite o un doble clic generan dos cobros.
*Verificación:* `rg -n "(paymentIntents|charges|refunds|transfers|payouts)->create\(|PaymentIntent::create\(|\.paymentIntents\.create\(" app server lib` y comprobar `idempotency_key`/`idempotencyKey`; en jobs, que la llave salga del ID del pedido y no de `Str::uuid()` dentro de `handle()`.
*Severidad:* alta
*Fuente:* Stripe API, Idempotent requests — https://docs.stripe.com/api/idempotent_requests

### SEC-INT-06 — Las llaves secretas y restringidas de Stripe (`sk_`, `rk_`) y los secretos de webhook (`whsec_`) nunca están en el código, en el repositorio ni en una app cliente; en clientes solo va la llave publicable (`pk_`)
Stripe pide además preferir llaves restringidas y rotarlas ante cualquier exposición.
*Si no:* cobros, reembolsos y lectura de datos de clientes con la cuenta de Stripe del proyecto.
*Verificación:* `rg -n "(sk|rk)_(live|test)_[0-9a-zA-Z]{10,}|whsec_[0-9a-zA-Z]{10,}" . -g '!node_modules' -g '!vendor'` · `gitleaks detect` sobre el historial.
*Severidad:* crítica
*Fuente:* Stripe, Best practices for managing secret API keys — https://docs.stripe.com/keys-best-practices

### SEC-INT-07 — Un bucket con datos de usuarios nunca es público; el acceso a objetos privados es siempre por URL prefirmada de corta duración emitida tras autorizar
Una URL prefirmada es una credencial al portador: sirve a quien la tenga hasta que caduca (hasta 7 días con credenciales de usuario IAM). Block Public Access activo y ACL desactivadas son los valores por defecto actuales de S3; en MinIO la política anónima del bucket debe ser `none` (**sin verificar** en fuente primaria).
*Si no:* listado y descarga de todos los archivos; o enlaces "temporales" que circulan durante días.
*Verificación:* `aws s3api get-public-access-block --bucket <b>` y `get-bucket-policy-status` · `rg -n "temporaryUrl\(|temporaryUploadUrl\(|getSignedUrl|PresignGetObject|generate_presigned_url" app server lib -A2` y revisar la caducidad (minutos, no días) y que haya autorización antes · `rg -n "'visibility'\s*=>\s*'public'|ACL.*public-read" config app`.
*Severidad:* crítica
*Fuente:* AWS, Sharing objects with presigned URLs — https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html · Security best practices for Amazon S3 — https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html

### SEC-INT-08 — En una subida directa por URL prefirmada, la clave del objeto siempre la genera el servidor, y el tipo y el tamaño siempre se limitan o se comprueban después
Un `PUT` prefirmado no limita tamaño; un `POST` prefirmado admite condiciones de política (`content-length-range`, `Content-Type`, prefijo de clave).
*Si no:* sobrescritura de objetos ajenos eligiendo la clave, subida de archivos de cualquier tamaño y tipo con cargo al proyecto, HTML activo servido desde el bucket.
*Verificación:* leer el endpoint que emite la URL: `rg -n "temporaryUploadUrl\(|createPresignedPost|PresignPutObject|generate_presigned_(post|url)" app server lib -B4 -A6`; la clave no debe salir de la petición.
*Severidad:* alta
*Fuente:* AWS, Uploading objects with presigned URLs — https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html · POST Policy — https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-HTTPPOSTConstructPolicy.html · Laravel 13, Temporary Upload URLs — https://laravel.com/docs/13.x/filesystem#temporary-upload-urls

### SEC-INT-09 — La llave de API de OneSignal (`os_v2_app_…`, `os_v2_org_…`) nunca está en la app ni en el frontend; las notificaciones se envían siempre desde el backend
El App ID es público. Además, sin Identity Verification un cliente puede hacer `login` con el External ID de otro usuario; al 2026-10-02 OneSignal indica que Flutter todavía no expone `login(externalId, token)`.
*Si no:* con la llave, envío de notificaciones a toda la base de usuarios; sin verificación de identidad, un dispositivo recibe las notificaciones de otro usuario, por lo que una push nunca debe llevar datos sensibles.
*Verificación:* `rg -n "os_v2_(app|org)_|ONESIGNAL_(REST_)?API_KEY|Authorization.*(Basic|Key)\s" lib JSSRC resources/js android ios` · `rg -n "api\.onesignal\.com|onesignal\.com/api" lib JSSRC resources/js`.
*Severidad:* crítica
*Fuente:* OneSignal, Keys & IDs — https://documentation.onesignal.com/docs/keys-and-ids · Identity Verification — https://documentation.onesignal.com/docs/identity-verification

### SEC-INT-10 — En el cliente solo va el DSN de Sentry; los tokens de autenticación de Sentry nunca, y el envío de PII por defecto nunca se activa sin decisión explícita
El DSN es público por diseño: solo permite enviar eventos. Los tokens (`sntrys_…`, prefijo **sin verificar** en esta lectura) dan acceso de lectura y gestión, y suelen colarse por la subida de source maps o de símbolos.
*Si no:* con el token, lectura de todos los errores, que contienen datos de usuarios; con PII por defecto, cabeceras, cookies e IP de usuarios en un tercero.
*Verificación:* `rg -n "sntry[su]_|SENTRY_AUTH_TOKEN" . -g '!node_modules' -g '!vendor'` (solo admisible en secretos de CI) · `rg -n "send_default_pii|sendDefaultPii" config lib JSSRC -g '*.py'`.
*Severidad:* alta
*Fuente:* Sentry, DSN Explainer — https://docs.sentry.io/concepts/key-terms/dsn-explainer/ · Auth Tokens — https://docs.sentry.io/account/auth-tokens/ · Scrubbing Sensitive Data — https://docs.sentry.io/platforms/php/guides/laravel/data-management/sensitive-data/

### SEC-INT-11 — Los webhooks de proveedores de correo siempre se autentican: firma ECDSA en SendGrid y autenticación básica sobre HTTPS en Mailjet
Mailjet no firma los eventos; su única protección documentada es HTTPS más usuario y contraseña en la URL del endpoint.
*Si no:* cualquiera inyecta eventos falsos de rebote, baja o queja y altera el estado de suscripción o la reputación interna de los destinatarios.
*Verificación:* `rg -n "mailjet|sendgrid" routes app server -i` y en cada handler: `rg -n "X-Twilio-Email-Event-Webhook-Signature|auth\.basic|PHP_AUTH_USER|hash_equals" <archivo>` · prueba: POST sin credenciales debe dar 401/403.
*Severidad:* media
*Fuente:* Twilio SendGrid, Event Webhook Security Features — https://www.twilio.com/docs/sendgrid/for-developers/tracking-events/getting-started-event-webhook-security-features · Mailjet, Webhooks — https://dev.mailjet.com/email/guides/webhooks/

---

## Dudas y huecos

- **Puntos sin verificar en fuente primaria** (marcados en la regla): persistencia del Keychain de iOS tras desinstalar (MOV-09); análisis de SFC de Livewire 4 por Larastan (nota de Livewire 4 en la cabecera); emisión de nonces CSP en Nuxt (JS-11); ausencia de tope de tamaño por defecto en `UploadFile` (PY-09); política anónima de MinIO (INT-07); prefijos de tokens de Sentry (INT-10); estado de Nuxt 5.
- **SEC-LW-10 (livewire-dropzone)** se apoya en la lectura del código del paquete, no en un aviso publicado. Conviene reproducirlo en un proyecto real antes de fijar la severidad.
- **OWASP Go-SCP** se cita por la página del proyecto; no se bajó a capítulo y párrafo.
- **GraphQL** no se convirtió en reglas: ningún stack del usuario lo usa. Existe hoja OWASP: https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html
- **Fuera de alcance**: Jetstream (teams, tokens de API en la interfaz) no tiene reglas propias, solo lo que hereda de Fortify y Sanctum; MySQL (privilegios del usuario de la app, TLS) y la configuración de MinIO pertenecen a infraestructura; iOS nativo (ATS, entitlements) solo se toca donde afecta a Flutter.
- **Los patrones de grep no se ejecutaron contra los repositorios del usuario.** Antes de adoptarlos conviene una pasada de calibración sobre dos o tres proyectos para medir falsos positivos, sobre todo en LAR-08, LW-02 y LW-04 (dependen de `rg -L` y de PCRE2).
- **Numeración MASWE.** Los identificadores de este catálogo son los que publica hoy mas.owasp.org. No coinciden con los de material de 2024–2025, así que una referencia MASWE tomada de otra fuente puede apuntar a otra debilidad. No se encontró la nota de versión que documente el cambio.
- **Fuentes de apoyo comprobadas solo por disponibilidad (HTTP 200) o leídas solo en sus encabezados, sin releer el pasaje:** RFC 8725; hojas OWASP de OS Command Injection, Unvalidated Redirects, Logging, HTML5 Security, Webhook Security, File Upload, Pinning, Mass Assignment, SSRF Prevention, NPM Security y Third Party Payment Gateway; AWS POST Policy y subida con URL prefirmada; Sentry Auth Tokens; `api.flutter.dev` (`badCertificateCallback`); Pydantic `ConfigDict`; Node `child_process`; SQLAlchemy `text()`. Las reglas que las citan se apoyan además en una fuente sí leída, salvo SEC-API-13 (JWT genérico), que descansa en el RFC.
