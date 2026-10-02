# 04 — Protecciones de plataforma y herramientas del auditor

Investigación para `elyares-auditor`. Alcance: controles defensivos de plataforma, configuración y operación, y herramientas ejecutables en solo lectura. Las reglas de código (OWASP web, API, stacks, IA) las cubren otros documentos.

- Fecha de verificación: **2026-10-02**. Todo lo que cita versión o flag se comprobó ese día contra fuente primaria (documentación oficial, texto legal, o la API de releases de GitHub). Lo que no se pudo comprobar va marcado **«sin verificar»**.
- Lo marcado **«interpretación»** es criterio propio derivado de la fuente, no texto literal de ella.
- `HOST`, `IMAGEN`, `CONTENEDOR`, `BUCKET` son marcadores a sustituir.
- Los comandos de verificación son de lectura. Los que llevan `sudo` se ejecutan en el VPS por SSH y no modifican estado.

## 0. Versiones y hechos confirmados

| Elemento | Estado a 2026-10-02 | Fuente |
|---|---|---|
| NIST SP 800-63B | **Revisión 4**, final, publicada julio 2025; sustituye a la 63B de 2020 | https://csrc.nist.gov/pubs/sp/800/63/b/4/final |
| OWASP ASVS | 5.0.0 (identificadores `V<cap>.<sec>.<req>`) | https://owasp.org/www-project-application-security-verification-standard/ |
| OWASP Top 10 | Edición 2025 (A02 Security Misconfiguration, A03 Software Supply Chain Failures, A09 Security Logging & Alerting Failures) | https://owasp.org/Top10/2025/ |
| OWASP Secure Headers | `headers_add.json` actualizado 2026-09-13 | https://github.com/OWASP/www-project-secure-headers/blob/master/ci/headers_add.json |
| SLSA | v1.2 «Approved»; incluye Build track (L0–L3) y Source track | https://slsa.dev/spec/ |
| LFPDPPP (México) | **Ley nueva**, DOF 20-03-2025, abroga la de 2010; última reforma DOF 14-11-2025 | https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf |
| Reglamento LFPDPPP | Sigue publicado el de DOF 21-12-2011 como «texto vigente» | https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LFPDPPP.pdf |
| Guía TLS (ex-Mozilla) | Mozilla la movió a TLSRef; v6.0 elimina el perfil «Old» | https://docs.tlsref.org/server-side-tls.html |
| Caddy | v2.11.6 (2026-10-01, con correcciones de seguridad) | https://github.com/caddyserver/caddy/releases |
| Docker Engine / Compose | v29.8.2 (2026-09-30) / v5.5.1 (2026-09-03) | https://github.com/moby/moby/releases · https://github.com/docker/compose/releases |
| Laravel | 13.34.0. **Laravel 11 dejó de recibir parches de seguridad el 2026-03-12**; Laravel 12 los recibe hasta 2027-02-24; Laravel 13 hasta 2028-03-17 | https://laravel.com/docs/13.x/releases#support-policy |
| Livewire / Alpine | v4.4.7 / v3.17.4. Livewire 4 trae `csp_safe` | https://livewire.laravel.com/docs/csp |
| Fortify / Sanctum | v1.40.0 / v4.3.3 | https://github.com/laravel/fortify/releases |
| Nuxt / nuxt-security | v4.5.2 / v2.6.0 | https://nuxt-security.vercel.app/advanced/strict-csp |
| CIS Docker Benchmark | v1.9.0 listado (solo miembros); v1.8.0 en CIS-CAT. `docker-bench-security` sigue basado en v1.6.0 | https://www.cisecurity.org/benchmark/docker |
| Enlightn | **Repositorio archivado el 2024-06-15**. No usar | https://github.com/enlightn/enlightn |
| MinIO (community) | **Repositorio archivado; README: «THIS REPOSITORY IS NO LONGER MAINTAINED»**; solo código fuente, sin binarios | https://github.com/minio/minio |
| Gitleaks | v8.30.1; el autor lo declara «feature complete», solo parches de seguridad, y se muda a Betterleaks | https://github.com/gitleaks/gitleaks |
| Trivy | v0.75.0. **Comprometido el 2026-03-19** (binario v0.69.4, 76 de 77 tags de `trivy-action`, `setup-trivy`) | https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23 |
| Psalm | Estable 6.19.1; la 7 está en beta | https://github.com/vimeo/psalm/releases |

## 0.1 Niveles de impacto de las herramientas

El auditor clasifica cada comando antes de ejecutarlo:

- **N0 — estático local.** Lee el repositorio o una imagen ya descargada. Puede descargar bases de vulnerabilidades o enviar a un servicio de avisos la lista de paquetes y versiones (nunca el código). Permitido por defecto.
- **N1 — remoto pasivo.** Peticiones equivalentes a las de un navegador o un cliente TLS contra un sistema vivo (`curl -I`, Observatory, testssl.sh, ssh-audit). Solo contra hosts del usuario; deja rastro en logs y puede disparar fail2ban/CrowdSec.
- **N2 — activo.** Envía cargas de ataque o fuzzing (nuclei, ZAP en modo activo, sqlmap). **Requiere autorización explícita y entorno propio.** El auditor solo los lista, nunca los ejecuta.

Salvaguardas del propio auditor (interpretación, derivada de cómo funcionan las herramientas):

- Nunca ejecutar `composer install`, `npm install`, `pnpm install`, `pip install` ni `dart pub get` dentro del repo auditado: ejecutan scripts de terceros o reescriben lockfiles. Auditar siempre sobre el lockfile.
- TruffleHog y Betterleaks **validan los secretos encontrados autenticándose contra el proveedor**. En modo solo lectura usar `--no-verification`.
- `pip-audit -r` sin `--no-deps` o `--require-hashes` resuelve dependencias con pip y puede ejecutar código de build.
- `docker compose config` imprime los secretos ya interpolados: no volcar su salida a un informe.
- Los informes se escriben fuera del repo auditado.
- Semgrep envía métricas cuando las reglas vienen del registro; usar `--metrics=off`.

---

## 1. Cabeceras y navegador (HDR)

Referencia de directiva en Caddy (solo para saber que existe; no es configuración completa). `header` admite fijar, añadir (`+`), borrar (`-`), valor por defecto (`?`) y diferir (`>`):

```
header {
	Strict-Transport-Security "max-age=63072000; includeSubDomains"
	X-Content-Type-Options nosniff
	?Referrer-Policy strict-origin-when-cross-origin   # ? = solo si la app no la envió
	-Server                                            # - = eliminar
}
```

Fuente: https://caddyserver.com/docs/caddyfile/directives/header. La CSP con nonce debe emitirla la aplicación, porque el nonce cambia por respuesta (interpretación).

### SEC-HDR-01 — Toda respuesta HTML siempre envía `Content-Security-Policy` como cabecera HTTP, nunca solo como `<meta>`
La etiqueta `<meta>` no admite `frame-ancestors`, `sandbox` ni endpoint de reporte. Una política nueva se despliega primero como `Content-Security-Policy-Report-Only`.
*Si no:* un XSS que pase el escapado se ejecuta sin segunda barrera.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^content-security-policy'`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V3.4.3 · OWASP CSP Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html

### SEC-HDR-02 — `script-src` nunca contiene `'unsafe-inline'` ni `'unsafe-eval'`; los scripts solo se autorizan con nonce o hash más `'strict-dynamic'`
Convivencia por stack: Livewire 4 exige `'unsafe-eval'` salvo que se active `'csp_safe' => true` en `config/livewire.php` (Alpine pasa entonces a su evaluador CSP y dejan de funcionar funciones flecha, template literals, spread y acceso dinámico a propiedades). Alpine suelto: build `@alpinejs/csp`. Laravel + Vite: `Vite::useCspNonce()` en un middleware y `Vite::cspNonce()` en la cabecera. Nuxt: módulo `nuxt-security` con `nonce: true` en SSR y `ssg.hashScripts` en SSG. Livewire 3 (proyectos en Laravel 11): requisito de `unsafe-eval` **sin verificar** en su documentación.
*Si no:* la CSP queda decorativa; cualquier inyección de script se ejecuta.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^content-security-policy' | grep -E "unsafe-(inline|eval)"` (no debe devolver nada en `script-src`); en repo: `grep -n "csp_safe" config/livewire.php`, `grep -rn "useCspNonce" app/ bootstrap/`, `grep -n "nuxt-security" package.json`.
*Severidad:* alta
*Fuente:* OWASP CSP Cheat Sheet (Strict CSP) · https://livewire.laravel.com/docs/csp · https://alpinejs.dev/advanced/csp · https://laravel.com/docs/13.x/vite#content-security-policy-csp-nonce · https://nuxt-security.vercel.app/advanced/strict-csp

### SEC-HDR-03 — La CSP siempre declara `object-src 'none'`, `base-uri` restringido y `form-action 'self'`
`'strict-dynamic'` solo cubre scripts; estas tres directivas cierran inyección de `<base>`, plugins y exfiltración por formularios.
*Si no:* un `<base href>` inyectado redirige los scripts relativos a un servidor ajeno aun con nonce.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^content-security-policy' | grep -o -E "(object-src|base-uri|form-action)[^;]*"` (deben salir las tres).
*Severidad:* media
*Fuente:* OWASP Secure Headers Project, `headers_add.json` — https://owasp.org/www-project-secure-headers/

### SEC-HDR-04 — Toda respuesta siempre declara `frame-ancestors` (`'none'` o lista explícita)
`frame-ancestors` no hereda de `default-src`. `X-Frame-Options: DENY` se mantiene solo como respaldo para navegadores antiguos.
*Si no:* clickjacking sobre acciones autenticadas.
*Verificación:* `curl -sSI https://HOST/ | grep -i -E 'frame-ancestors|^x-frame-options'`
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V3.4.6 · OWASP HTTP Headers Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

### SEC-HDR-05 — Toda respuesta HTTPS siempre envía `Strict-Transport-Security` con `max-age` ≥ 31536000 e `includeSubDomains`
OWASP y TLSRef proponen `max-age=63072000`. `preload` solo si **todos** los subdominios (incluidos los internos) sirven HTTPS; hstspreload.org exige ≥ 1 año, `includeSubDomains` y `preload`. El ejemplo oficial de Caddy la declara a mano (que Caddy no la añada sola: interpretación).
*Si no:* la primera visita por HTTP admite downgrade y robo de sesión en redes hostiles.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^strict-transport-security'`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V3.4.1 · https://hstspreload.org/

### SEC-HDR-06 — Toda respuesta siempre envía `X-Content-Type-Options: nosniff`
Aplica también a descargas y archivos subidos por usuarios.
*Si no:* un archivo subido se interpreta como script o HTML.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^x-content-type-options'`
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V3.4.4

### SEC-HDR-07 — Toda respuesta siempre envía `Referrer-Policy` igual o más estricta que `strict-origin-when-cross-origin`
OWASP Secure Headers propone `no-referrer`; el Cheat Sheet, `strict-origin-when-cross-origin`.
*Si no:* rutas con identificadores (paciente, expediente, token) se filtran a terceros por `Referer`.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^referrer-policy'`
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V3.4.5

### SEC-HDR-08 — Toda respuesta HTML siempre envía `Permissions-Policy` negando las capacidades que la app no usa
Mínimo `geolocation=(), camera=(), microphone=()`; la lista completa de OWASP incluye `payment`, `usb`, `display-capture`, etc.
*Si no:* un script inyectado o un iframe de terceros puede pedir cámara, micrófono o ubicación con el origen de la app.
*Verificación:* `curl -sSI https://HOST/ | grep -i '^permissions-policy'`
*Severidad:* baja
*Fuente:* OWASP Secure Headers Project — https://owasp.org/www-project-secure-headers/

### SEC-HDR-09 — Los documentos HTML siempre envían `Cross-Origin-Opener-Policy: same-origin` y los recursos `Cross-Origin-Resource-Policy`; `Cross-Origin-Embedder-Policy` solo se activa donde no rompe recursos de terceros
OWASP recomienda las tres (`require-corp` para COEP). COEP bloquea imágenes, fuentes y scripts de terceros sin CORP/CORS: activarla solo tras probar (interpretación).
*Si no:* una ventana abierta por un tercero conserva referencia a la app (XS-Leaks, tabnabbing).
*Verificación:* `curl -sSI https://HOST/ | grep -i -E '^cross-origin-(opener|resource|embedder)-policy'`
*Severidad:* baja
*Fuente:* OWASP ASVS 5.0 V3.4.8 · OWASP HTTP Headers Cheat Sheet

### SEC-HDR-10 — Las cookies de sesión siempre llevan `Secure`, `HttpOnly` y `SameSite`, y su nombre siempre usa el prefijo `__Host-` salvo que deban compartirse entre hosts
`__Host-` exige `Secure`, sin `Domain` y `Path=/`. `SameSite=None` exige `Secure`. En Laravel, `config/session.php` trae `http_only=true` y `same_site=lax`, pero `secure` depende de `SESSION_SECURE_COOKIE` y **no tiene valor por defecto**.
*Si no:* la sesión viaja por HTTP, es legible por JavaScript o la sobrescribe un subdominio.
*Verificación:* `curl -sSI https://HOST/login | grep -i '^set-cookie'`; en servidor: `grep -nE '^SESSION_(SECURE_COOKIE|COOKIE|DOMAIN|SAME_SITE)' .env`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V3.3.1–V3.3.4 · MDN Cookies — https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies

### SEC-HDR-11 — CORS nunca refleja un `Origin` arbitrario ni combina `Access-Control-Allow-Origin: *` con credenciales
El origen permitido es fijo o se valida contra lista. Si varía, la respuesta lleva `Vary: Origin`. El origen `null` nunca entra en la lista.
*Si no:* cualquier sitio lee respuestas autenticadas de la API con la sesión de la víctima.
*Verificación:* `curl -sSI -H 'Origin: https://evil.example' https://HOST/api/user | grep -i '^access-control-'` (no debe devolver `evil.example`); en Laravel: `grep -nE "allowed_origins|supports_credentials" config/cors.php`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V3.4.2 · MDN CORS — https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS

### SEC-HDR-12 — Las respuestas nunca exponen cabeceras de huella (`Server`, `X-Powered-By`) ni usan cabeceras retiradas (`X-XSS-Protection` distinto de `0`, `Expect-CT`, `Public-Key-Pins`)
OWASP mantiene la lista de cabeceras a eliminar en `headers_remove.json`.
*Si no:* se regala versión exacta de servidor y runtime; las retiradas crean fallos propios.
*Verificación:* `curl -sSI https://HOST/ | grep -i -E '^(server|x-powered-by|x-xss-protection|expect-ct|public-key-pins)'`
*Severidad:* baja
*Fuente:* OWASP Secure Headers Project · OWASP ASVS 5.0 V13.4.6

### SEC-HDR-13 — Las respuestas con datos personales o autenticados siempre llevan `Cache-Control: no-store`
Aplica a vistas de expediente, exportaciones y respuestas de API con datos de titular.
*Si no:* los datos quedan en la caché del navegador o de un proxy compartido.
*Verificación:* `curl -sSI -b 'COOKIE_DE_PRUEBA' https://HOST/RUTA_AUTENTICADA | grep -i '^cache-control'` (requiere sesión de prueba; si no, solo revisión manual).
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V14.3.2 · OWASP Secure Headers Project

---

## 2. Autenticación y abuso (AUT)

### SEC-AUT-01 — Las contraseñas solo se almacenan con argon2id o bcrypt con parámetros iguales o superiores a los de OWASP, nunca con hash rápido ni cifrado reversible
Mínimos OWASP: argon2id `m=19456 (19 MiB), t=2, p=1` (o equivalentes: 46 MiB/t=1, 12 MiB/t=3, 9 MiB/t=4, 7 MiB/t=5); bcrypt factor ≥ 10 y entrada limitada a 72 bytes; PBKDF2-HMAC-SHA256 600 000 iteraciones. NIST exige sal ≥ 32 bits. Laravel por defecto: bcrypt `rounds=12`, argon `memory=65536, time=4, threads=1`, `rehash_on_login=true`: todos por encima del mínimo.
*Si no:* una fuga de la tabla de usuarios equivale a una fuga de contraseñas en claro.
*Verificación:* `grep -nE "driver|rounds|memory|time|rehash_on_login" config/hashing.php`; `grep -nE '^(HASH_DRIVER|BCRYPT_ROUNDS|ARGON_)' .env`; consulta de solo lectura `SELECT LEFT(password,7) AS p, COUNT(*) FROM users GROUP BY p;` (se espera `$2y$12$` o `$argon2`).
*Severidad:* crítica
*Fuente:* OWASP Password Storage Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html · OWASP ASVS 5.0 V11.4.2 · NIST SP 800-63B-4 §3.1.1.2

### SEC-AUT-02 — La política de contraseñas siempre exige longitud (15 sin MFA, 8 con MFA), admite al menos 64 caracteres y nunca impone reglas de composición, rotación periódica, pistas ni preguntas secretas
NIST 800-63B-4: mínimo 15 si la contraseña es factor único, 8 si solo forma parte de MFA; no composición; no cambio periódico (sí forzarlo ante evidencia de compromiso); permitir gestores y pegar; Unicode cuenta por punto de código.
*Si no:* las reglas de composición producen contraseñas predecibles y la rotación forzada, variaciones triviales.
*Verificación:* `grep -rnE "Password::(min|defaults)|mixedCase\(|symbols\(|numbers\(" app/` (Laravel); probar el formulario con una frase de 64 caracteres y con pegado; resto solo revisión manual.
*Severidad:* media
*Fuente:* NIST SP 800-63B-4 §3.1.1.2 — https://pages.nist.gov/800-63-4/sp800-63b.html · OWASP ASVS 5.0 V6.2.1, V6.2.5, V6.2.7, V6.2.9, V6.2.10, V6.4.2

### SEC-AUT-03 — Toda contraseña nueva o cambiada siempre se compara contra una lista de contraseñas comprometidas o comunes
NIST lo exige (SHALL) comparando la contraseña entera. En Laravel: `Password::min(...)->uncompromised()` consulta haveibeenpwned por k-anonimato.
*Si no:* el credential stuffing acierta con contraseñas ya filtradas aunque sean largas.
*Verificación:* `grep -rn "uncompromised" app/`; otros stacks: solo revisión manual.
*Severidad:* media
*Fuente:* NIST SP 800-63B-4 §3.1.1.2 · OWASP ASVS 5.0 V6.2.4, V6.2.12 · https://laravel.com/docs/13.x/validation

### SEC-AUT-04 — Las cuentas administrativas y las que acceden a datos sensibles siempre usan MFA, y nunca con SMS o correo como único segundo factor
Preferencia: passkeys/FIDO2, después TOTP. NIST prohíbe el correo como canal fuera de banda y trata la telefonía (PSTN) como autenticador restringido; AAL2 debe ofrecer una opción resistente a phishing. Los códigos de recuperación son de un solo uso y el restablecimiento de contraseña nunca salta el MFA.
*Si no:* una contraseña filtrada da acceso completo a expedientes o al panel de administración.
*Verificación:* `grep -n "twoFactorAuthentication" config/fortify.php`; `SELECT COUNT(*) FROM users WHERE is_admin=1 AND two_factor_confirmed_at IS NULL;` (ajustar a la columna de rol real); resto solo revisión manual.
*Severidad:* alta
*Fuente:* OWASP MFA Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html · OWASP ASVS 5.0 V6.3.3, V6.4.3, V6.5.1 · NIST SP 800-63B-4 §2.2

### SEC-AUT-05 — Login, verificación de segundo factor y restablecimiento siempre están limitados por cuenta y por IP
NIST: no más de 100 intentos fallidos consecutivos por cuenta. Fortify limita por combinación usuario+IP (`fortify.limiters.login`); eso no frena un ataque distribuido contra una cuenta, así que hace falta además un límite solo por cuenta. El bloqueo se diseña para que no sirva de denegación de servicio contra el usuario legítimo.
*Si no:* fuerza bruta y credential stuffing sin coste.
*Verificación:* `grep -nA4 "limiters" config/fortify.php`; `grep -rn "RateLimiter::for" app/Providers/`; prueba N1 con cuenta propia: `for i in $(seq 1 15); do curl -s -o /dev/null -w '%{http_code}\n' -X POST https://HOST/login -d 'email=prueba@propio.mx&password=x'; done` (debe aparecer `429`).
*Severidad:* alta
*Fuente:* NIST SP 800-63B-4 §3.2.2 · OWASP ASVS 5.0 V6.3.1 · https://laravel.com/docs/13.x/fortify

### SEC-AUT-06 — Login, registro y recuperación nunca revelan si una cuenta existe, ni por mensaje, ni por código HTTP, ni por tiempo de respuesta
Mensajes de referencia OWASP: «Login failed; Invalid user ID or password» y «If that email address is in our database, we will send you an email…». El hash se calcula siempre, exista o no el usuario.
*Si no:* el atacante obtiene la lista de usuarios válidos (en un sistema médico, quién es paciente).
*Verificación:* comparar cuerpo, código y tiempo de `POST /forgot-password` con un correo existente y uno inexistente (cuentas propias); solo revisión manual para el resto.
*Severidad:* media
*Fuente:* OWASP Authentication Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html · OWASP ASVS 5.0 V6.3.8

### SEC-AUT-07 — Todo endpoint costoso siempre tiene límite de tasa y cuota de recursos propios
Exportaciones, reportes, búsquedas, subida de archivos, envío de correo/SMS, generación de PDF, llamadas a modelos de IA. El límite global de la API no basta.
*Si no:* denegación de servicio barata y factura inflada de terceros (SMS, IA, correo).
*Verificación:* `php artisan route:list --json | grep -c throttle` frente al total de rutas; listar rutas sin `throttle`; en otros stacks, solo revisión manual.
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V15.1.3, V15.2.2

### SEC-AUT-08 — El CAPTCHA solo se usa como capa adicional tras intentos fallidos, nunca como único control contra automatización
OWASP: muchas implementaciones se resuelven de forma automática o subcontratada; es más útil exigirlo solo después de fallos iniciales.
*Si no:* falsa sensación de protección y fricción para todos los usuarios.
*Verificación:* solo revisión manual (confirmar que SEC-AUT-05 se cumple con el CAPTCHA desactivado).
*Severidad:* baja
*Fuente:* OWASP Authentication Cheat Sheet

### SEC-AUT-09 — La sesión siempre se regenera al autenticar y siempre caduca por inactividad y por tiempo total
NIST AAL2: reautenticación total recomendada ≤ 24 h e inactividad ≤ 1 h; AAL1: total ≤ 30 días. Cambiar correo, contraseña o MFA exige la credencial actual. Laravel por defecto: `SESSION_LIFETIME=120`.
*Si no:* una sesión robada u olvidada en un equipo compartido sigue viva indefinidamente.
*Verificación:* `grep -nE "'lifetime'|expire_on_close" config/session.php`; `grep -n '^SESSION_LIFETIME' .env`; caducidad de tokens Sanctum: `grep -n "expiration" config/sanctum.php`.
*Severidad:* media
*Fuente:* NIST SP 800-63B-4 §2.1–2.2 · OWASP ASVS 5.0 V7.2.4, V6.2.3

### SEC-AUT-10 — Producción nunca contiene cuentas por defecto ni credenciales sembradas por seeders o fixtures
Incluye `admin@admin.com`, `test@example.com` y usuarios de demostración.
*Si no:* acceso administrativo con credenciales publicadas en el propio repositorio.
*Verificación:* `grep -rnE "admin@|password'?\s*=>\s*(bcrypt|Hash::make)\(" database/seeders/`; `SELECT email FROM users WHERE email LIKE '%@example.%' OR email LIKE 'admin@%' OR email LIKE 'test@%';`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V6.3.2, V13.2.3

### SEC-AUT-11 — Los paneles de administración, diagnóstico y documentación nunca son accesibles sin autenticación
Telescope, Horizon, Pulse, Debugbar, phpMyAdmin/Adminer, consola de MinIO, `/docs` `/redoc` `/openapi.json` de FastAPI, `/debug/pprof` de Go, devtools de Nuxt.
*Si no:* lectura de peticiones, colas, consultas SQL y variables de entorno sin credenciales.
*Verificación:* `for p in telescope horizon pulse _debugbar docs redoc openapi.json debug/pprof/ phpmyadmin adminer.php; do printf '%s ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' "https://HOST/$p"; done` (esperado 401/403/404).
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V13.4.5, V15.2.3

---

## 3. TLS y red (NET)

### SEC-NET-01 — El servidor solo acepta TLS 1.2 y 1.3, y HTTP siempre redirige a HTTPS
Caddy trae `tls1.2` mínimo y `tls1.3` máximo por defecto, y su documentación pide no tocar `protocols`, `ciphers` ni `curves`. El perfil «Intermediate» de TLSRef es TLS 1.2+1.3 con suites ECDHE AEAD.
*Si no:* downgrade a protocolos rotos o tráfico en claro.
*Verificación:* `grep -nE 'protocols|ciphers|curves|auto_https|http://' Caddyfile`; `curl -sI http://HOST/ | head -1` (301/308); `testssl.sh -p https://HOST` (N1).
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V12.1.1, V12.2.1 · https://caddyserver.com/docs/caddyfile/directives/tls · https://docs.tlsref.org/server-side-tls.html

### SEC-NET-02 — Los certificados siempre se renuevan de forma automática, el directorio de datos de Caddy siempre es persistente y `on_demand` nunca se activa sin endpoint `ask`
Caddy renueva solo si los puertos 80/443 están abiertos, el DNS apunta al servidor y el directorio de datos es «writeable and persistent». Un `/data` sin volumen pierde los certificados en cada recreación y agota los límites de la CA.
*Si no:* certificado caducado en producción o emisión abusiva de certificados para dominios ajenos.
*Verificación:* `grep -nE '/data|caddy_data' docker-compose*.yml`; `grep -nA3 'on_demand' Caddyfile`; `echo | openssl s_client -connect HOST:443 -servername HOST 2>/dev/null | openssl x509 -noout -enddate`
*Severidad:* alta
*Fuente:* https://caddyserver.com/docs/automatic-https · OWASP ASVS 5.0 V12.2.2

### SEC-NET-03 — Docker nunca publica en `0.0.0.0` los puertos de servicios internos; solo se publican en `127.0.0.1` o no se publican
Docker enruta en la tabla `nat` antes de las cadenas que usa ufw: un puerto publicado es accesible desde Internet aunque ufw lo «bloquee». La documentación lo llama «insecure by default». El filtrado propio va en la cadena `DOCKER-USER`.
*Si no:* MySQL, Redis o un panel quedan abiertos al mundo con el firewall aparentemente cerrado.
*Verificación:* `docker ps --format '{{.Names}}\t{{.Ports}}' | grep -E '0\.0\.0\.0|\[::\]'` (solo debe aparecer Caddy con 80/443); `grep -nE '^\s*-\s*"?[0-9]+:[0-9]+' docker-compose*.yml`; `sudo iptables -S DOCKER-USER`
*Severidad:* crítica
*Fuente:* https://docs.docker.com/engine/network/packet-filtering-firewalls/#docker-and-ufw · https://docs.docker.com/engine/network/port-publishing/ · OWASP Docker Security Cheat Sheet RULE #5a

### SEC-NET-04 — Base de datos, Redis y almacenamiento de objetos nunca son alcanzables desde Internet, y Redis siempre exige autenticación
Redis solo entra en «protected mode» con la configuración por defecto y sin contraseña; con `bind 0.0.0.0` o un puerto publicado queda expuesto. Un `FLUSHALL` externo borra todo.
*Si no:* lectura o borrado completo de datos sin pasar por la aplicación.
*Verificación:* en el host: `sudo ss -tlnp | grep -E ':(3306|5432|6379|9000|9001|27017)\b'` (solo `127.0.0.1` o IP de red Docker); desde fuera (N1): `nc -zv -w3 HOST 3306; nc -zv -w3 HOST 6379`; `grep -nE 'requirepass|REDIS_PASSWORD' docker-compose*.yml .env` (sin imprimir valores).
*Severidad:* crítica
*Fuente:* https://redis.io/docs/latest/operate/oss_and_stack/management/security/ · OWASP Database Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html

### SEC-NET-05 — El firewall del host siempre deniega por defecto el tráfico entrante y solo abre 22, 80 y 443
En la Raspberry Pi casera, el router solo reenvía 80/443; SSH y paneles se alcanzan por VPN o túnel (interpretación).
*Si no:* cada servicio nuevo que escuche queda expuesto sin que nadie lo decida.
*Verificación:* `sudo ufw status verbose` (o `sudo nft list ruleset`); `sudo ss -tlnp` y comparar cada puerto en escucha con la lista permitida.
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V13.2.4 · CIS Benchmarks (distribución Linux correspondiente) — https://www.cisecurity.org/cis-benchmarks («sin verificar» el número de control)

### SEC-NET-06 — SSH solo acepta llaves públicas y nunca permite el inicio de sesión de root
OpenSSH trae `PasswordAuthentication yes` y `KbdInteractiveAuthentication yes` por defecto, y `PermitRootLogin prohibit-password`. Las tres se fijan en `no`. El usuario de despliegue no tiene sudo sin contraseña para todo (interpretación).
*Si no:* fuerza bruta de contraseñas contra el puerto 22 y compromiso directo de root.
*Verificación:* `sudo sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication|maxauthtries)'`; `ssh-audit HOST` (N1).
*Severidad:* crítica
*Fuente:* sshd_config(5) — https://man.openbsd.org/sshd_config · OWASP ASVS 5.0 V12.3.1

### SEC-NET-07 — fail2ban o CrowdSec siempre está activo y cubre al menos SSH
Con llaves obligatorias su valor es reducir ruido y frenar escaneos; con contraseñas es imprescindible.
*Si no:* intentos ilimitados contra SSH y contra el login web sin bloqueo a nivel de red.
*Verificación:* `systemctl is-active fail2ban crowdsec`; `sudo fail2ban-client status sshd`; `sudo cscli decisions list`
*Severidad:* media
*Fuente:* https://github.com/fail2ban/fail2ban (1.1.1) · https://docs.crowdsec.net/ (v1.8.1) · OWASP ASVS 5.0 V6.3.1

### SEC-NET-08 — El sistema operativo siempre aplica las actualizaciones de seguridad de forma automática
Debian/Ubuntu/Raspberry Pi OS: paquete `unattended-upgrades`. Un kernel parcheado no protege hasta reiniciar.
*Si no:* vulnerabilidades públicas explotables durante meses en el host y en Docker.
*Verificación:* `systemctl is-enabled apt-daily-upgrade.timer`; `cat /etc/apt/apt.conf.d/20auto-upgrades`; `ls -lt /var/log/unattended-upgrades/ | head -3`; `[ -f /var/run/reboot-required ] && echo REINICIO_PENDIENTE`
*Severidad:* alta
*Fuente:* https://wiki.debian.org/UnattendedUpgrades · OWASP Docker Security Cheat Sheet RULE #0

### SEC-NET-09 — La API de administración de Caddy y el daemon de Docker nunca escuchan fuera de localhost
La API de Caddy vive por defecto en `localhost:2019`. El socket de Docker por TCP (`2375/2376`) equivale a root remoto.
*Si no:* reconfiguración del proxy o ejecución de contenedores privilegiados por cualquiera que alcance el puerto.
*Verificación:* `grep -nE '^\s*admin' Caddyfile`; `sudo ss -tlnp | grep -E ':(2019|2375|2376)\b'`; `grep -nE 'tcp://|"hosts"' /etc/docker/daemon.json`
*Severidad:* crítica
*Fuente:* https://caddyserver.com/docs/caddyfile/options · OWASP Docker Security Cheat Sheet RULE #1

### SEC-NET-10 — La aplicación solo confía en `X-Forwarded-*` cuando la petición viene del proxy real, nunca de cualquier origen
Confiar en `*` solo es aceptable si el contenedor de la app no es alcanzable más que a través de Caddy (ver SEC-NET-03). Texto exacto de la opción `trusted_proxies` de Caddy y de la documentación de Laravel: **sin verificar** en esta sesión.
*Si no:* el cliente falsifica su IP y evade el límite de tasa, el bloqueo y la bitácora.
*Verificación:* `grep -rn "trustProxies" bootstrap/app.php`; `grep -n "trusted_proxies" Caddyfile`; resto solo revisión manual.
*Severidad:* media
*Fuente:* https://caddyserver.com/docs/caddyfile/options · https://laravel.com/docs/13.x/requests (sin verificar)

### SEC-NET-11 — El servidor web nunca sirve `.git`, `.env`, respaldos ni listados de directorio
La raíz servida es solo el directorio público (`public/` en Laravel, `.output/public` en Nuxt).
*Si no:* descarga del código fuente completo y de las credenciales.
*Verificación:* `for p in .git/HEAD .env .env.backup composer.json storage/logs/laravel.log backup.sql; do printf '%s ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' "https://HOST/$p"; done` (esperado 403/404); `grep -nE '^\s*root ' Caddyfile`
*Severidad:* crítica
*Fuente:* OWASP ASVS 5.0 V13.4.1, V13.4.3, V13.4.7

---

## 4. Contenedores (CNT)

### SEC-CNT-01 — Los contenedores nunca se ejecutan como root
`USER` en el Dockerfile o `user:` en compose.
*Si no:* una ejecución remota de código en la app es root dentro del contenedor y facilita la fuga al host.
*Verificación:* `docker inspect --format '{{.Name}} user={{.Config.User}}' $(docker ps -q)` (vacío o `0` = root); `hadolint Dockerfile` (DL3002); `trivy config .`
*Severidad:* alta
*Fuente:* OWASP Docker Security Cheat Sheet RULE #2 — https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html

### SEC-CNT-02 — Los contenedores nunca se ejecutan con `privileged`, con el socket de Docker montado ni compartiendo namespaces del host
Montar `/var/run/docker.sock` da control total del host. Si una herramienta lo necesita (Watchtower, Traefik, Portainer), se documenta como excepción.
*Si no:* comprometer ese contenedor es comprometer el host.
*Verificación:* `docker inspect --format '{{.Name}} priv={{.HostConfig.Privileged}} net={{.HostConfig.NetworkMode}} pid={{.HostConfig.PidMode}}' $(docker ps -q)`; `grep -nE 'privileged:|docker\.sock|network_mode:\s*host|pid:\s*host' docker-compose*.yml`; `kics scan -p . -t DockerCompose`
*Severidad:* crítica
*Fuente:* OWASP Docker Security Cheat Sheet RULE #1, #3

### SEC-CNT-03 — Todo servicio siempre declara `cap_drop: [ALL]` y `security_opt: [no-new-privileges]`, añadiendo solo las capacidades que necesita
En compose, `no-new-privileges` puede escribirse sin valor.
*Si no:* un binario setuid o una capacidad sobrante permite escalar dentro del contenedor.
*Verificación:* `docker inspect --format '{{.Name}} capdrop={{.HostConfig.CapDrop}} secopt={{.HostConfig.SecurityOpt}}' $(docker ps -q)`; `grep -nE 'cap_drop|cap_add|security_opt|no-new-privileges' docker-compose*.yml`
*Severidad:* media
*Fuente:* OWASP Docker Security Cheat Sheet RULE #3, #4 · https://docs.docker.com/reference/compose-file/services/

### SEC-CNT-04 — El sistema de archivos raíz del contenedor siempre es de solo lectura cuando el servicio lo permite
`read_only: true` más `tmpfs` para `/tmp` y volúmenes explícitos para lo que deba escribirse (en Laravel: `storage/` y `bootstrap/cache`).
*Si no:* el atacante deja webshells o modifica el código en ejecución.
*Verificación:* `docker inspect --format '{{.Name}} ro={{.HostConfig.ReadonlyRootfs}}' $(docker ps -q)`; `grep -nE 'read_only|tmpfs' docker-compose*.yml`
*Severidad:* media
*Fuente:* OWASP Docker Security Cheat Sheet RULE #8

### SEC-CNT-05 — Todo servicio siempre declara límites de memoria, CPU y procesos
*Si no:* un contenedor comprometido o con fuga de memoria tumba todos los proyectos del mismo VPS.
*Verificación:* `docker inspect --format '{{.Name}} mem={{.HostConfig.Memory}} cpus={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}}' $(docker ps -q)` (`0` = sin límite); `kics scan -p . -t DockerCompose` («Memory Not Limited», «Pids Limit Not Set»).
*Severidad:* baja
*Fuente:* OWASP Docker Security Cheat Sheet RULE #7

### SEC-CNT-06 — Las imágenes nunca contienen secretos en sus capas
Ni `ARG`/`ENV` con credenciales, ni `COPY .env`, ni `auth.json` de Composer, ni `.npmrc` con token. `.dockerignore` excluye `.env*` y `.git`. Los secretos de build usan montajes de BuildKit.
*Si no:* cualquiera con acceso a la imagen o al registro extrae las credenciales con `docker history`.
*Verificación:* `grep -nE '^(ARG|ENV) .*(KEY|SECRET|TOKEN|PASSWORD)' Dockerfile*`; `grep -nE '^\.env|^\.git' .dockerignore`; `docker history --no-trunc IMAGEN | grep -iE 'key|secret|token|password'`; `trivy image --scanners secret IMAGEN`
*Severidad:* crítica
*Fuente:* OWASP Docker Security Cheat Sheet RULE #12 · OWASP Secrets Management Cheat Sheet

### SEC-CNT-07 — Las imágenes base siempre se fijan por digest o, como mínimo, por versión exacta; nunca por `latest`
El tag es mutable: el incidente de Trivy de marzo de 2026 publicó malware bajo tags existentes, incluido `latest`.
*Si no:* un build reproduce hoy una imagen distinta a la revisada, quizá maliciosa.
*Verificación:* `grep -nE '^FROM ' Dockerfile* | grep -v '@sha256:'`; `grep -nE 'image:' docker-compose*.yml | grep -vE '@sha256:|:[0-9]+\.[0-9]+'`; `hadolint Dockerfile` (DL3006, DL3007).
*Severidad:* media
*Fuente:* OpenSSF Scorecard «Pinned-Dependencies» — https://github.com/ossf/scorecard/blob/main/docs/checks.md · OWASP Docker Security Cheat Sheet RULE #13

### SEC-CNT-08 — Toda imagen que llega a producción siempre se escanea, y las vulnerabilidades críticas con parche disponible nunca se despliegan
*Si no:* se despliega una imagen con fallos conocidos y explotables en el sistema base.
*Verificación:* `trivy image --severity HIGH,CRITICAL --ignore-unfixed IMAGEN`; alternativa `osv-scanner scan image IMAGEN`; comprobar que el paso existe en `.github/workflows/`.
*Severidad:* alta
*Fuente:* OWASP Docker Security Cheat Sheet RULE #9 · OWASP Top 10:2025 A03

### SEC-CNT-09 — El motor de Docker y el host siempre están actualizados, y la pertenencia al grupo `docker` solo se concede a quien ya es administrador
Docker advierte: «The docker group grants root-level privileges to the user».
*Si no:* cualquier cuenta del grupo `docker` es root del servidor; un motor viejo arrastra fugas de contenedor conocidas.
*Verificación:* `docker version --format '{{.Server.Version}}'` frente a la última (v29.8.2 a 2026-10-02); `getent group docker`; `sudo sh docker-bench-security.sh` (en el host).
*Severidad:* alta
*Fuente:* https://docs.docker.com/engine/install/linux-postinstall/ · OWASP Docker Security Cheat Sheet RULE #0 · CIS Docker Benchmark

---

## 5. Secretos (SCR)

### SEC-SCR-01 — Los archivos `.env` con valores reales nunca están en el repositorio
Solo `.env.example` con marcadores.
*Si no:* todo el que clone el repo (y GitHub) tiene las credenciales de producción.
*Verificación:* `git ls-files | grep -E '(^|/)\.env' | grep -vE '\.(example|dist|sample)$'`; `git log --all --diff-filter=A --name-only --format= | grep -E '(^|/)\.env' | sort -u`
*Severidad:* crítica
*Fuente:* OWASP Secrets Management Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html · OWASP ASVS 5.0 V13.3.1

### SEC-SCR-02 — En el servidor, `.env` nunca está dentro del directorio servido y siempre tiene permisos restrictivos
Permisos `600` o `640`, propiedad del usuario de despliegue.
*Si no:* otro usuario del VPS o una mala configuración del proxy expone todas las credenciales.
*Verificación:* `stat -c '%a %U:%G %n' .env`; `curl -s -o /dev/null -w '%{http_code}\n' https://HOST/.env` (403/404).
*Severidad:* crítica
*Fuente:* OWASP ASVS 5.0 V13.3.2, V13.4.7

### SEC-SCR-03 — El historial de git nunca contiene secretos; un secreto encontrado siempre se rota, no solo se borra
Reescribir el historial no invalida lo ya clonado. La push protection de GitHub está activa por defecto para repos públicos; en privados requiere GitHub Secret Protection (de pago).
*Si no:* credenciales válidas recuperables por cualquiera con acceso de lectura, para siempre.
*Verificación:* `gitleaks git --no-banner --redact --report-format json --report-path /RUTA_EXTERNA/gitleaks.json .`; `trufflehog git file://. --no-verification --json`
*Severidad:* crítica
*Fuente:* OWASP Secrets Management Cheat Sheet · https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection

### SEC-SCR-04 — Todo secreto siempre tiene dueño, fecha de última rotación y procedimiento de rotación documentado
Rotación obligatoria tras fuga, baja de un colaborador o compromiso de un proveedor. Incluye `APP_KEY`, credenciales de BD, llaves S3, tokens de terceros, deploy keys y DSN.
*Si no:* tras un incidente no se sabe qué rotar ni cómo, y la credencial filtrada sigue viva.
*Verificación:* solo revisión manual (existencia del inventario de secretos y su fecha).
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V13.1.4, V13.3.4 · OWASP Secrets Management Cheat Sheet

### SEC-SCR-05 — En CI los secretos solo viven en GitHub Secrets; nunca en el YAML, nunca en logs y nunca disponibles para PR de forks
GitHub pide no usar datos estructurados (JSON/YAML) como valor de secreto, porque no se enmascaran bien.
*Si no:* el secreto queda en el historial del repo o en los logs de ejecución.
*Verificación:* `gh secret list`; `grep -rnE '(password|token|secret|key)\s*:\s*[^$ ]' .github/workflows/`; `zizmor --offline .`
*Severidad:* alta
*Fuente:* OWASP Top 10 CI/CD CICD-SEC-6 — https://owasp.org/www-project-top-10-ci-cd-security-risks/ · https://docs.github.com/en/actions/reference/security/secure-use

### SEC-SCR-06 — Los archivos compose y de despliegue versionados nunca contienen secretos literales
Se inyectan con `env_file` no versionado o con `secrets:`.
*Si no:* las contraseñas de BD, Redis y MinIO quedan en git.
*Verificación:* `grep -nE '(PASSWORD|SECRET|KEY|TOKEN)\s*[:=]\s*[^$ {]' docker-compose*.yml Makefile`; `gitleaks dir --redact .`; `semgrep scan --config p/docker-compose --metrics=off .`
*Severidad:* alta
*Fuente:* OWASP Docker Security Cheat Sheet RULE #12 · OWASP Secrets Management Cheat Sheet

### SEC-SCR-07 — Producción nunca comparte credenciales con desarrollo, staging o CI
Una cuenta de BD, un bucket y un juego de llaves por entorno.
*Si no:* comprometer el entorno más débil compromete producción.
*Verificación:* solo revisión manual (comparar huellas, no valores: `sha256sum` de cada credencial en cada entorno).
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V13.3.2 · OWASP Top 10 CI/CD CICD-SEC-6

### SEC-SCR-08 — Los artefactos que llegan al cliente nunca contienen secretos
Todo lo que entra por `VITE_*`, `NUXT_PUBLIC_*`/`runtimeConfig.public`, `--dart-define` o se empaqueta en un APK/IPA es público.
*Si no:* llaves de API con permisos de servidor extraíbles desde el navegador o descompilando la app.
*Verificación:* `grep -rnE '^(VITE|NUXT_PUBLIC)_[A-Z_]*(SECRET|PRIVATE|PASSWORD|TOKEN)' .env.example`; `gitleaks dir --redact public/build` (o `.output/public`, `dist/`, `build/app/outputs`).
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V14.3.3, V13.3.1

---

## 6. Datos (DAT)

### SEC-DAT-01 — Todo dato en tránsito siempre va cifrado, incluidas las conexiones a base de datos, Redis, S3/MinIO y SMTP fuera del propio host
Dentro de la misma red Docker en un único host el riesgo es menor (interpretación); en cuanto cruza hosts, TLS con verificación de certificado.
*Si no:* credenciales y datos personales legibles en la red del proveedor.
*Verificación:* `grep -nE '^(DB_HOST|REDIS_HOST|AWS_ENDPOINT|AWS_URL|MAIL_ENCRYPTION|MAIL_SCHEME|MYSQL_ATTR_SSL_CA)' .env` (un `http://` o un host remoto sin SSL es hallazgo); en MySQL: `SHOW VARIABLES LIKE 'require_secure_transport';`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V12.3.1, V12.3.3 · OWASP Database Security Cheat Sheet

### SEC-DAT-02 — La aplicación nunca se conecta a la base de datos como root o superusuario; su cuenta solo tiene los privilegios que usa sobre su propia base
Una cuenta por aplicación. Las migraciones pueden usar una cuenta distinta con DDL.
*Si no:* una inyección SQL lee o destruye las bases de los 30 proyectos del mismo servidor.
*Verificación:* `grep -n '^DB_USERNAME' .env` (no `root`); `SHOW GRANTS FOR CURRENT_USER();` (sin `ALL PRIVILEGES ON *.*`, `FILE`, `SUPER` ni `GRANT OPTION`).
*Severidad:* alta
*Fuente:* OWASP Database Security Cheat Sheet · OWASP ASVS 5.0 V13.2.2

### SEC-DAT-03 — Los datos personales sensibles siempre se almacenan cifrados en reposo
Mínimo: cifrado del volumen o del disco. Para salud e imágenes médicas, además cifrado a nivel de campo o de objeto (en Laravel, casts `encrypted`). El nivel exigible es **interpretación** del Art. 18 LFPDPPP (medidas según riesgo y sensibilidad).
*Si no:* un respaldo, un disco reutilizado o un volcado robado exponen los expedientes.
*Verificación:* `lsblk -o NAME,FSTYPE,MOUNTPOINT | grep -i crypt`; `grep -rnE "'encrypted(:[a-z]+)?'" app/Models/`; resto solo revisión manual.
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V14.1.1, V14.2.4 · LFPDPPP Art. 18

### SEC-DAT-04 — Los respaldos siempre se cifran antes de salir del servidor y la llave nunca se guarda junto al respaldo
El cifrado del lado del servidor del bucket no protege frente a quien robe las credenciales del bucket; hace falta cifrado en cliente (restic, age, gpg).
*Si no:* quien acceda al bucket tiene todas las bases de datos.
*Verificación:* inspeccionar el script o `Makefile` de respaldo: `grep -rnE 'restic|age |gpg|openssl enc|mysqldump|pg_dump' Makefile scripts/ deploy/`; solo revisión manual para la custodia de la llave.
*Severidad:* alta
*Fuente:* OWASP Database Security Cheat Sheet · OWASP ASVS 5.0 V14.2.4

### SEC-DAT-05 — La restauración de un respaldo siempre se prueba de forma periódica y se registra la fecha
*Si no:* el día del incidente se descubre que el respaldo está vacío, corrupto o cifrado con una llave perdida.
*Verificación:* `restic -r REPO check --read-data-subset=5%` (lectura); existencia del registro de la última restauración: solo revisión manual.
*Severidad:* alta
*Fuente:* https://restic.readthedocs.io/en/stable/045_working_with_repos.html · OWASP Top 10:2025 A02 (interpretación)

### SEC-DAT-06 — Los respaldos siempre viven fuera del host de producción y siempre están protegidos contra borrado desde ese host
Versionado u Object Lock (WORM) en el bucket; la credencial que usa el servidor puede escribir pero no borrar ni cambiar el ciclo de vida.
*Si no:* un ransomware o un atacante con acceso al VPS borra producción y respaldos a la vez.
*Verificación:* `aws s3api get-bucket-versioning --bucket BUCKET`; `aws s3api get-object-lock-configuration --bucket BUCKET`; política de la credencial: solo revisión manual. Equivalente en MinIO: **sin verificar**.
*Severidad:* alta
*Fuente:* https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html

### SEC-DAT-07 — Los buckets nunca son públicos ni admiten acceso anónimo
Block Public Access activo; ninguna política con `"Principal": "*"`. En MinIO, sin política anónima.
*Si no:* imágenes médicas, documentos y respaldos descargables conociendo la URL.
*Verificación:* `aws s3api get-public-access-block --bucket BUCKET`; `aws s3api get-bucket-policy-status --bucket BUCKET`; prueba anónima: `curl -s -o /dev/null -w '%{http_code}\n' https://ENDPOINT_S3/BUCKET/` (403). Comando `mc anonymous get`: **sin verificar**.
*Severidad:* crítica
*Fuente:* https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html

### SEC-DAT-08 — Las URL prefirmadas siempre se emiten con la caducidad mínima necesaria, para un objeto y un método concretos
El tope técnico con SigV4 y credenciales de usuario IAM es 7 días; una URL prefirmada es reutilizable hasta que caduca. Para datos sensibles, minutos (interpretación).
*Si no:* un enlace reenviado o registrado en un log da acceso al archivo durante días.
*Verificación:* `grep -rnE "temporaryUrl\(|temporaryUploadUrl\(|generate_presigned_url|PresignGetObject|getSignedUrl" --include='*.php' --include='*.py' --include='*.go' --include='*.ts' .` y revisar el tiempo de cada llamada.
*Severidad:* media
*Fuente:* https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html

### SEC-DAT-09 — Todo almacén de datos personales siempre tiene un plazo de conservación definido y un borrado que se ejecuta
Base de datos, respaldos, logs, exportaciones temporales y archivos subidos. Liga con SEC-LEG-05 y SEC-LEG-08.
*Si no:* datos que ya no deberían existir aparecen en la siguiente fuga.
*Verificación:* `aws s3api get-bucket-lifecycle-configuration --bucket BUCKET`; `php artisan schedule:list | grep -iE 'prune|purge|clean'`; resto solo revisión manual.
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V14.2.7 · LFPDPPP Art. 10

### SEC-DAT-10 — Los datos de producción nunca se copian a desarrollo, staging o equipos personales sin anonimizar
*Si no:* los datos de pacientes acaban en portátiles y entornos sin los controles de producción.
*Verificación:* solo revisión manual (procedimiento de volcado; `grep -rnE 'mysqldump|pg_dump|db:pull|scp .*\.sql' Makefile scripts/`).
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V14.2.3 · LFPDPPP Art. 18 (interpretación)

---

## 7. Observabilidad de seguridad (OBS)

### SEC-OBS-01 — La aplicación siempre registra los eventos de seguridad con un vocabulario estable
Mínimo, con los nombres de OWASP: `authn_login_success`, `authn_login_fail`, `authn_login_lock`, `authn_password_change`, `authn_token_created`/`revoked`, `authz_fail`, `authz_change`, `authz_admin`, `privilege_permissions_changed`, `user_created`/`updated`/`deleted`, `excess_rate_limit_exceeded`, `sensitive_read`/`create`/`update`/`delete`, `session_created`/`expired`, `sys_startup`/`crash`, `malicious_csp_violation`.
*Si no:* tras un incidente no se puede reconstruir qué pasó ni a quién notificar.
*Verificación:* `grep -rnE "authn_|authz_|sensitive_|Login::class|Failed::class|Lockout::class|PasswordReset::class" app/`; resto solo revisión manual.
*Severidad:* alta
*Fuente:* OWASP Logging Vocabulary Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html · OWASP ASVS 5.0 V16.3.1–V16.3.3

### SEC-OBS-02 — Cada entrada de log siempre incluye cuándo, dónde, quién y qué, con hora en UTC o con desfase explícito, en formato estructurado
Campos de referencia: `datetime` (ISO 8601 con desfase), `appid`, `event`, `level`, `description`, `source_ip`, `request_uri`, `request_method`. El reloj del servidor se sincroniza por NTP. El formato estructurado (JSON) neutraliza la inyección de líneas.
*Si no:* no se pueden correlacionar eventos entre servicios ni confiar en la cronología.
*Verificación:* `timedatectl show -p NTPSynchronized -p Timezone`; `grep -nE "'channels'|JsonFormatter|'tap'" config/logging.php`
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V16.2.1, V16.2.2, V16.4.1 · OWASP Logging Vocabulary Cheat Sheet

### SEC-OBS-03 — Los logs nunca contienen contraseñas, tokens, identificadores de sesión, llaves, cadenas de conexión, datos de tarjeta ni datos de salud
Lista «Data to exclude» de OWASP. Atención a los volcados de petición completa, a `dd`/`dump` olvidados y a los bindings SQL.
*Si no:* el log se convierte en la fuga; cualquiera con acceso de lectura a logs suplanta usuarios.
*Verificación:* en el servidor: `grep -cEi 'password=|authorization: bearer|"token":|_session=' storage/logs/*.log` (solo el conteo, sin volcar contenido); `gitleaks dir --redact storage/logs`
*Severidad:* alta
*Fuente:* OWASP Logging Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html · OWASP ASVS 5.0 V16.2.5

### SEC-OBS-04 — Los logs de seguridad siempre se envían a un sistema separado del host de la aplicación, donde la aplicación no puede modificarlos
*Si no:* quien compromete el servidor borra sus huellas.
*Verificación:* `grep -nE "syslog|papertrail|loki|stack|LOG_CHANNEL" config/logging.php .env`; `grep -nE 'logging:|driver:' docker-compose*.yml`; solo revisión manual para el destino.
*Severidad:* media
*Fuente:* OWASP ASVS 5.0 V16.4.2, V16.4.3

### SEC-OBS-05 — El acceso y la modificación de datos sensibles siempre quedan en una bitácora de auditoría de solo inserción
La cuenta de BD de la aplicación no tiene `UPDATE` ni `DELETE` sobre la tabla de auditoría. En sistemas clínicos, NOM-024 define «registro de auditoría» como el registro cronológico que permite reconstruir la información a estados anteriores.
*Si no:* no se puede demostrar quién vio o alteró un expediente, ni detectar un abuso interno.
*Verificación:* `SHOW GRANTS FOR CURRENT_USER();` y comprobar la tabla de auditoría; `grep -rnE "activitylog|auditing|Auditable" composer.json app/Models/`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V16.3.2, V16.4.2 · NOM-024-SSA3-2012 §3.42, §6.6.2 — https://dof.gob.mx/nota_detalle.php?codigo=5280847&fecha=30/11/2012

### SEC-OBS-06 — Siempre existen alertas activas sobre picos de login fallido, fallos de autorización, errores 5xx, caducidad de certificados, respaldos fallidos y disco lleno
Top 10:2025 renombró A09 a «Security Logging & Alerting Failures» para subrayar que registrar sin alertar no sirve.
*Si no:* el ataque o la pérdida de respaldos se descubre semanas después.
*Verificación:* solo revisión manual (reglas de alerta en Sentry y en el monitor de uptime; último disparo de prueba).
*Severidad:* media
*Fuente:* OWASP Top 10:2025 A09 — https://owasp.org/Top10/2025/ · OWASP ASVS 5.0 V16.4.3

### SEC-OBS-07 — Sentry nunca recibe PII en sistemas con datos personales: `send_default_pii` desactivado, depuradores del servidor activos y `before_send` filtrando lo propio
El SDK no envía PII por defecto. En el servidor, «Use Default Scrubbers» cubre campos como `password`, `secret`, `token`, `api_key`, `auth`, `credentials` y valores con forma de tarjeta; hay que añadir en «Additional Sensitive Fields» los propios (CURP, RFC, expediente) y activar «Prevent Storing of IP Addresses». Los breadcrumbs incluyen consultas SQL y query strings.
*Si no:* datos de pacientes almacenados en un tercero fuera de México sin base legal.
*Verificación:* `grep -nE "send_default_pii|before_send|sql_bindings" config/sentry.php`; `grep -n '^SENTRY_SEND_DEFAULT_PII' .env`; ajustes del proyecto en Sentry: solo revisión manual.
*Severidad:* alta
*Fuente:* https://docs.sentry.io/platforms/php/guides/laravel/data-management/sensitive-data/ · https://docs.sentry.io/security-legal-pii/scrubbing/server-side-scrubbing/ · OWASP ASVS 5.0 V14.2.3

### SEC-OBS-08 — Producción nunca ejecuta en modo depuración ni devuelve trazas o detalles internos al usuario
`APP_DEBUG=false`, `APP_ENV=production`; FastAPI sin `debug=True` ni `--reload`; Nuxt sin devtools; Go sin pprof público.
*Si no:* la página de error muestra variables de entorno, consultas y rutas del servidor.
*Verificación:* `grep -nE '^(APP_DEBUG|APP_ENV)=' .env`; `curl -s https://HOST/ruta-inexistente-$(date +%s) | grep -ciE 'stack trace|whoops|ignition|traceback'` (esperado `0`).
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V13.4.2, V16.5.1 · OWASP Top 10:2025 A02

### SEC-OBS-09 — Los logs siempre tienen rotación, plazo de conservación definido y acceso restringido
Los logs contienen datos personales (IP, identificadores): heredan las reglas de retención de SEC-DAT-09.
*Si no:* el disco se llena y tumba el servicio, o se conservan datos personales sin límite.
*Verificación:* `ls /etc/logrotate.d/`; `grep -nE "'days'|daily" config/logging.php`; `stat -c '%a %U:%G' storage/logs`; `grep -nE 'max-size|max-file' docker-compose*.yml /etc/docker/daemon.json`
*Severidad:* baja
*Fuente:* OWASP ASVS 5.0 V16.1.1, V16.2.3

---

## 8. Cadena de suministro y CI (SUP)

### SEC-SUP-01 — Los lockfiles siempre están versionados y CI y despliegue siempre instalan desde el lockfile sin resolverlo de nuevo
`composer install` (nunca `composer update` en `make update`), `npm ci`, `pnpm install --frozen-lockfile`, `go.sum`, `uv.lock` o `requirements.txt` con hashes, `pubspec.lock` en aplicaciones.
*Si no:* producción instala una versión que nadie revisó, quizá publicada hace una hora por una cuenta comprometida.
*Verificación:* `git ls-files | grep -E '(composer\.lock|package-lock\.json|pnpm-lock\.yaml|go\.sum|uv\.lock|pubspec\.lock)$'`; `grep -nE 'composer update|npm install|npm i |pnpm install($| [^-])' Makefile .github/workflows/*.yml`
*Severidad:* alta
*Fuente:* OWASP Top 10 CI/CD CICD-SEC-3 · OpenSSF Scorecard «Pinned-Dependencies» · OWASP Top 10:2025 A03

### SEC-SUP-02 — Las dependencias siempre se auditan en CI y nunca se usan paquetes abandonados sin decisión registrada
*Si no:* vulnerabilidades publicadas con parche disponible siguen en producción.
*Verificación:* `composer audit --locked --format=json --abandoned=report`; `npm audit --omit=dev --audit-level=high --json`; `pnpm audit --prod --audit-level high --json`; `govulncheck ./...`; `pip-audit --require-hashes -r requirements.txt`; `osv-scanner scan source -r .`; presencia del paso: `grep -rnE 'composer audit|npm audit|pnpm audit|govulncheck|pip-audit|osv-scanner' .github/workflows/`
*Severidad:* alta
*Fuente:* OWASP ASVS 5.0 V15.1.1, V15.2.1 · OpenSSF Scorecard «Vulnerabilities» · https://getcomposer.org/doc/03-cli.md#audit

### SEC-SUP-03 — Las GitHub Actions de terceros siempre se fijan por SHA de commit completo, nunca por tag ni rama
GitHub: fijar por SHA completo «is currently the only way to use an action as an immutable release». En marzo de 2026, 76 de 77 tags de `aquasecurity/trivy-action` fueron reescritos con un ladrón de credenciales.
*Si no:* un tag reescrito ejecuta código ajeno con los secretos del repositorio.
*Verificación:* `grep -rnE 'uses:\s*[^ ]+@' .github/workflows/ | grep -vE '@[0-9a-f]{40}'`; `zizmor --offline .`
*Severidad:* alta
*Fuente:* https://docs.github.com/en/actions/reference/security/secure-use · GHSA-69fq-xp46-6x23 · OWASP Top 10 CI/CD CICD-SEC-8

### SEC-SUP-04 — Todo workflow siempre declara `permissions` con el mínimo necesario; el valor por defecto del `GITHUB_TOKEN` es solo lectura
*Si no:* una acción comprometida puede empujar código, publicar releases o modificar el propio workflow.
*Verificación:* `grep -L '^permissions:' .github/workflows/*.yml`; `gh api repos/OWNER/REPO/actions/permissions/workflow --jq .default_workflow_permissions` (esperado `read`).
*Severidad:* alta
*Fuente:* OpenSSF Scorecard «Token-Permissions» · OWASP Top 10 CI/CD CICD-SEC-5 · https://docs.github.com/en/actions/reference/security/secure-use

### SEC-SUP-05 — Los workflows nunca usan `pull_request_target` o `workflow_run` con checkout del código del PR, ni interpolan entrada no confiable dentro de `run:`
La entrada no confiable (título del PR, nombre de rama, cuerpo de issue) pasa por una variable de entorno intermedia.
*Si no:* un PR externo ejecuta código con los secretos del repo (Poisoned Pipeline Execution).
*Verificación:* `grep -rnE 'pull_request_target|workflow_run' .github/workflows/`; `grep -rnE 'run:.*\$\{\{\s*github\.(event|head_ref)' .github/workflows/`; `zizmor --offline .`
*Severidad:* alta
*Fuente:* OWASP Top 10 CI/CD CICD-SEC-4 · OpenSSF Scorecard «Dangerous-Workflow»

### SEC-SUP-06 — La rama de despliegue siempre está protegida: sin push directo, sin force-push y con las comprobaciones de CI obligatorias
En proyectos de una sola persona, al menos checks obligatorios y bloqueo de force-push y de borrado (interpretación).
*Si no:* una credencial robada empuja directo a la rama que `make update` despliega.
*Verificación:* `gh api repos/OWNER/REPO/branches/main/protection` (404 = sin protección); `gh api repos/OWNER/REPO/rulesets`
*Severidad:* media
*Fuente:* OWASP Top 10 CI/CD CICD-SEC-1 · OpenSSF Scorecard «Branch-Protection»

### SEC-SUP-07 — Framework, runtime y servicios de infraestructura siempre están en una versión con soporte de seguridad vigente
Hallazgos directos a 2026-10-02: **Laravel 11 sin parches de seguridad desde 2026-03-12**; MinIO community archivado y sin mantenimiento; Enlightn archivado. Aplica igual a PHP, Node, Go, Python, MySQL y Docker.
*Si no:* las vulnerabilidades nuevas del framework ya no reciben parche.
*Verificación:* `composer show laravel/framework | grep versions`; `php -v; node -v; go version; python3 --version`; `docker ps --format '{{.Image}}' | grep -i minio`
*Severidad:* alta
*Fuente:* https://laravel.com/docs/13.x/releases#support-policy · https://github.com/minio/minio · OWASP ASVS 5.0 V15.2.1

### SEC-SUP-08 — Todo repositorio siempre tiene una herramienta de actualización de dependencias activa, incluido el ecosistema `github-actions`, con un periodo de espera para versiones recién publicadas
Dependabot o Renovate. pnpm ofrece `minimumReleaseAge`; el equivalente en otros gestores está **sin verificar**.
*Si no:* las dependencias envejecen hasta que actualizar es un proyecto, o se adopta una versión maliciosa el mismo día de su publicación.
*Verificación:* `ls .github/dependabot.yml renovate.json 2>/dev/null`; `grep -n 'package-ecosystem' .github/dependabot.yml`; `grep -n 'minimumReleaseAge' pnpm-workspace.yaml`
*Severidad:* media
*Fuente:* OpenSSF Scorecard «Dependency-Update-Tool» · https://pnpm.io/cli/audit

### SEC-SUP-09 — Cada versión desplegada siempre tiene un SBOM y, si se publican imágenes o binarios, siempre van firmados o con procedencia
SLSA Build L1 = procedencia que muestra cómo se construyó; L2 = procedencia firmada por plataforma de build alojada. Para despliegues por `git pull` sin artefacto, el SBOM del lockfile es el control aplicable (interpretación).
*Si no:* ante una vulnerabilidad nueva no se sabe qué proyectos de los 30 están afectados.
*Verificación:* `trivy fs --format cyclonedx --output /RUTA_EXTERNA/sbom.cdx.json .`; `npm sbom --sbom-format cyclonedx` (**sin verificar**); `cosign verify IMAGEN` (**sin verificar** la sintaxis).
*Severidad:* baja
*Fuente:* OWASP ASVS 5.0 V15.1.2 · SLSA v1.2 Build track — https://slsa.dev/spec/v1.2/ · OpenSSF Scorecard «Signed-Releases»

### SEC-SUP-10 — Las herramientas de seguridad y de build siempre se instalan fijadas por versión y verificadas; nunca con `curl | sh` ni con la etiqueta `latest`
Versiones que el aviso de Trivy da como seguras: binario v0.69.2 y v0.69.3, `trivy-action` v0.35.0, `setup-trivy` v0.2.6. Las maliciosas fueron el binario v0.69.4 y las imágenes de Docker Hub v0.69.5 y v0.69.6.
*Si no:* el escáner, que corre con acceso a todo el código y a los secretos de CI, se convierte en el vector.
*Verificación:* `grep -rnE 'curl .*\|\s*(sudo )?(sh|bash)|:latest' .github/workflows/ Makefile Dockerfile*`
*Severidad:* media
*Fuente:* GHSA-69fq-xp46-6x23 — https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23 · OWASP Top 10 CI/CD CICD-SEC-8, CICD-SEC-9

### SEC-SUP-11 — El servidor solo despliega desde la rama protegida y con una credencial de solo lectura sobre el repositorio
Deploy key sin escritura; `make update` no acepta una rama arbitraria. Sin despliegue automático, la revisión previa al `make update` es el control de flujo (interpretación).
*Si no:* un servidor comprometido puede empujar código al repo, o se despliega una rama sin revisar.
*Verificación:* `gh api repos/OWNER/REPO/keys --jq '.[] | {title, read_only}'`; `git -C /RUTA/APP rev-parse --abbrev-ref HEAD`; `grep -nE 'git (pull|fetch|checkout)' Makefile`
*Severidad:* media
*Fuente:* OWASP Top 10 CI/CD CICD-SEC-1, CICD-SEC-2

---

## 9. Legal — México (LEG)

Base: LFPDPPP **nueva**, DOF 20-03-2025 (vigente desde el 21-03-2025; última reforma DOF 14-11-2025). Cambios relevantes frente a la de 2010, comprobados en el texto: la autoridad ya no es el INAI sino la **Secretaría Anticorrupción y Buen Gobierno** (Art. 2 fr. XV; transitorios); la ley de 2010 queda abrogada (transitorio Segundo); el lenguaje pasa a «persona titular» y «persona encargada»; las multas se expresan en UMA (hasta 320 000, duplicables en datos sensibles). Las obligaciones de seguridad (Art. 18–20) conservan el contenido de la ley anterior. El Reglamento de 2011 sigue publicado como vigente y cita la numeración antigua; que no exista aún uno nuevo queda **sin verificar**. Esto no es asesoría jurídica.

### SEC-LEG-01 — Todo sistema con datos personales siempre tiene documentadas sus medidas de seguridad administrativas, técnicas y físicas, con inventario de datos y de sistemas
El Art. 18 exige establecerlas y mantenerlas, atendiendo al riesgo, la sensibilidad y el desarrollo tecnológico, y no menores a las que el responsable usa para su propia información. El Reglamento (Art. 61) enumera inventario, análisis de riesgo, análisis de brecha, plan de trabajo, auditorías y capacitación.
*Si no:* infracción sancionable y, ante una vulneración, imposibilidad de acreditar diligencia.
*Verificación:* solo revisión manual (existencia y fecha del documento de seguridad e inventario). El informe del propio auditor sirve como evidencia de «revisiones o auditorías» (interpretación).
*Severidad:* alta
*Fuente:* LFPDPPP Art. 18 — https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf · Reglamento LFPDPPP Art. 57–62 — https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LFPDPPP.pdf

### SEC-LEG-02 — Siempre existe un procedimiento para informar de inmediato a las personas titulares de una vulneración que afecte de forma significativa sus derechos
El Art. 19 obliga a informar «de forma inmediata». El Reglamento (Art. 63–66) define vulneración (pérdida, robo o copia, acceso no autorizado, alteración) y el contenido mínimo del aviso: naturaleza del incidente, datos comprometidos, recomendaciones, acciones correctivas y medios de contacto. La ley no fija un plazo en horas ni exige, en su texto, notificar a la autoridad (interpretación de la lectura del Art. 19).
*Si no:* infracción; además, sin bitácora (SEC-OBS-01, SEC-OBS-05) no se puede saber a quién avisar.
*Verificación:* solo revisión manual (plan de respuesta, plantilla de aviso, capacidad de listar titulares afectados a partir de los logs).
*Severidad:* alta
*Fuente:* LFPDPPP Art. 19 · Reglamento LFPDPPP Art. 63–66

### SEC-LEG-03 — Los datos personales sensibles solo se tratan con consentimiento expreso y por escrito, del que siempre se conserva evidencia
El Art. 8 admite firma autógrafa, firma electrónica o «cualquier mecanismo de autenticación». Sensibles (Art. 2 fr. VI): salud presente o futura, información genética, origen étnico, creencias, opiniones políticas, preferencia sexual. Tampoco pueden crearse bases con datos sensibles sin finalidad legítima y concreta. Control técnico: registro de consentimiento con titular, fecha, versión del aviso y mecanismo.
*Si no:* tratamiento ilícito; las sanciones se duplican en datos sensibles (Art. 59 fr. IV y Art. 64).
*Verificación:* existencia de una tabla o registro de consentimientos: `grep -rniE 'consent|consentimiento' database/migrations/ app/Models/`; resto solo revisión manual.
*Severidad:* crítica
*Fuente:* LFPDPPP Art. 2 fr. VI, Art. 8, Art. 59, Art. 64

### SEC-LEG-04 — El sistema siempre permite localizar, exportar, corregir y cancelar los datos de una persona titular dentro del plazo legal
Derechos ARCO (Art. 21–26). El responsable comunica su determinación en un máximo de 20 días y la hace efectiva en los 15 días siguientes; ambos plazos ampliables una sola vez (Art. 31). «Días» son días hábiles (Art. 2 fr. VIII). Debe existir una persona o área designada (Art. 29).
*Si no:* incumplimiento de plazo y procedimiento ante la Secretaría.
*Verificación:* solo revisión manual (¿se pueden reunir todos los datos de un titular, incluidos archivos en S3, respaldos y Sentry?).
*Severidad:* media
*Fuente:* LFPDPPP Art. 21–31

### SEC-LEG-05 — Los datos que ya no son necesarios siempre se bloquean y después se suprimen; nunca se conservan sin plazo
Art. 10: cumplida la finalidad, supresión previo bloqueo. Art. 24: la cancelación abre un periodo de bloqueo igual al plazo de prescripción, durante el cual los datos no pueden tratarse. Los datos de incumplimiento contractual se eliminan a los 72 meses. Para sensibles, el periodo de tratamiento debe ser el mínimo indispensable (Art. 12). Control técnico: estado «bloqueado» inaccesible para la operación normal y purga programada. Un `deleted_at` que sigue siendo consultable no es bloqueo (interpretación).
*Si no:* conservación indebida; mayor superficie en cada fuga.
*Verificación:* `php artisan schedule:list | grep -iE 'prune|purge'`; `grep -rn "SoftDeletes" app/Models/ | wc -l` y comprobar si hay purga definitiva; resto solo revisión manual.
*Severidad:* media
*Fuente:* LFPDPPP Art. 2 fr. III, Art. 10, Art. 12, Art. 24

### SEC-LEG-06 — Todo punto donde se recaban datos por medios electrónicos siempre muestra el aviso de privacidad, al menos en su modalidad simplificada
El aviso simplificado remite al integral (Art. 16 fr. II). Un cambio de finalidad exige nuevo consentimiento (Art. 11).
*Si no:* tratamiento sin información previa; infracción.
*Verificación:* `curl -s https://HOST/register | grep -ciE 'aviso de privacidad'`; `curl -s -o /dev/null -w '%{http_code}\n' https://HOST/aviso-de-privacidad` (ajustar ruta).
*Severidad:* media
*Fuente:* LFPDPPP Art. 11, Art. 14–16

### SEC-LEG-07 — Todo tercero que trata datos por cuenta del responsable siempre está identificado y obligado a confidencialidad, incluidos los proveedores de nube
Art. 20: controles para que quien intervenga en el tratamiento guarde confidencialidad, incluso al terminar la relación. El Reglamento (Art. 50–52) regula al encargado y el cómputo en la nube. Control técnico: inventario de subencargados (hosting del VPS, S3, Sentry, correo, SMS, proveedores de IA) con la región donde alojan y el contrato aplicable.
*Si no:* datos de salud enviados a un tercero sin instrumento jurídico ni cobertura en el aviso de privacidad.
*Verificación:* `grep -nE '^(SENTRY_|MAIL_|AWS_|OPENAI_|ANTHROPIC_|TWILIO_|.*_DSN|.*_API_KEY)' .env.example` para listar terceros; resto solo revisión manual.
*Severidad:* alta
*Fuente:* LFPDPPP Art. 20, Art. 35–36 · Reglamento LFPDPPP Art. 50–52

### SEC-LEG-08 — Los sistemas con información clínica nunca eliminan el expediente antes de 5 años desde el último acto médico y siempre aplican autenticación, autorización por roles y registro de auditoría
NOM-004-SSA3-2012 §5.4: conservación mínima de 5 años. NOM-024-SSA3-2012 §6.6: sistema de gestión de seguridad de la información, documentos electrónicos «inalterables», autenticación de todos los usuarios (se recomiendan factores adicionales), autorización basada en roles, cifrado y autenticación en el intercambio. Si el proyecto de imágenes médicas es jurídicamente un SIRES o parte del expediente clínico es **interpretación** a confirmar con un abogado. Vigencia actual de ambas NOM comprobada solo por su texto en el DOF de 2012: **sin verificar** que no haya modificación posterior.
*Si no:* borrado ilícito de expedientes, o un sistema clínico sin trazabilidad.
*Verificación:* confirmar que la purga de SEC-LEG-05 excluye registros clínicos con menos de 5 años; `grep -rnE 'Gate::|Policy|role|permission' app/ | head`; SEC-OBS-05; resto solo revisión manual.
*Severidad:* alta
*Fuente:* NOM-004-SSA3-2012 §5.4 — https://dof.gob.mx/nota_detalle.php?codigo=5272787&fecha=15/10/2012 · NOM-024-SSA3-2012 §6.6 — https://dof.gob.mx/nota_detalle.php?codigo=5280847&fecha=30/11/2012

---

## 10. Tabla de herramientas

Versiones y fechas tomadas de la API de releases de GitHub el 2026-10-02 salvo que se indique. El ruido es una estimación propia, no un dato de la fuente. «Solo lectura» se refiere al repo o sistema auditado.

### 10.1 Estáticas locales (N0)

| Herramienta | Stack | Comando | Qué detecta | Solo lectura | Ruido | Mantenida a 2026 |
|---|---|---|---|---|---|---|
| **Semgrep CE** | PHP, Go, JS/TS, Python (GA); Dart, Dockerfile, YAML (experimental) | `semgrep scan --config p/default --config p/owasp-top-ten --metrics=off --json . > /RUTA_EXTERNA/semgrep.json` | Patrones de inyección, criptografía débil, configuración insegura. Gratis: motor LGPL, sin análisis entre archivos (eso es Pro). No existen `p/laravel`, `p/dart` ni `p/flutter` (404); `p/php` trae 24 reglas, 3 de Laravel | Sí (no usar `--autofix`). Con reglas del registro envía métricas salvo `--metrics=off` | Medio | Sí — v1.179.0 (2026-10-02) · https://docs.semgrep.dev/cli-reference |
| Semgrep, reglas de infraestructura | Dockerfile, compose, Actions | `semgrep scan --config p/dockerfile --config p/docker-compose --config p/github-actions --config p/secrets --metrics=off .` | 7 + 6 + 12 + 52 reglas respectivamente | Sí | Bajo | Sí |
| **Gitleaks** | Cualquiera | `gitleaks git --no-banner --redact --report-format json --report-path /RUTA_EXTERNA/gitleaks.json .` · árbol actual: `gitleaks dir --redact .` | Secretos en historial y en archivos. `detect`/`protect` están obsoletos desde v8.19.0 | Sí | Medio (entropía genérica) | Sí, en modo mantenimiento — v8.30.1 (2026-03-21); solo parches de seguridad · https://github.com/gitleaks/gitleaks |
| Betterleaks | Cualquiera | `betterleaks git /ruta/al/repo` | Sucesor de Gitleaks por el mismo autor; añade validación y hasta revocación de secretos | Sí si no se usa validación ni revocación (flags para desactivarlas: **sin verificar**) | Bajo-medio | Sí — v1.9.0 (2026-09-29), v2 en desarrollo · https://github.com/betterleaks/betterleaks |
| **TruffleHog** | Cualquiera, imágenes | `trufflehog git file://. --no-verification --json` · `trufflehog filesystem . --no-verification --json` · `trufflehog docker --image IMAGEN --no-verification` | Más de 700 detectores de credenciales | Sí con `--no-verification`. **Sin ese flag se autentica contra el proveedor con cada secreto hallado** (`--results=verified` da casi cero falsos positivos, pero ya no es pasivo) | Alto sin verificación; muy bajo con ella | Sí — v3.97.9 (2026-09-24) · https://github.com/trufflesecurity/trufflehog |
| **Trivy** | Todos; imágenes; Dockerfile | `trivy fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --disable-telemetry .` · `trivy image --severity HIGH,CRITICAL --ignore-unfixed IMAGEN` · `trivy config .` | Vulnerabilidades en lockfiles y paquetes del SO, secretos, configuración de Dockerfile/K8s/Terraform. **No analiza `docker-compose.yml`** (escáneres por defecto: azure-arm, cloudformation, dockerfile, helm, kubernetes, terraform, ansible) | Sí (descarga base de datos) | Medio | Sí — v0.75.0 (2026-10-01). Instalar fijado y verificado por el incidente de 2026-03 · https://github.com/aquasecurity/trivy |
| **OSV-Scanner** | Composer, npm, pnpm, bun, Go, pip/uv/poetry, pub | `osv-scanner scan source -r .` · `osv-scanner scan image IMAGEN:TAG` | Vulnerabilidades conocidas a partir de lockfiles (`composer.lock`, `package-lock.json`, `pnpm-lock.yaml`, `go.mod`, `uv.lock`, `requirements.txt`, `pubspec.lock`) | Sí (envía nombres y versiones a osv.dev; no usar el subcomando `fix`) | Bajo | Sí — v2.6.0 (2026-09-14) · https://github.com/google/osv-scanner |
| `composer audit` | PHP/Laravel | `composer audit --locked --format=json --abandoned=report` | Avisos de seguridad, paquetes abandonados y malware. Sale con 1 si hay hallazgos | Sí (`--locked` audita el lock sin tocar `vendor/`) | Bajo | Sí — Composer 2.10.3 (2026-08-27) · https://getcomposer.org/doc/03-cli.md#audit |
| `npm audit` | Node/React/Nuxt | `npm audit --omit=dev --audit-level=high --json` · `npm audit signatures` | Vulnerabilidades; `signatures` verifica firmas del registro y atestaciones de procedencia | Sí (sin el subcomando `fix`) | Medio-alto (transitivas de build) | Sí · https://docs.npmjs.com/cli/v11/commands/npm-audit |
| `pnpm audit` | Node | `pnpm audit --prod --audit-level high --json` | Igual que npm, sobre `pnpm-lock.yaml` | Sí (sin `--fix`) | Medio | Sí — docs v11/v12 · https://pnpm.io/cli/audit |
| **govulncheck** | Go | `govulncheck ./...` (JSON: `-format json`, que siempre sale con 0) | Vulnerabilidades solo en funciones realmente alcanzadas por el código | Sí (consulta vuln.go.dev) | Muy bajo | Sí — v1.8.0 (2026-09-08, pkg.go.dev) · https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck |
| gosec | Go | `gosec -fmt json -out /RUTA_EXTERNA/gosec.json -exclude-generated ./...` | Credenciales en código, TLS inseguro, SQL concatenado, reglas `G7xx` de taint. Requiere Go ≥ 1.25 | Sí (no usar las opciones de corrección por IA) | Medio | Sí — v2.29.0 (2026-08-26) · https://github.com/securego/gosec |
| pip-audit | Python/FastAPI | `pip-audit --require-hashes -r requirements.txt` · fijado sin hashes: `pip-audit --no-deps -r requirements.txt` · proyecto: `pip-audit --locked .` | Vulnerabilidades en dependencias Python. `--locked` solo admite `pyproject.toml` y `pylock.*.toml` (para `uv.lock`, usar osv-scanner) | Sí con `--no-deps`, `--require-hashes` o `--locked`; sin ellos resuelve con pip. No usar `--fix` | Bajo | Sí — v2.10.1 (2026-06-10) · https://github.com/pypa/pip-audit |
| Bandit | Python | `bandit -r . -f json -o /RUTA_EXTERNA/bandit.json --severity-level=high` | `eval`, `subprocess` con shell, deserialización, criptografía débil | Sí | Alto sin filtrar severidad | Sí — 1.9.4 (2026-02-25) · https://bandit.readthedocs.io/ |
| `dart pub outdated` | Dart/Flutter | `dart pub outdated --json` | Dependencias atrasadas. Los avisos de seguridad (GitHub Advisory Database) los muestra pub al resolver, no este comando | Sí. (`dart pub get` sí puede reescribir `pubspec.lock`) | Bajo | Sí · https://dart.dev/tools/pub/cmd/pub-outdated · https://dart.dev/tools/pub/security-advisories |
| MobSF | Flutter (APK/IPA) | Servicio propio; análisis estático del binario | Secretos embebidos, permisos, configuración de red y almacenamiento inseguro | Sí sobre el binario; exige levantar un servidor. Uso concreto **sin verificar** | Alto | Sí — v4.5.3 (2026-09-21) · https://github.com/MobSF/Mobile-Security-Framework-MobSF |
| hadolint | Dockerfile | `hadolint -f json Dockerfile` · `docker run --rm -i hadolint/hadolint < Dockerfile` | `USER` root (DL3002), imagen sin versión (DL3006), `latest` (DL3007), shell inseguro | Sí | Medio (muchas reglas de estilo) | Sí — v2.15.1 (2026-07-31) · https://github.com/hadolint/hadolint |
| **KICS** | docker compose, Dockerfile | `kics scan -p . -t DockerCompose,Dockerfile --report-formats json -o /RUTA_EXTERNA/kics --no-progress` | 23 consultas de compose: socket montado, `privileged`, sin `no-new-privileges`, capacidades, namespaces del host, puerto no ligado a interfaz, sin límites | Sí | Medio | Sí — v2.2.0 (2026-09-17) · https://docs.kics.io/latest/queries/dockercompose-queries/ |
| Checkov | Dockerfile, Actions, secretos | `checkov -d . --framework dockerfile github_actions secrets` (flags **sin verificar**) | Políticas `CKV_DOCKER_*`, `CKV_GHA_*`. **Sin soporte de docker compose** en su índice de políticas | Sí | Medio | Sí — 3.3.21 (2026-09-30) · https://www.checkov.io/5.Policy%20Index/all.html |
| Larastan / PHPStan | Laravel | `vendor/bin/phpstan analyse --error-format=json` (requiere estar en `require-dev`) | Errores de tipos. **No hace análisis de taint** ni trae reglas de seguridad propias | Sí | Alto en código heredado | Sí — Larastan v3.12.2 (2026-09-19), PHPStan 2.2.16 · https://github.com/larastan/larastan |
| **Psalm + psalm-plugin-laravel** | Laravel | `./vendor/bin/psalm --taint-analysis` | Taint de petición a sumidero: SQLi, XSS, shell, path traversal, SSRF, open redirect | El análisis sí. **Instalarlo modifica `composer.json`**: correrlo en una copia. Plugin 3.x = Psalm 6 estable + Laravel 11; 4.x = Psalm 7 beta + Laravel 12/13 | Medio | Sí — plugin v4.16.5 (2026-10-01), Psalm 6.19.1 · https://github.com/psalm/psalm-plugin-laravel |
| Enlightn | Laravel | — | — | — | — | **No** — archivado el 2024-06-15 · https://github.com/enlightn/enlightn |
| **zizmor** | GitHub Actions | `zizmor --offline .` | Inyección de plantillas, permisos excesivos, acciones sin fijar, persistencia de credenciales | Sí; con token en el entorno pasa a modo en línea, `--offline` lo impide | Bajo | Sí — v1.30.1 (2026-09-09) · https://docs.zizmor.sh/usage/ |
| OpenSSF Scorecard | Repos en GitHub | `scorecard --repo=github.com/OWNER/REPO --show-details` (necesita `GITHUB_AUTH_TOKEN`) | Branch-Protection, Token-Permissions, Pinned-Dependencies, Dangerous-Workflow, Vulnerabilities, SAST, Signed-Releases | Sí (lee por API) | Medio (varias comprobaciones pensadas para proyectos abiertos) | Sí — v5.5.0 (2026-04-23) · https://github.com/ossf/scorecard |
| Grype / Syft | Imágenes, directorios | `grype IMAGEN` · `syft dir:. -o cyclonedx-json` (sintaxis **sin verificar**) | Vulnerabilidades / SBOM. Alternativa a Trivy | Sí | Medio | Sí — Grype v0.119.0, Syft v1.54.0 · https://github.com/anchore/grype |
| docker-bench-security | Host Docker | `sudo sh docker-bench-security.sh` | Controles del CIS Docker Benchmark **v1.6.0** (hay v1.8/v1.9) | Sí; requiere root en el host | Medio | Parcial — última release v1.6.1 (2023-12-20), commits hasta 2026-06 · https://github.com/docker/docker-bench-security |
| Dockle | Imágenes | `dockle IMAGEN` | Buenas prácticas CIS de imagen (usuario, `ADD`, setuid) | Sí | Medio | Parcial — v0.4.15 (2025-01-06) · https://github.com/goodwithtech/dockle |
| Lynis | Host Linux | `sudo lynis audit system` (sintaxis **sin verificar**) | Endurecimiento del SO: SSH, kernel, permisos, servicios | Sí; se ejecuta en el servidor | Alto | Sí — 3.1.7 (2026-06-25) · https://github.com/CISOfy/lynis |

### 10.2 Remotas pasivas (N1) — solo contra hosts propios

| Herramienta | Stack | Comando | Qué detecta | Solo lectura | Ruido | Mantenida a 2026 |
|---|---|---|---|---|---|---|
| `curl` | Cualquier web | `curl -sSI https://HOST/` | Cabeceras de respuesta (reglas HDR) | Sí; una petición normal | Nulo | Sí |
| **MDN HTTP Observatory** | Cualquier web | `npx @mdn/mdn-http-observatory HOST` · `curl -X POST 'https://observatory-api.mdn.mozilla.net/api/v2/scan?host=HOST'` | CSP, cookies, CORS, redirección, HSTS, SRI, `nosniff`, framing; nota de A+ a F. API comprobada en vivo el 2026-10-02 | Sí; un escaneo por host por minuto. La variante API hace la petición desde MDN y **guarda el resultado** | Bajo | Sí — v1.7.1 (2026-09-03) · https://github.com/mdn/mdn-http-observatory |
| securityheaders.com | Cualquier web | Interfaz web (opciones «Hide results» y «Follow redirects») | Presencia y calidad de cabeceras; nota A+–F | Sí; el resultado es público si no se marca «Hide results». Proyecto de Snyk; condiciones de la API **sin verificar** | Bajo | Sí (sitio activo) · https://securityheaders.com/ |
| **testssl.sh** | TLS en cualquier puerto | `testssl.sh --quiet --severity MEDIUM --jsonfile /RUTA_EXTERNA/tls.json https://HOST` · parcial: `-p` protocolos, `-S` servidor, `-h` cabeceras, `-U` vulnerabilidades | Protocolos, suites, certificado, vulnerabilidades TLS conocidas. El resultado no sale de la máquina | Sí, pero abre cientos de conexiones: puede activar fail2ban/CrowdSec | Bajo | Sí — v3.2.4 (2026-07-12) · https://testssl.sh/ |
| Qualys SSL Labs | TLS público | Interfaz web. La API v4 exige registro con **correo de organización (no admite Gmail)** | Nota de configuración TLS | Sí; lo ejecuta un tercero; `publish` desactivado por defecto. Uso comercial no permitido sin permiso | Bajo | Sí · https://github.com/ssllabs/ssllabs-scan/blob/master/ssllabs-api-docs-v4.md |
| ssh-audit | SSH | `ssh-audit HOST` · políticas: `ssh-audit -L`, `ssh-audit -P "NOMBRE" HOST` | Algoritmos débiles, versión, cumplimiento de guías de endurecimiento | Sí; solo negocia el protocolo | Bajo | Sí — v3.9.0 (2026-07-04) · https://github.com/jtesta/ssh-audit |

### 10.3 Activas (N2) — requieren autorización explícita y entorno propio

El auditor **no las ejecuta**; solo las menciona como paso posterior que decide el usuario, contra staging propio.

| Herramienta | Qué hace | Por qué no es solo lectura | Versión |
|---|---|---|---|
| nuclei | Plantillas de detección de CVE y malas configuraciones | Envía cargas de explotación y fuzzing; puede alterar estado | v3.11.1 (2026-08-08) |
| OWASP ZAP | Proxy y escáner DAST | El escaneo activo ataca formularios y parámetros; crea registros basura | v2.17.0 (2025-12-15) |
| sqlmap | Explotación de inyección SQL | Explota la vulnerabilidad: lee y puede modificar la base de datos | 1.10 (2026-01-01) |

---

## 11. Dudas y huecos

1. **Reglamento de la LFPDPPP.** El publicado por la Cámara de Diputados sigue siendo el de 2011, con numeración de la ley abrogada. No confirmé si la Secretaría Anticorrupción y Buen Gobierno ha emitido reglamento o lineamientos nuevos.
2. **NOM-004 y NOM-024.** Leí el texto del DOF de 2012; no comprobé modificaciones posteriores ni si el proyecto de imágenes médicas es un SIRES en sentido legal.
3. **Livewire 3.** La documentación de CSP consultada es la de la versión 4. Los proyectos en Laravel 11 con Livewire 3 no tienen confirmado el camino a una CSP sin `unsafe-eval`.
4. **MinIO.** Con el repositorio archivado, falta decidir destino (AIStor Free, otro servidor S3 o S3 gestionado). Los comandos `mc` de verificación no se comprobaron.
5. **Checkov, Grype, Syft, Lynis, cosign, `npm sbom`.** Versión confirmada; flags no comprobados en esta sesión.
6. **Trusted proxies.** No localicé el texto exacto en la documentación de Caddy ni de Laravel.
7. **CIS.** Los benchmarks son de descarga registrada; las reglas de host citan CIS de forma genérica, sin número de control.
8. **Semgrep para Dart y Laravel.** Dart es experimental y sin ruleset en el registro; Laravel solo tiene 3 reglas. Para Laravel el análisis de taint real es Psalm; para Flutter no hay SAST gratuito equivalente.
9. **Ruido.** Las valoraciones de la tabla son estimación propia; conviene calibrarlas contra dos o tres repos reales antes de fijar umbrales.
10. **Ninguna herramienta está instalada** en el equipo del usuario (comprobado con `which`): solo `npm`, `pnpm`, `dart` y `docker`. El auditor necesita un paso de instalación fijada y verificada (SEC-SUP-10).
