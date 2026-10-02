# 01 — Núcleo web OWASP (agnóstico de stack)

Catálogo de reglas para `elyares-auditor`. Alcance: aplicación web, sin reglas específicas de framework. Fuera de alcance (otros investigadores): API/móvil/reglas por stack (2), código generado por IA y apps con LLM (3), infraestructura y herramientas (4).

Fecha de la investigación: 2026-10-02. Todo lo citado se leyó ese día en la fuente primaria (repositorios `OWASP/Top10`, `OWASP/ASVS`, `OWASP/CheatSheetSeries`, `OWASP/www-project-proactive-controls`). Lo que no se pudo confirmar va marcado **sin verificar**.

## 1. Estándares vigentes

| Estándar | Versión vigente | Fecha confirmada | URL primaria | Cómo se confirmó |
|---|---|---|---|---|
| OWASP Top 10 | **2025** (final, 8.ª edición) | Aviso de *release candidate* retirado del repo el 2025-12-24. Fecha oficial de publicación: **sin verificar** | https://owasp.org/Top10/2025/ | `owasp.org/www-project-top-ten`: "The most current released version is the OWASP Top Ten 2025"; commits "Remove RC notice" / "Removed RC" en `OWASP/Top10` |
| OWASP ASVS | **5.0.0** | 2025-05-30 (release `v5.0.0_release`) | https://github.com/OWASP/ASVS/tree/v5.0.0 | API de releases de GitHub; README: "The latest stable version is version 5.0.0 (dated May 2025)". El README anuncia 5.0.1 como próximo parche: **no publicado** a 2026-10-02 (el tag `latest` es la rama de desarrollo, no una versión) |
| OWASP Top 10 Proactive Controls | **2024** | Tag `v4.0.0` del repo: 2024-10-20. Fecha de publicación original de la edición: **sin verificar** | https://top10proactive.owasp.org/archive/2024/ | El sitio lista "Top 10 2024" como última edición y "Future Top 10 (WIP)" como borrador en curso |
| OWASP Cheat Sheet Series | Sin versión (documento vivo) | Leído en `master` @ `063e9df7b0` (2026-10-02) | https://cheatsheetseries.owasp.org/ | Fuentes Markdown del repo `OWASP/CheatSheetSeries` |

### 1.1 Top 10:2025 — categorías exactas y cambio frente a 2021

| 2025 | Nombre exacto | Posición 2021 | Qué cambió |
|---|---|---|---|
| A01 | Broken Access Control | A01 | Se mantiene n.º 1. **Absorbe SSRF** (A10:2021, CWE-918). También contiene CSRF (CWE-352), open redirect (CWE-601) y path traversal (CWE-22) |
| A02 | Security Misconfiguration | A05 | Sube de 5 a 2. Incluye XXE (CWE-611), atributos de cookie (CWE-614, CWE-1004) y CORS permisivo (CWE-942) |
| A03 | Software Supply Chain Failures | A06 (*Vulnerable and Outdated Components*) | Ampliada: dependencias, sistemas de build y distribución |
| A04 | Cryptographic Failures | A02 | Baja de 2 a 4 |
| A05 | Injection | A03 | Baja de 3 a 5. Incluye XSS |
| A06 | Insecure Design | A04 | Baja de 4 a 6. Contiene subida de archivos sin restricción (CWE-434), condiciones de carrera (CWE-362), flujo de trabajo (CWE-841) y clickjacking (CWE-1021) |
| A07 | Authentication Failures | A07 (*Identification and Authentication Failures*) | Cambio de nombre |
| A08 | Software or Data Integrity Failures | A08 (*Software **and** Data…*) | Cambio de nombre. Contiene deserialización (CWE-502) y asignación masiva (CWE-915) |
| A09 | Security Logging & Alerting Failures | A09 (*…Monitoring Failures*) | Cambio de nombre: registrar sin alertar tiene "valor mínimo" |
| A10 | Mishandling of Exceptional Conditions | — | **Nueva**: manejo de errores, fallo abierto, errores lógicos (24 CWE) |

Resumen: dos categorías nuevas (A03 ampliada, A10 nueva) y una consolidación (SSRF dentro de A01). Fuente: https://owasp.org/Top10/2025/0x00_2025-Introduction/

### 1.2 ASVS 5.0.0 — capítulos

345 requisitos: 70 de nivel 1, 183 de nivel 2, 92 de nivel 3. Identificador: `V<capítulo>.<sección>.<requisito>`.

| Cap. | Nombre | L1 | L2 | L3 | Cubierto aquí |
|---|---|---|---|---|---|
| V1 | Encoding and Sanitization | 8 | 19 | 3 | Sí (INJ, XSS, DES) |
| V2 | Validation and Business Logic | 4 | 7 | 2 | Sí (VAL, BIZ) |
| V3 | Web Frontend Security | 8 | 11 | 12 | Sí (XSS, CSRF, SES, CFG) |
| V4 | API and Web Service | 2 | 8 | 6 | Parcial (CFG-03, CSRF-04); resto: investigador 2 |
| V5 | File Handling | 4 | 5 | 4 | Sí (FILE) |
| V6 | Authentication | 13 | 22 | 12 | Sí (AUTH) |
| V7 | Session Management | 6 | 12 | 1 | Sí (SES) |
| V8 | Authorization | 4 | 3 | 6 | Sí (AC) |
| V9 | Self-contained Tokens | 4 | 3 | 0 | Una regla (AUTH-11); detalle: investigador 2 |
| V10 | OAuth and OIDC | 5 | 24 | 7 | Una regla (CSRF-03); resto: investigador 2 |
| V11 | Cryptography | 3 | 11 | 10 | Sí (CRY, AUTH-01) |
| V12 | Secure Communication | 3 | 6 | 3 | Parcial (CRY-04, CRY-05); resto: investigador 4 |
| V13 | Configuration | 1 | 12 | 8 | Sí (SECR, CFG, ERR-02) |
| V14 | Data Protection | 2 | 7 | 4 | Parcial (SES-04, CRY-06, CFG-04) |
| V15 | Secure Coding and Architecture | 3 | 10 | 8 | Sí (AC-06, AC-07, DEP, VAL-02, INJ-08) |
| V16 | Security Logging and Error Handling | 0 | 16 | 1 | Sí (LOG, ERR) |
| V17 | WebRTC | 0 | 7 | 5 | No aplica al stack |

### 1.3 Proactive Controls 2024 → áreas del catálogo

| Control | Nombre exacto | Áreas |
|---|---|---|
| C1 | Implement Access Control | AC |
| C2 | Use Cryptography to Protect Data | CRY, SECR, AUTH-01 |
| C3 | Validate all Input & Handle Exceptions | VAL, INJ, ERR |
| C4 | Address Security from the Start | BIZ |
| C5 | Secure By Default Configurations | CFG, SECR-04 |
| C6 | Keep your Components Secure | DEP |
| C7 | Secure Digital Identities | AUTH, SES |
| C8 | Leverage Browser Security Features | XSS-06, SES-03, CFG-04 |
| C9 | Implement Security Logging and Monitoring | LOG |
| C10 | Stop Server Side Request Forgery | SSRF |

Fuente: https://top10proactive.owasp.org/archive/2024/the-top-10/

## 2. Cobertura: Top 10:2025 → reglas

La asignación sigue la lista de CWE de cada categoría de 2025 (comprobada en la página de cada categoría), no la intuición de 2021.

| Categoría | Reglas |
|---|---|
| A01 Broken Access Control | AC-01, AC-02, AC-03, AC-04, AC-05, AC-08, AC-10, CSRF-01, CSRF-02, CSRF-03, CSRF-04, SSRF-01, SSRF-02, SSRF-03, RED-01, INJ-06, CFG-01, CFG-05, SECR-05, BIZ-10, BIZ-11 |
| A02 Security Misconfiguration | CFG-02, CFG-03, CFG-04, ERR-02, AC-09, SES-03, INJ-07, SECR-04 |
| A03 Software Supply Chain Failures | DEP-01, DEP-02, DEP-03 |
| A04 Cryptographic Failures | AUTH-01, AUTH-07, AUTH-10, AUTH-11, SES-05, CRY-01, CRY-02, CRY-03, CRY-04, CRY-06, CRY-07, BIZ-03 |
| A05 Injection | INJ-01, INJ-02, INJ-03, INJ-04, INJ-05, XSS-01, XSS-02, XSS-03, XSS-04, XSS-05, XSS-06, VAL-01 |
| A06 Insecure Design | BIZ-01, BIZ-02, BIZ-04, BIZ-05, BIZ-07, BIZ-08, FILE-01, FILE-02, FILE-03, FILE-04, FILE-05, FILE-06, AC-04, AC-05, VAL-01 |
| A07 Authentication Failures | AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-09, AUTH-12, SES-01, SES-02, SES-04, CRY-05, SECR-01, SECR-02, SECR-03 |
| A08 Software or Data Integrity Failures | DES-01, DES-02, AC-06, BIZ-03, DEP-01, DEP-03 |
| A09 Security Logging & Alerting Failures | LOG-01, LOG-02, LOG-03, LOG-04, LOG-05, LOG-06 |
| A10 Mishandling of Exceptional Conditions | ERR-01, ERR-03, ERR-04, BIZ-06, BIZ-09 |
| Sin CWE propio en el Top 10:2025 (solo ASVS) | INJ-08, VAL-02, AC-07 |

## 3. Cómo leer las reglas

- Total: **100 reglas** en 18 áreas. Severidad: 21 críticas, 56 altas, 23 medias. No hay reglas de severidad baja: lo que habría sido bajo se dejó fuera (ver §22).
- Los patrones de `rg` (ripgrep) son puntos de partida: cada coincidencia es *un sitio que revisar*, no un hallazgo. Están escritos para varios lenguajes a la vez (PHP, Go, Python, JS/TS); el investigador 2 debe afinarlos por stack.
- En los patrones, `\x60` es el acento grave (se escribe así para no romper el Markdown).
- `host` en los comandos `curl` es el dominio desplegado. Los tests marcados "test:" son pruebas dinámicas contra un entorno de staging.
- Nivel ASVS entre paréntesis. Se cita un requisito L3 solo cuando es el texto exacto que respalda la regla; va marcado.
- La URL de ASVS apunta al capítulo en el tag `v5.0.0`; el requisito se localiza por su identificador dentro de la página.

---

## 4. Autenticación (AUTH)

### SEC-AUTH-01 — Las contraseñas siempre se almacenan con Argon2id, scrypt, bcrypt o PBKDF2 con parámetros vigentes; nunca con hash rápido ni cifrado reversible
Mínimos OWASP: Argon2id m=19456, t=2, p=1 (o equivalente); scrypt N=2^17, r=8, p=1; bcrypt coste ≥ 10 y solo en sistemas heredados; PBKDF2-HMAC-SHA256 ≥ 600 000 iteraciones.  
*Si no:* un volcado de la tabla de usuarios se rompe offline a miles de millones de intentos por segundo, y las contraseñas recuperadas se reutilizan contra otros servicios.  
*Verificación:* `rg -n "md5\(|sha1\(|hash\('sha|hashlib\.(md5|sha1|sha256)\(|sha256\.Sum|createHash\("` en el código de usuarios y autenticación; leer la configuración del hasher y sus parámetros de coste.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V11.4.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x20-V11-Cryptography.md · Password Storage Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html · Top 10 A04:2025 https://owasp.org/Top10/2025/A04_2025-Cryptographic_Failures/

### SEC-AUTH-02 — La política de contraseñas nunca impone reglas de composición ni rotación periódica ni trunca la entrada: exige mínimo 8 caracteres, admite al menos 64 y rechaza las comunes o filtradas
Con bcrypt el límite real es 72 bytes: se rechaza por encima, no se trunca en silencio. Sin MFA, OWASP considera débil menos de 15 caracteres.  
*Si no:* se aceptan contraseñas que ya están en diccionarios de ataque (credential stuffing, password spraying); el truncado silencioso reduce la entropía real sin que el usuario lo sepa.  
*Verificación:* leer las reglas de validación de registro y cambio de contraseña; `rg -n "mixedCase|symbols\(\)|password_expires|must_change_password|substr\(\$password"`; test: `password` y una contraseña de una lista de filtradas se rechazan, una frase de 64 caracteres con espacios y Unicode se acepta.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V6.2.1, V6.2.4, V6.2.5, V6.2.8 (L1), V6.2.9, V6.2.10, V6.2.12 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md · Authentication Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

### SEC-AUTH-03 — Las respuestas de login, registro y recuperación nunca revelan si una cuenta existe
Cuenta el mensaje, el código HTTP y el tiempo de respuesta. La ruta rápida "usuario no existe → error inmediato" delata por temporización.  
*Si no:* enumeración de cuentas, que da la lista de objetivos para stuffing y phishing dirigido.  
*Verificación:* test: mismas peticiones con un email existente y uno inexistente devuelven el mismo cuerpo, el mismo status y tiempos comparables; `rg -n -i "user not found|no existe|not registered|already (in use|taken|registered)|ya está registrad"`.  
*Severidad:* media  
*Fuente:* Authentication Cheat Sheet §Authentication and Error Messages https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html · Forgot Password Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html · Top 10 A07:2025 https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/

### SEC-AUTH-04 — El login, la verificación de códigos y la recuperación siempre tienen un límite de intentos asociado a la cuenta, no solo a la IP
El atacante rota IP; el contador va con la cuenta. El bloqueo debe ser progresivo para que no sirva para dejar fuera a usuarios legítimos.  
*Si no:* fuerza bruta, credential stuffing y password spraying sin coste; un código de 6 dígitos cae en minutos.  
*Verificación:* localizar el middleware o limitador en las rutas de login, segundo factor, recuperación y verificación; test: N+1 intentos fallidos sobre la misma cuenta desde IP distintas terminan en 429 o bloqueo temporal.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V6.3.1 (L1), V6.6.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md · Authentication Cheat Sheet §Protect Against Automated Attacks https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

### SEC-AUTH-05 — Nunca se despliegan cuentas ni credenciales por defecto
Incluye usuarios creados por seeders, migraciones o scripts de arranque.  
*Si no:* acceso administrativo inmediato con credenciales públicas o adivinables.  
*Verificación:* `rg -n -i "admin@|password123|'password'|secret123|changeme|admin/admin|12345678" database seeds migrations fixtures scripts`; confirmar que los seeders de demostración no se ejecutan en producción.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V6.3.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md · Top 10 A07:2025 https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/

### SEC-AUTH-06 — El cambio de contraseña siempre exige la contraseña actual, y cambiar email, teléfono o MFA siempre exige reautenticación
*Si no:* una sesión secuestrada (XSS, CSRF, equipo desatendido) se convierte en toma permanente de la cuenta cambiando el email o la contraseña.  
*Verificación:* leer los handlers de cambio de contraseña, email y MFA: validan la contraseña actual o una confirmación reciente; test: la petición sin contraseña actual se rechaza.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V6.2.3 (L1), V7.5.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md · Authentication Cheat Sheet §Require Re-authentication for Sensitive Features https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

### SEC-AUTH-07 — Los tokens de recuperación siempre son aleatorios (CSPRNG), de un solo uso, con caducidad y guardados como hash; la cuenta no se modifica hasta que se presenta uno válido
*Si no:* tokens predecibles o reutilizables dan la toma de cuenta; una fuga de la base de datos con tokens en claro permite restablecer cualquier cuenta; bloquear la cuenta al pedir el reset es una denegación de servicio a voluntad.  
*Verificación:* leer la generación (no `uniqid`, `md5(time())`, `rand`), la columna de expiración, el borrado tras el uso y que la tabla guarda el hash; test: reutilizar un token falla, un token caducado falla.  
*Severidad:* alta  
*Fuente:* Forgot Password Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html · ASVS 5.0.0 V6.4.1 (L1), V6.5.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md

### SEC-AUTH-08 — Los enlaces absolutos enviados por correo nunca se construyen a partir de la cabecera Host de la petición
La URL base sale de configuración o se valida contra una lista de dominios de confianza.  
*Si no:* inyección de cabecera Host: el enlace de recuperación apunta al dominio del atacante y la víctima le entrega el token al hacer clic.  
*Verificación:* `rg -n "getHost\(\)|HTTP_HOST|request\.host|r\.Host|req\.headers\.host|X-Forwarded-Host"`; test: `curl -H 'Host: evil.test'` contra el endpoint de recuperación y leer el enlace del correo generado.  
*Severidad:* alta  
*Fuente:* Forgot Password Cheat Sheet §URL Tokens https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html (la fuente lo exige para el enlace de recuperación; extenderlo a todo enlace por correo es derivación)

### SEC-AUTH-09 — La recuperación de contraseña nunca evita el MFA, y los códigos de un solo uso solo se aceptan una vez y dentro de su ventana de validez
Códigos fuera de banda: vida máxima de 10 minutos. TOTP: 30 segundos.  
*Si no:* la recuperación por correo degrada el MFA a un único factor; un código capturado se reutiliza.  
*Verificación:* test: tras restablecer la contraseña de una cuenta con MFA, el acceso sigue pidiendo el segundo factor; reutilizar el mismo TOTP o código de recuperación se rechaza; un código antiguo se rechaza.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V6.4.3, V6.5.1, V6.5.5 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md

### SEC-AUTH-10 — Los secretos (tokens, firmas, hashes, códigos) siempre se comparan con una función de tiempo constante
*Si no:* ataque de temporización que recupera el valor byte a byte; con comparación laxa, además, confusión de tipos.  
*Verificación:* `rg -n "(token|signature|hmac|digest|secret|api_key|otp|code)\w*\s*(===?|!==?)\s"`; cada comparación usa `hash_equals`, `hmac.compare_digest`, `subtle.ConstantTimeCompare` o `crypto.timingSafeEqual`.  
*Severidad:* media  
*Fuente:* Authentication Cheat Sheet §Compare Password Hashes Using Safe Functions https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html · Session Management Cheat Sheet §Server-Side Session Token Storage https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

### SEC-AUTH-11 — Un token autocontenido (JWT) solo se acepta tras verificar su firma con un algoritmo de una allowlist fija y validar `exp`, `nbf`, `aud` e `iss`
La clave de verificación sale de configuración, nunca de cabeceras del propio token (`jku`, `x5u`, `jwk`). `none` no está en la allowlist.  
*Si no:* falsificación de tokens (algoritmo `none`, confusión RS/HS, clave inyectada) y suplantación de cualquier usuario; tokens emitidos para otro servicio se aceptan aquí.  
*Verificación:* `rg -n "jwt\.decode|jwt\.verify|jwt\.Parse|JWT::decode|verify_signature|algorithms\s*="`; lista de algoritmos fija; ausencia de `verify=False`, `"verify_signature": False` y de `decode()` sin verificación usado para decidir; test: token con `alg: none` y token caducado se rechazan.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V9.1.1, V9.1.2, V9.1.3, V9.2.1 (L1), V9.2.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x18-V9-Self-contained-Tokens.md · Top 10 A07:2025 https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/

### SEC-AUTH-12 — Las cuentas con privilegios administrativos solo se autentican con MFA
*Si no:* una sola contraseña filtrada o reutilizada da control administrativo completo.  
*Verificación:* leer el guard de las rutas de administración: exige segundo factor confirmado; test: un administrador sin MFA configurado no entra al panel.  
*Severidad:* alta  
*Fuente:* Multifactor Authentication Cheat Sheet §Quick Recommendations https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html · ASVS 5.0.0 V6.3.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md · Top 10 A07:2025 https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/

## 5. Gestión de sesión (SES)

### SEC-SES-01 — El identificador de sesión siempre se regenera al autenticar y en todo cambio de nivel de privilegio
*Si no:* fijación de sesión: el atacante planta un identificador conocido y hereda la sesión autenticada de la víctima.  
*Verificación:* `rg -n "regenerate\(|session_regenerate_id|cycle_key|session\.clear\(|RenewToken"` en el handler de login; test: el valor de la cookie de sesión antes y después del login es distinto.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V7.2.4 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md · Session Management Cheat Sheet §Renew the Session ID After Any Privilege Level Change https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

### SEC-SES-02 — El fin de sesión (logout, inactividad, vida máxima, cambio de contraseña, cuenta desactivada) siempre invalida la sesión en el servidor
Borrar la cookie no basta. Los tokens autocontenidos necesitan lista de revocación, fecha mínima por usuario o vida corta. Los tiempos de expiración se aplican en servidor.  
*Si no:* un token robado sigue valiendo tras el logout o tras "recuperar" la cuenta; el atacante conserva el acceso indefinidamente.  
*Verificación:* test: guardar la cookie o token, hacer logout y reutilizarlo → 401; cambiar la contraseña invalida las demás sesiones y tokens; `rg -n "expiration.*null|expires_in.*(None|0)|lifetime"` → ninguna sesión ni token sin caducidad.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V7.4.1, V7.4.2 (L1), V7.3.1, V7.3.2, V7.4.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md · Session Management Cheat Sheet §Session Expiration https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

### SEC-SES-03 — Las cookies de sesión siempre llevan `Secure`, `HttpOnly` y un `SameSite` explícito (`Lax` o `Strict`)
Recomendado el prefijo `__Host-` (sin `Domain`, `Path=/`). `SameSite=None` solo con necesidad documentada.  
*Si no:* robo del identificador por XSS (sin `HttpOnly`) o por red (sin `Secure`); envío de la cookie en peticiones entre sitios (CSRF).  
*Verificación:* `curl -sI https://host/login | rg -i set-cookie` → cada cookie de sesión con los tres atributos; leer la configuración de sesión.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V3.3.1 (L1), V3.3.2, V3.3.3, V3.3.4 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · Session Management Cheat Sheet §Cookies https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

### SEC-SES-04 — Los tokens de sesión y de acceso nunca se guardan en `localStorage` o `sessionStorage` ni viajan en la URL
ASVS V14.3.3 admite el token de sesión en almacenamiento del navegador; la cheat sheet lo prohíbe. Se adopta la más estricta.  
*Si no:* un único XSS exfiltra el token y da acceso fuera del navegador; un token en la URL queda en logs, historial y cabecera Referer.  
*Verificación:* `rg -n "(localStorage|sessionStorage)\.(setItem|getItem)" | rg -i "token|jwt|auth|session"`; `rg -n "[?&](token|access_token|api_key|session_id)="`.  
*Severidad:* alta  
*Fuente:* Session Management Cheat Sheet §HTML5 Web Storage API https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html · ASVS 5.0.0 V14.2.1 (L1), V14.3.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x23-V14-Data-Protection.md

### SEC-SES-05 — Los tokens de sesión siempre los genera el servidor con un CSPRNG y al menos 128 bits de entropía, y la aplicación nunca acepta un identificador que no emitió
Una clave de API estática no es una sesión. Usar el gestor de sesiones del framework cumple la regla.  
*Si no:* predicción o fuerza bruta del identificador; fijación de sesión con un valor elegido por el atacante.  
*Verificación:* confirmar el gestor de sesión del framework; si hay tokens propios, `rg -n "uniqid|mt_rand|\brand\(|Math\.random|math/rand|random\.(random|randint|choice)"` junto a su generación; modo estricto de sesión activado.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V7.2.1, V7.2.2, V7.2.3 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md · Session Management Cheat Sheet §Session ID Generation and Verification https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

## 6. Control de acceso, IDOR y multi-tenant (AC)

### SEC-AC-01 — Toda ruta deniega por defecto: solo es pública si figura en una allowlist explícita, y la autorización siempre se decide en el servidor
Ocultar un botón o una ruta en el cliente no es control de acceso.  
*Si no:* endpoints olvidados accesibles sin sesión (navegación forzada); escalada de privilegios llamando directamente al endpoint que la interfaz oculta.  
*Verificación:* volcar todas las rutas del router y comparar las que no llevan middleware de autenticación/autorización con la lista pública documentada; test: cada endpoint privado sin sesión → 401/403, y con un usuario sin el permiso → 403.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V8.2.1, V8.3.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md · Top 10 A01:2025 https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/ · Authorization Cheat Sheet §Deny by Default https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html · Proactive Controls 2024 C1 https://top10proactive.owasp.org/archive/2024/the-top-10/c1-accesscontrol/

### SEC-AC-02 — Todo acceso a un objeto por su identificador siempre comprueba que el solicitante tiene permiso sobre ese objeto concreto
Un UUID o identificador aleatorio es defensa en profundidad, no autorización. Patrón preferido: buscar dentro del conjunto del usuario (`usuario.proyectos.buscar(id)`), no en toda la tabla.  
*Si no:* IDOR/BOLA: cambiar el identificador en la URL o el cuerpo da lectura, modificación o borrado de datos ajenos.  
*Verificación:* `rg -n "find(OrFail)?\(\$|findById\(|get_object_or_404|\.get\(\w*_?id\)|First\(&\w+, *\w*id|findUnique\(|where\('id'"` y, por cada resultado, localizar la policy, el scope o la comprobación de propiedad; test con dos usuarios sobre lectura, edición, borrado y exportación.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V8.2.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md · IDOR Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html · Top 10 A01:2025 https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/

### SEC-AC-03 — La identidad, el rol y el tenant del actor nunca se leen de parámetros, cuerpo o cabeceras que el cliente controla
Salen siempre de la sesión o del token verificado. Un identificador de tenant enviado por el cliente es un selector que hay que validar contra la pertenencia del usuario.  
*Si no:* suplantación o escalada cambiando un campo (`user_id`, `role`, `tenant_id`) o una cabecera (`X-Tenant-ID`).  
*Verificación:* `rg -n -i "(request|req|input|body|payload|params|headers)\S*(user_id|tenant_id|account_id|owner_id|company_id|role|is_admin|x-tenant|x-user)"`; cada aparición es una acción administrativa validada o se elimina.  
*Severidad:* crítica  
*Fuente:* Business Logic Security Cheat Sheet §Identity and Role https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html · Multi-Tenant Security Cheat Sheet §1 https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html

### SEC-AC-04 — Los datos de un tenant solo se consultan a través de una frontera común que impone el alcance del tenant; nunca filtrando a mano consulta por consulta
Frontera común: scope global del ORM, repositorio con alcance o seguridad a nivel de fila en la base de datos. Las rutas administrativas entre tenants son explícitas, autorizadas aparte y auditadas.  
*Si no:* basta una consulta sin el filtro para leer o modificar datos de otro cliente.  
*Verificación:* identificar el mecanismo común; `rg -n "withoutGlobalScope|DB::table\(|DB::select|\.raw\(|execute\(|text\("` y revisar cada consulta que lo esquiva; test: un usuario del tenant A pide cada tipo de recurso del tenant B → denegado.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V8.4.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md · Multi-Tenant Security Cheat Sheet §2–3 https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html · Top 10 A06:2025 https://owasp.org/Top10/2025/A06_2025-Insecure_Design/

### SEC-AC-05 — Las claves de caché, las rutas de almacenamiento y los trabajos en cola siempre incluyen el tenant, y el consumidor siempre lo revalida
El `tenant_id` dentro de un mensaje de cola no prueba autorización.  
*Si no:* fuga entre clientes por caché compartida, por rutas de archivo colisionadas o por un trabajo que procesa datos con el contexto equivocado.  
*Verificación:* `rg -n "Cache::|cache\.(get|set)|redis\.(Get|Set)|\.remember\("` → la clave lleva el tenant cuando el dato varía por tenant; prefijo de tenant en las rutas de almacenamiento; los handlers de cola recargan y reautorizan el contexto.  
*Severidad:* alta  
*Fuente:* Multi-Tenant Security Cheat Sheet §4–6 y Do's and Don'ts https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html

### SEC-AC-06 — Los endpoints solo asignan campos de una allowlist por acción; nunca vuelcan la petición completa en un modelo
*Si no:* asignación masiva: el atacante añade `is_admin`, `role`, `price`, `user_id` o `email_verified_at` a la petición y se guarda.  
*Verificación:* `rg -n "request->all\(\)|->fill\(\$request|create\(\$request->(all|input)|guarded\s*=\s*\[\]|\*\*(payload|data|body)\b|model_dump\(\)\)|Object\.assign\(\w+,\s*req\.body|\.\.\.req\.body|Bind(JSON)?\(&"`; cada escritura parte de datos validados con una lista cerrada de campos (objeto de entrada/DTO).  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V15.3.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md · Mass Assignment Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html · Top 10 A08:2025 https://owasp.org/Top10/2025/A08_2025-Software_or_Data_Integrity_Failures/

### SEC-AC-07 — Las respuestas solo devuelven los campos que el consumidor necesita y puede ver; nunca el objeto de dominio completo
*Si no:* exposición de hashes de contraseña, tokens, identificadores de proveedores, PII de otros usuarios y campos internos.  
*Verificación:* `rg -n "return \$\w+;|->toArray\(\)|json\(\$\w+\)|res\.json\(\w*(user|row|doc)|c\.JSON\(\S+,\s*\w*(user|model)"`; cada respuesta pasa por un transformador o esquema de salida; test: buscar `password`, `token`, `secret`, `two_factor` en las respuestas JSON.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V15.3.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md, V8.2.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md

### SEC-AC-08 — Los archivos privados solo se sirven tras la misma comprobación de autorización que el resto de recursos
*Si no:* quien conoce o adivina la URL descarga documentos de otros usuarios sin sesión.  
*Verificación:* listar qué se escribe en almacenamiento público (`rg -n -i "public-read|visibility.*public|disk\('public'\)|/public/uploads"`); test: la URL de un archivo privado sin sesión y con la sesión de otro usuario → denegado.  
*Severidad:* alta  
*Fuente:* Authorization Cheat Sheet §Enforce Authorization Checks on Static Resources https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html · File Upload Cheat Sheet §User Permissions https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

### SEC-AC-09 — CORS nunca refleja el `Origin` de la petición sin validarlo contra una allowlist, ni combina comodín con credenciales
*Si no:* cualquier sitio que visite la víctima lee respuestas autenticadas de la aplicación.  
*Verificación:* `curl -sI -H 'Origin: https://evil.test' https://host/api/ruta | rg -i access-control` → no devuelve `evil.test`; `rg -n -i "allowed_origins.*\*|allow_origins=\[\"\*\"\]|origin:\s*true|AllowAllOrigins|supports_credentials"`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V3.4.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · Top 10 A02:2025 (CWE-942) https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/

### SEC-AC-10 — Cada endpoint que recibe un identificador de objeto siempre tiene un test que lo invoca con un objeto ajeno y espera denegación
Es la única forma de que la regla AC-02 siga cumpliéndose cuando el código cambia.  
*Si no:* una refactorización elimina una comprobación de propiedad y nadie lo nota hasta la brecha.  
*Verificación:* cruzar la lista de rutas con parámetro de objeto con los tests que afirman 403/404 (`rg -n -c "assertForbidden|assertNotFound|status_code == 40[34]|StatusForbidden|toBe\(40[34]\)" tests`); toda ruta sin test es hallazgo.  
*Severidad:* media  
*Fuente:* Authorization Cheat Sheet §Create Unit and Integration Test Cases for Authorization Logic https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html · IDOR Prevention Cheat Sheet §Verifying access controls https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html · Top 10 A01:2025 https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/

## 7. Validación de entrada e inyección (VAL, INJ)

### SEC-VAL-01 — Toda entrada se valida siempre en el servidor contra una definición positiva (tipo, formato, longitud, rango o lista de valores); la validación del cliente nunca cuenta como control
La validación no sustituye a la parametrización ni a la codificación de salida: es una capa más.  
*Si no:* datos malformados que llegan a la base de datos y a componentes posteriores; primer eslabón de inyecciones y abusos de lógica.  
*Verificación:* por cada endpoint que escribe existe un esquema de entrada; `rg -n "request->(input|get|all)\(|request\.(json|form)\b|req\.(body|query)\.|c\.(Query|PostForm|Param)\("` en handlers sin validación previa; test con `curl`: tipos erróneos, longitudes extremas y valores fuera de lista se rechazan.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V2.2.1, V2.2.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md · Input Validation Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html · Proactive Controls 2024 C3 https://top10proactive.owasp.org/archive/2024/the-top-10/c3-validate-input-and-handle-exceptions/

### SEC-VAL-02 — Las comparaciones en decisiones de seguridad siempre son estrictas y con tipos explícitos; nunca con igualdad laxa
*Si no:* confusión de tipos (*type juggling*): `"0e123" == "0e456"` o `0 == "texto"` dan verdadero y saltan la comparación de tokens o hashes.  
*Verificación:* linter con igualdad estricta obligatoria (`eqeqeq`, análisis estático en nivel estricto); `rg -n "[^=!<>]==[^=]"` en el código de autenticación y autorización; `rg -n "in_array\([^)]*\)"` sin tercer argumento `true`.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V15.3.5 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md

### SEC-INJ-01 — Las consultas a base de datos siempre usan parámetros enlazados o el ORM; nunca concatenan ni interpolan entrada
Los métodos "raw" del ORM con interpolación son SQL concatenado.  
*Si no:* inyección SQL: lectura y modificación de toda la base de datos, salto del login y, según privilegios, ejecución de comandos.  
*Verificación:* `rg -n "(raw|Raw|unprepared|statement|execute|query|Exec|Query)\((\"|'|f\"|\x60)[^)]*(\$|\{|%s| \+ )"`; `rg -n -i "f\"(select|insert|update|delete)|Sprintf\(\"(select|insert|update|delete)|\x60(select|insert|update|delete)[^\x60]*\$\{"`; semgrep con el conjunto de reglas de inyección SQL.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V1.2.4 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · SQL Injection Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html · Top 10 A05:2025 https://owasp.org/Top10/2025/A05_2025-Injection/

### SEC-INJ-02 — Los nombres de tabla, columna y dirección de orden solo se toman de una allowlist definida en el código; nunca de la entrada
Los identificadores SQL no admiten parámetros enlazados ni se pueden escapar de forma fiable.  
*Si no:* inyección SQL a través de `sort`, `order` o `column`, aunque todo lo demás esté parametrizado.  
*Verificación:* `rg -n -i "order_?by\w*\(\s*(\$request|request|req|params|input)|sort\w*\s*=\s*(\$request|request\.|req\.)|ORDER BY \"\s*\+|order by \{|ORDER BY %s"`; cada valor pasa por un mapa o enumeración cerrada.  
*Severidad:* alta  
*Fuente:* SQL Injection Prevention Cheat Sheet §Defense Option 3 https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html · Top 10 A05:2025 https://owasp.org/Top10/2025/A05_2025-Injection/

### SEC-INJ-03 — Nunca se ejecuta un comando del sistema construido con entrada a través de un shell; solo API nativas o ejecución con lista de argumentos y comando fijo
Aun con los argumentos escapados cabe inyección de argumentos (`--output=…`): se antepone `--` a los operandos y se valida cada argumento contra una allowlist.  
*Si no:* ejecución remota de comandos con los privilegios del proceso.  
*Verificación:* `rg -n "shell_exec|\bexec\(|\bsystem\(|passthru\(|proc_open|popen\(|fromShellCommandline|shell=True|os\.(system|popen)|Command\(\"(sh|bash)\"|child_process|execSync|shell:\s*true"`; cada llamada con datos externos usa lista de argumentos, sin shell.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V1.2.5 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · OS Command Injection Defense Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html

### SEC-INJ-04 — Nunca se evalúa como código ningún dato influido por el usuario
Incluye `eval`, constructores de funciones desde texto, temporizadores con cadena e importación dinámica por nombre recibido.  
*Si no:* ejecución remota de código en servidor, o XSS en el navegador.  
*Verificación:* `rg -n "\beval\(|new Function\(|setTimeout\(\s*['\"\x60]|setInterval\(\s*['\"\x60]|create_function|assert\(\$|\bexec\(|compile\(|__import__\(|import_module\("`.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V1.3.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · Top 10 A05:2025 https://owasp.org/Top10/2025/A05_2025-Injection/

### SEC-INJ-05 — El texto de una plantilla nunca se construye con entrada del usuario; la entrada solo entra como dato
*Si no:* inyección de plantillas en servidor (SSTI): ejecución de código o lectura de configuración y secretos.  
*Verificación:* `rg -n "render_template_string\(|from_string\(|Blade::(render|compileString)\(|Template\(\w|\.Parse\(\w|ejs\.render\(\w|compile\(\w*(req|input|body)"` → el primer argumento es una constante o un archivo del repositorio.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V1.3.7 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md

### SEC-INJ-06 — Las rutas de archivo nunca se construyen con nombres aportados por el usuario; si es inevitable, la ruta canónica siempre se verifica dentro del directorio base
*Si no:* salto de directorio (`../../.env`), inclusión de archivos local o remota, lectura o sobrescritura de archivos arbitrarios.  
*Verificación:* `rg -n "(file_get_contents|fopen|readfile|unlink|include|require|download|sendFile|FileResponse|open|ReadFile|Open|Remove)\(.*(request|req\.|input|params|\$_(GET|POST)|filename|path)"`; cada uso canonicaliza y comprueba el prefijo; test: `..%2f..%2f.env`, ruta absoluta, byte nulo.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V5.3.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md · Top 10 A01:2025 (CWE-22) https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/

### SEC-INJ-07 — Los analizadores XML siempre se configuran con DTD y entidades externas deshabilitadas
Una opción de seguridad no soportada por el analizador es un fallo de configuración, no una advertencia.  
*Si no:* XXE: lectura de archivos locales, SSRF y denegación de servicio por expansión de entidades.  
*Verificación:* `rg -n "LIBXML_NOENT|LIBXML_DTDLOAD|simplexml_load|DOMDocument|XMLReader|lxml|xml\.(sax|dom|etree)|resolve_entities|encoding/xml|xml2js|libxmljs"` y leer la configuración de cada analizador; test: documento con `<!DOCTYPE … SYSTEM "file:///etc/passwd">` se rechaza.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V1.5.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · XML External Entity Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html

### SEC-INJ-08 — La entrada JSON nunca se fusiona de forma recursiva en objetos de la aplicación sin descartar `__proto__`, `constructor` y `prototype`
Solo aplica a JavaScript/TypeScript.  
*Si no:* contaminación de prototipo: salto de comprobaciones de autorización, denegación de servicio o ejecución de código en Node.  
*Verificación:* `rg -n "_\.merge\(|defaultsDeep\(|deepmerge\(|\$\.extend\(\s*true|Object\.assign\(\w+,\s*(req|request)\.|\[\w+\]\[\w+\]\s*="` en código que recibe datos de la petición; auditoría de dependencias sobre las librerías de fusión.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V15.3.6 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md

## 8. XSS y codificación de salida (XSS)

### SEC-XSS-01 — Los datos no confiables solo se emiten en HTML a través del autoescape del framework; toda vía de escape lleva contenido saneado o constante
Vías de escape: salida sin escapar de la plantilla, `v-html`, `dangerouslySetInnerHTML`, filtros `safe`, tipos "HTML de confianza".  
*Si no:* XSS almacenado o reflejado: robo de sesión, acciones en nombre de la víctima, toma de la cuenta de administración.  
*Verificación:* `rg -n "\{!!|v-html|dangerouslySetInnerHTML|\|\s*safe\b|Markup\(|mark_safe|template\.(HTML|JS|URL)\(|autoescape\s*=?\s*(False|false|off)|\{@html"`; cada resultado se justifica (constante o salida de un saneador).  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V1.2.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · XSS Prevention Cheat Sheet §Framework Security https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html · Top 10 A05:2025 https://owasp.org/Top10/2025/A05_2025-Injection/

### SEC-XSS-02 — El HTML o Markdown aportado por usuarios siempre se sanea con una librería de saneamiento reconocida, y nunca se modifica después de saneado
Un saneador casero con expresiones regulares o `strip_tags` no cuenta. El conversor de Markdown no debe dejar pasar HTML crudo ni enlaces inseguros.  
*Si no:* XSS almacenado a través del editor de texto enriquecido, comentarios o descripciones.  
*Verificación:* localizar los campos de texto enriquecido y el saneador en su camino; `rg -n "strip_tags\(|preg_replace\([^)]*script|replace\([^)]*<script"` (saneado casero = hallazgo); test: guardar `<img src=x onerror=alert(1)>` y `[x](javascript:alert(1))`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V1.3.1 (L1), V1.3.5 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · XSS Prevention Cheat Sheet §HTML Sanitization https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html

### SEC-XSS-03 — El JavaScript del cliente nunca escribe datos no confiables en sumideros que interpretan HTML; solo usa `textContent` o equivalentes seguros
Sumideros: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, y los métodos `.html()`/`.append()` de librerías.  
*Si no:* XSS basado en DOM, invisible para el servidor y para un WAF.  
*Verificación:* `rg -n "\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write(ln)?\(|\)\.(html|append|prepend|after|before)\("`; cada uno recibe una constante o la salida de un saneador.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V3.2.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · DOM based XSS Prevention Cheat Sheet (Guideline #4) https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html

### SEC-XSS-04 — Los datos del servidor nunca se interpolan dentro de `<script>`, manejadores de evento en línea ni cadenas JavaScript; solo se pasan como JSON serializado de forma segura o en atributos `data-*`
El escape HTML no protege dentro de un contexto JavaScript.  
*Si no:* XSS rompiendo la cadena o el bloque de script, aunque la plantilla tenga autoescape.  
*Verificación:* `rg -n -U "<script[^>]*>[^<]*(\{\{|<\?=|\$\{)"` sobre plantillas; `rg -n "on(click|load|error|change|submit)=\"[^\"]*(\{\{|<\?=)"`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V1.2.3 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · XSS Prevention Cheat Sheet §Output Encoding for JavaScript Contexts y §Dangerous Contexts https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html

### SEC-XSS-05 — Una URL aportada por el usuario solo se coloca en `href` o `src` si su esquema es `http` o `https`
Los frameworks de componentes no bloquean `javascript:` en enlaces.  
*Si no:* XSS al hacer clic en un enlace `javascript:` o `data:` guardado en un perfil, comentario o campo "sitio web".  
*Verificación:* `rg -n "(href|src|:href|:src|:to)=\"?\{?\{?\s*\$?\w*\.?(url|link|website|href)"` y comprobar la validación de esquema en servidor; test: guardar `javascript:alert(1)` y ver el HTML generado.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V1.2.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · XSS Prevention Cheat Sheet §XSS Prevention Rules Summary https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html

### SEC-XSS-06 — Toda respuesta HTML siempre lleva una Content-Security-Policy con `object-src 'none'`, `base-uri 'none'` y los scripts limitados por nonce, hash o allowlist
Es defensa en profundidad: no sustituye a XSS-01…05.  
*Si no:* cualquier XSS residual se ejecuta sin freno; la inyección de `<base>` secuestra los scripts con ruta relativa.  
*Verificación:* `curl -sI https://host/ | rg -i content-security-policy` y revisar las directivas; ausencia de `'unsafe-eval'` y de `'unsafe-inline'` sin nonce en `script-src`.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V3.4.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · Content Security Policy Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html · Proactive Controls 2024 C8 https://top10proactive.owasp.org/archive/2024/the-top-10/c8-leverage-browser-security-features/

## 9. CSRF y peticiones entre orígenes (CSRF)

### SEC-CSRF-01 — Toda petición que cambia estado y se autentica por cookie siempre verifica un token anti-CSRF o una defensa equivalente; nunca hay rutas exentas sin otra autenticación
Equivalentes admitidos por OWASP: cabeceras Fetch Metadata con respaldo, o cabecera personalizada para APIs (que entonces deben rechazar `text/plain` y formularios). `SameSite` es defensa en profundidad, no sustituto. Una ruta exenta (webhook) se autentica por firma.  
*Si no:* un sitio tercero ejecuta acciones con la sesión de la víctima: cambio de email, compras, altas de administrador.  
*Verificación:* `rg -n -i "except|csrf_exempt|csrf:\s*false|ignoreMethods|WithoutMiddleware|skip_before_action"` junto a la configuración CSRF; test: POST con cookie válida y sin token → rechazado; POST con `Content-Type: text/plain` a un endpoint JSON → rechazado.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V3.5.1, V3.5.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · CSRF Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html · Top 10 A01:2025 (CWE-352) https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/

### SEC-CSRF-02 — Ninguna operación que cambia estado se expone nunca por GET
`SameSite=Lax` envía la cookie en navegaciones GET de primer nivel: no protege este caso.  
*Si no:* CSRF con un simple enlace o `<img src>`; precargadores y rastreadores ejecutan la acción.  
*Verificación:* `rg -n -i "(get|any)\(\s*['\"][^'\"]*(delete|destroy|remove|logout|update|toggle|approve|cancel|pay|confirm)"`; revisar que ningún handler GET escribe en base de datos.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V3.5.3 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · CSRF Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

### SEC-CSRF-03 — El cliente OAuth/OIDC siempre valida `state` o usa PKCE ligado a la sesión que inició el flujo
*Si no:* CSRF de login o inyección de código de autorización: la víctima queda vinculada a la cuenta del atacante, o el atacante entra con la identidad de la víctima.  
*Verificación:* leer el callback: compara `state` con el guardado en sesión o envía `code_verifier`; `rg -n -i "stateless\(\)|state\s*=\s*None|skip_state|verify_state\s*=\s*False"`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V10.1.2, V10.2.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x19-V10-OAuth-and-OIDC.md

### SEC-CSRF-04 — Las conexiones WebSocket solo se aceptan sobre TLS y tras comprobar la cabecera `Origin` contra una allowlist
*Si no:* secuestro de WebSocket entre sitios: una página externa abre el canal con las cookies de la víctima y lee o envía mensajes.  
*Verificación:* `rg -n "CheckOrigin|allowed_?origins|ws://"`; una función de comprobación de origen que devuelve siempre verdadero es hallazgo; test: handshake con `Origin: https://evil.test` → rechazado.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V4.4.1 (L1), V4.4.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x13-V4-API-and-Web-Service.md

## 10. SSRF (SSRF)

### SEC-SSRF-01 — Una petición saliente cuyo destino deriva de entrada del usuario solo se envía tras validar esquema, host y puerto contra una allowlist
Solo `http` y `https`. Incluye funciones que descargan por URL de forma indirecta: importadores, previsualización de enlaces, procesado de imágenes por URL.  
*Si no:* SSRF: acceso a servicios internos sin autenticación (caché, almacenamiento de objetos, base de datos, panel del proxy), a metadatos de la nube, escaneo de la red interna y lectura con `file://`.  
*Verificación:* `rg -n "(Http::\w+|file_get_contents|curl_init|requests\.\w+|httpx\.\w+|http\.(Get|Post)|fetch|axios\.\w+|getimagesize|urlopen)\(\s*\$?\w*(url|uri|link|src|endpoint)"` y rastrear el origen de cada URL hasta la entrada.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V1.3.6 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md, V13.2.4 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md · SSRF Prevention Cheat Sheet (Case 1) https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html · Top 10 A01:2025 (CWE-918) https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/ · Proactive Controls 2024 C10 https://top10proactive.owasp.org/archive/2024/the-top-10/c10-stop-server-side-request-forgery/

### SEC-SSRF-02 — Cuando el destino no puede limitarse por allowlist (webhooks salientes, importadores), la aplicación siempre resuelve el nombre y rechaza la petición si cualquiera de las IP resueltas es privada, de loopback, de enlace local o de metadatos
Se comprueban todos los registros A y AAAA. Mínimo a bloquear: `127.0.0.0/8`, `0.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1`, enlace local IPv6. Conectar a la IP ya validada (para cerrar el DNS rebinding) es derivación: la fuente describe el ataque y manda validar todas las IP.  
*Si no:* salto de la validación por nombre: un dominio público que resuelve a una dirección interna, o notaciones alternativas de IP.  
*Verificación:* leer la función de validación; test con `http://169.254.169.254/`, `http://127.0.0.1:6379/`, `http://[::1]/`, `http://2130706433/`, `http://0/` y un dominio que resuelve a `127.0.0.1` → todos rechazados.  
*Severidad:* alta  
*Fuente:* SSRF Prevention Cheat Sheet (Case 2 y §Deny-list) https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

### SEC-SSRF-03 — El cliente HTTP que procesa una URL del usuario nunca sigue redirecciones automáticamente
*Si no:* una URL que pasa la validación responde con un 302 hacia un destino interno y la validación queda burlada.  
*Verificación:* junto a cada llamada de SSRF-01, `rg -n -i "allow_redirects|follow_redirects|FOLLOWLOCATION|CheckRedirect|maxRedirects|redirect:\s*['\"]|withoutRedirecting"` → redirecciones desactivadas, o cada salto revalidado.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V15.3.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md · SSRF Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

## 11. Subida y descarga de archivos (FILE)

### SEC-FILE-01 — Un archivo subido solo se acepta si su extensión está en una allowlist y su contenido real corresponde a esa extensión; nunca se confía en el `Content-Type` que envía el cliente
La extensión se valida tras decodificar el nombre: dobles extensiones, mayúsculas, byte nulo y extensiones alternativas son los saltos conocidos. Para imágenes, reescribirlas destruye contenido inyectado.  
*Si no:* subida de ejecutables, HTML o scripts disfrazados de imagen o documento.  
*Verificación:* leer las reglas de validación del endpoint de subida; `rg -n "getClientMimeType|getClientOriginalExtension|content_type|\.mimetype\b|file\.type\b"` usados como decisión son hallazgo; test: subir `shell.php` renombrado a `.jpg`, `.pHp` y `.jpg.php`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V5.2.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md · File Upload Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html · Top 10 A06:2025 (CWE-434) https://owasp.org/Top10/2025/A06_2025-Insecure_Design/

### SEC-FILE-02 — Toda subida siempre tiene un límite de tamaño aplicado en servidor, y todo archivo comprimido se comprueba (tamaño descomprimido, número de entradas, rutas sin `..`) antes de extraerse
*Si no:* agotamiento de disco o memoria, bomba de descompresión, *zip slip* que sobrescribe archivos de la aplicación.  
*Verificación:* límite en la validación y en el servidor web; `rg -n "ZipArchive|extractTo|zipfile|tarfile|extractall|archive/(zip|tar)|unzipper|adm-zip"` y leer las comprobaciones previas a la extracción.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V5.2.1 (L1), V5.2.3 (L2), V5.3.3 (L3, *zip slip*) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md · File Upload Cheat Sheet §Upload and Download Limits https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

### SEC-FILE-03 — El nombre con que se almacena un archivo siempre lo genera el servidor; el nombre original del usuario nunca forma parte de la ruta
El nombre original se guarda, saneado, solo como metadato.  
*Si no:* salto de directorio, sobrescritura de archivos de otros usuarios o del sistema, XSS a través del nombre.  
*Verificación:* `rg -n "getClientOriginalName|originalname|\.filename\b|file\.name\b|header\.Filename"` → nunca aparece en la construcción de la ruta de destino.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V5.3.2 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md · File Upload Cheat Sheet §Filename Safety https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

### SEC-FILE-04 — Los archivos subidos nunca se almacenan donde el servidor web o el intérprete pueda ejecutarlos
Orden de preferencia de OWASP: otro host, fuera del webroot, dentro del webroot solo con escritura.  
*Si no:* webshell: ejecución remota de código subiendo un script y pidiéndolo por URL.  
*Verificación:* el destino de subida está fuera del webroot o en almacenamiento de objetos; el servidor no pasa al intérprete nada del directorio de subidas; test: subir `.php`, `.phtml` y `.html` y pedirlos por URL → no se ejecutan ni se interpretan.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V5.3.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md · File Upload Cheat Sheet §File Storage Location https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

### SEC-FILE-05 — El contenido subido por usuarios siempre se sirve como adjunto y con `nosniff`, o desde un origen separado; nunca en línea como HTML o SVG en el origen de la aplicación
Un SVG es un documento con scripts: se sanea o se sirve como descarga.  
*Si no:* XSS almacenado: el archivo se ejecuta con el origen y las cookies de la aplicación.  
*Verificación:* `curl -sI` sobre un archivo subido → `Content-Disposition: attachment` y `X-Content-Type-Options: nosniff`, o dominio distinto; si `svg` o `html` están en la allowlist de subida, comprobar su saneado.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V3.2.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md, V1.3.4 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md

### SEC-FILE-06 — El nombre de archivo de la cabecera `Content-Disposition` siempre lo fija o sanea el servidor; nunca se copia tal cual de la entrada
*Si no:* inyección de cabeceras y descarga de archivo reflejada (el navegador guarda un ejecutable con nombre elegido por el atacante).  
*Verificación:* `rg -n -i "content-disposition"` y los helpers de descarga; test con un nombre que contenga comillas, `;` y saltos de línea.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V5.4.1, V5.4.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md

## 12. Criptografía (CRY)

### SEC-CRY-01 — Nunca se usan MD5, SHA-1, modo ECB, relleno PKCS#1 v1.5 ni cifrado sin autenticar para proteger datos; el cifrado siempre es autenticado y viene de una librería validada
Preferencia: AES-GCM. Sin algoritmos propios.  
*Si no:* colisiones y firmas falsificadas, descifrado por oráculo de relleno, modificación del texto cifrado sin que se detecte.  
*Verificación:* `rg -n -i "\bmd5|\bsha1|\bdes\b|3des|rc4|ecb|aes-\d+-cbc|AES/CBC|NewCBC|MODE_(ECB|CBC)|createCipher\("`; cada uso no criptográfico (etag, clave de caché) se justifica.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V11.3.1, V11.3.2, V11.4.1 (L1), V11.2.1, V11.3.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x20-V11-Cryptography.md · Cryptographic Storage Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html · Top 10 A04:2025 https://owasp.org/Top10/2025/A04_2025-Cryptographic_Failures/

### SEC-CRY-02 — Todo valor aleatorio con función de seguridad siempre sale de un CSPRNG; nunca de un generador pseudoaleatorio común
Aplica a tokens, códigos, contraseñas temporales, claves, sales, nonces e identificadores no adivinables. Un UUID no garantiza aleatoriedad criptográfica.  
*Si no:* tokens de recuperación, códigos de un solo uso e invitaciones predecibles.  
*Verificación:* `rg -n "\b(rand|mt_rand|uniqid|lcg_value|array_rand)\(|Math\.random\(|\"math/rand\"|\brandom\.(random|randint|choice|choices|sample)\("` cerca de `token|code|otp|password|key|secret|nonce|salt`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V11.5.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x20-V11-Cryptography.md · Cryptographic Storage Cheat Sheet §Secure Random Number Generation https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

### SEC-CRY-03 — Un IV o nonce nunca es constante ni se reutiliza con la misma clave
*Si no:* en GCM, repetir el nonce expone la clave de autenticación y la relación entre los textos; en CBC, un IV fijo revela prefijos idénticos.  
*Verificación:* `rg -n -i "(iv|nonce)\s*[:=]\s*(['\"]|b['\"]|\[\]byte\(\"|str_repeat|bytes\(\d+\)|Buffer\.alloc\()"`; el IV se genera en cada operación y se guarda junto al texto cifrado.  
*Severidad:* alta  
*Fuente:* Top 10 A04:2025 §How to prevent https://owasp.org/Top10/2025/A04_2025-Cryptographic_Failures/ · ASVS 5.0.0 V11.3.4 (L3) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x20-V11-Cryptography.md

### SEC-CRY-04 — Todo el tráfico entre cliente y aplicación solo viaja por TLS, y las respuestas siempre incluyen `Strict-Transport-Security` con `max-age` de al menos un año
Efecto observable desde la aplicación; la configuración del proxy es del investigador 4.  
*Si no:* robo de sesión y credenciales por intermediario; degradación a HTTP.  
*Verificación:* `curl -sI http://host/` → redirección a HTTPS sin contenido; `curl -sI https://host/ | rg -i strict-transport` → `max-age=31536000` o más (con `includeSubDomains` en L2); `rg -n "http://" ` en URL de API y de configuración del cliente.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V12.2.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x21-V12-Secure-Communication.md, V3.4.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md

### SEC-CRY-05 — Los clientes TLS salientes nunca desactivan la verificación de certificados
*Si no:* intermediario sobre las llamadas a proveedores de pago, almacenamiento o API internas: robo de claves y manipulación de respuestas.  
*Verificación:* `rg -n "verify\s*=\s*False|'verify'\s*=>\s*false|withoutVerifying\(|SSL_VERIFY(PEER|HOST)\s*,\s*(false|0)|InsecureSkipVerify:\s*true|rejectUnauthorized:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|badCertificateCallback"`.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V12.3.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x21-V12-Secure-Communication.md · Top 10 A07:2025 (CWE-295) https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/

### SEC-CRY-06 — Los datos sensibles (tokens, claves de API, contraseñas, datos personales) nunca viajan en la URL ni en la cadena de consulta
*Si no:* fuga por logs del servidor y del proxy, historial del navegador, cabecera Referer y herramientas de analítica.  
*Verificación:* `rg -n -i "[?&](api_?key|token|access_token|password|secret|auth)="`; rutas con secretos en el path salvo enlaces de un solo uso; revisar una muestra de los logs de acceso.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V14.2.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x23-V14-Data-Protection.md

### SEC-CRY-07 — No se almacena ningún dato sensible que la aplicación no necesite; los datos de tarjeta solo se manejan mediante la tokenización del proveedor de pagos
"Los datos que no se guardan no se pueden robar."  
*Si no:* una brecha expone datos que no hacía falta tener, con todas las obligaciones legales y de PCI DSS que conlleva.  
*Verificación:* `rg -n -i "card_?number|\bcvv\b|\bcvc\b|\bpan\b|exp_(month|year)"` en migraciones, modelos, validadores y logs; listar las columnas con datos personales sin uso funcional.  
*Severidad:* alta  
*Fuente:* Top 10 A04:2025 §How to prevent https://owasp.org/Top10/2025/A04_2025-Cryptographic_Failures/ · Cryptographic Storage Cheat Sheet §Minimize the Storage of Sensitive Information https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

## 13. Secretos (SECR)

### SEC-SECR-01 — Los secretos nunca están en el código fuente, el historial del repositorio, las imágenes ni los artefactos de build
Incluye instrucciones `ENV` y `ARG` de un Dockerfile: quedan en las capas de la imagen.  
*Si no:* cualquiera con acceso al repositorio o a la imagen (colaboradores, CI, una fuga, un agente con acceso de lectura) obtiene credenciales de producción.  
*Verificación:* `gitleaks detect --source . --log-opts=--all`; `rg -n "sk_live_|sk_test_|rk_live_|whsec_|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|xox[baprs]-|ghp_[A-Za-z0-9]{36}"`; `git ls-files | rg "(^|/)\.env($|\.)"` → solo el archivo de ejemplo; `rg -n -i "^(ENV|ARG) .*(KEY|SECRET|PASSWORD|TOKEN)=" Dockerfile*`.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V13.3.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md · Secrets Management Cheat Sheet §5.1 https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html · Cryptographic Storage Cheat Sheet §Key Storage https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html · Top 10 A02:2025 https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/

### SEC-SECR-02 — Ningún secreto de backend se incluye nunca en código que se entrega al cliente (bundle web, aplicación móvil, HTML)
Todo lo que llega al navegador o al binario de la app es público. Las variables con prefijo "público" del bundler se incrustan en el JavaScript.  
*Si no:* extracción trivial de la clave secreta del proveedor de pagos, de notificaciones o de almacenamiento desde el navegador o el paquete de la app.  
*Verificación:* `rg -n "(VITE_|NUXT_PUBLIC_|NEXT_PUBLIC_|REACT_APP_|EXPO_PUBLIC_)\w*(SECRET|PRIVATE|PASSWORD|ADMIN|SERVICE)"`; `rg -n "sk_live_|sk_test_|service_role|-----BEGIN"` sobre el directorio de salida del build; `strings` sobre el binario o paquete móvil.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V13.3.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md (la aplicación al bundle del cliente es lectura directa de "build artifacts") · Top 10 A07:2025 (CWE-798) https://owasp.org/Top10/2025/A07_2025-Authentication_Failures/

### SEC-SECR-03 — Un secreto expuesto siempre se revoca y se rota; borrarlo del código o del historial nunca basta
Orden de OWASP: revocación, rotación, eliminación, registro.  
*Si no:* la clave sigue siendo válida en clones, cachés, forks y copias de seguridad.  
*Verificación:* solo revisión manual: por cada hallazgo de SECR-01, evidencia de que la clave se regeneró en el proveedor después de la exposición.  
*Severidad:* alta  
*Fuente:* Secrets Management Cheat Sheet §9.2 Remediation https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

### SEC-SECR-04 — Cada entorno siempre usa credenciales propias, y ningún servicio conserva credenciales por defecto
*Si no:* acceso con credenciales públicas de fábrica; un entorno de pruebas comprometido da acceso a producción.  
*Verificación:* `rg -n -i "minioadmin|root:root|admin:admin|password:\s*(root|secret|password|changeme|example)|_PASSWORD=(root|secret|password|postgres)$|SECRET_KEY\s*=\s*['\"](changeme|secret|dev)"` sobre archivos de composición, ejemplos de entorno y configuración; comparar que las claves de staging y producción difieren.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V13.2.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md · Top 10 A02:2025 §How to prevent https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/

### SEC-SECR-05 — La aplicación solo se conecta a la base de datos y a servicios externos con cuentas de mínimo privilegio; nunca con root, administrador ni claves de alcance total
Una cuenta de base de datos por aplicación, sin acceso a otras bases.  
*Si no:* una inyección SQL o una ejecución de código escala a todo el servidor de base de datos o a toda la cuenta del proveedor.  
*Verificación:* `rg -n -i "DB_USER(NAME)?=root|user:\s*root|://(root|postgres):"`; `SHOW GRANTS FOR CURRENT_USER;` → sin privilegios globales; las claves de proveedores son restringidas al uso de la aplicación.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V13.2.2, V13.3.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md · SQL Injection Prevention Cheat Sheet §Least Privilege https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html

## 14. Manejo de errores y fuga de información (ERR)

### SEC-ERR-01 — Las respuestas de error nunca incluyen trazas, consultas, rutas del sistema, versiones ni secretos; un manejador global siempre devuelve un mensaje genérico y registra el detalle en servidor
*Si no:* reconocimiento gratuito (stack, versiones, estructura de la base de datos), localización de puntos de inyección y fuga de secretos de entorno.  
*Verificación:* provocar errores (JSON malformado, tipo erróneo, identificador inexistente, 500 forzado) y buscar en la respuesta `Stack trace|SQLSTATE|Traceback|goroutine|/var/www|\.(php|py|go|js):\d+`; confirmar el manejador global; `rg -n "getMessage\(\)|str\(e\)|err\.Error\(\)|error\.(message|stack)"` devueltos al cliente.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V16.5.1 (L2), V16.5.4 (L3) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md · Error Handling Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html · Top 10 A10:2025 https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/

### SEC-ERR-02 — El modo de depuración siempre está desactivado en producción
*Si no:* las páginas de depuración muestran entorno, secretos y código; en algunos frameworks permiten ejecutar código.  
*Verificación:* `rg -n -i "APP_DEBUG=true|DEBUG\s*=\s*True|debug=True|--reload|DebugMode|NODE_ENV=development|devtools:\s*true|sourcemap:\s*true"` en la configuración de producción y en los archivos de composición; provocar un 500 en producción y ver la respuesta.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V13.4.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md · Top 10 A02:2025 https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/

### SEC-ERR-03 — Una excepción o error dentro de un control de seguridad siempre termina en denegación; nunca se captura y se continúa
Controles: autorización, verificación de firma, validación de pago, validación de entrada.  
*Si no:* fallo abierto: un error provocado (tiempo de espera, entrada inválida, servicio caído) salta la verificación y la operación se procesa.  
*Verificación:* `rg -n -U "catch\s*\([^)]*\)\s*\{\s*\}|except[^:\n]*:\s*\n\s*(pass|continue)\b|catch\s*\{\s*\}|_\s*=\s*err\b|if err != nil \{\s*\}"`; revisar a mano cada bloque de captura en los controles citados; test: forzar el fallo de la dependencia y comprobar que la operación se deniega.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V16.5.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md · Top 10 A10:2025 https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/ · Authorization Cheat Sheet §Exit Safely when Authorization Checks Fail https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

### SEC-ERR-04 — Toda llamada a un servicio externo siempre tiene tiempo de espera, y su fallo nunca deja la operación en un estado intermedio
Varios clientes HTTP estándar no tienen tiempo de espera por defecto.  
*Si no:* agotamiento de procesos por una dependencia lenta (denegación de servicio); estados a medias explotables (cobrado sin pedido, pedido sin cobro).  
*Verificación:* `rg -n "Http::|Guzzle|requests\.|httpx\.|http\.Client\{|http\.(Get|Post)\(|\bfetch\(|axios"` y comprobar el tiempo de espera explícito y el tratamiento del error en cada llamada.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V16.5.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md · Top 10 A10:2025 https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/

## 15. Logging y auditoría (LOG)

### SEC-LOG-01 — Siempre se registran los intentos de autenticación (éxito y fallo) y los fallos de autorización, con usuario, origen, acción y momento en UTC
*Si no:* fuerza bruta, credential stuffing y sondeo de identificadores ajenos pasan inadvertidos; sin evidencia para reconstruir un incidente.  
*Verificación:* provocar un login fallido y un 403 y comprobar la entrada con quién, desde dónde, qué y cuándo; `rg -n "Log::|logger\.|slog\.|log\.(Print|Info|Warn)"` en los handlers de autenticación y en el manejador de accesos denegados.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V16.2.1, V16.2.2, V16.3.1, V16.3.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md · Logging Cheat Sheet §Which events to log https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html · Top 10 A09:2025 https://owasp.org/Top10/2025/A09_2025-Security_Logging_and_Alerting_Failures/ · Proactive Controls 2024 C9 https://top10proactive.owasp.org/archive/2024/the-top-10/c9-security-logging-and-monitoring/

### SEC-LOG-02 — Los logs, trazas e informes de errores nunca contienen contraseñas, tokens de sesión o de acceso, claves, datos de tarjeta ni datos personales sensibles
Incluye lo que se envía al servicio externo de errores.  
*Si no:* quien lee los logs o el panel de errores obtiene credenciales; una lectura de archivos de log se convierte en toma de cuentas.  
*Verificación:* `rg -n -i "(log|logger|console|print|dump|dd)\S*\(.*(request->all\(\)|req\.body|request\.(json|body|form)|password|token|secret|authorization|card)"`; lista de campos enmascarados del informador de errores; `rg -i "password|bearer |sk_live"` sobre una muestra de logs reales.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V16.2.5 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md · Logging Cheat Sheet §Data to exclude https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html · Secrets Management Cheat Sheet §8.3 https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

### SEC-LOG-03 — Los datos del usuario siempre se codifican o se pasan como campos estructurados al registrarlos; nunca se concatenan en la línea de log
*Si no:* inyección en logs: entradas falsas mediante saltos de línea, y ataque al visor o al analizador de logs.  
*Verificación:* formato estructurado con contexto separado del mensaje; `rg -n "(Log::\w+|logger\.\w+|log\.\w+)\((f?\"|\x60)[^)]*(\$|\{)"`; test: enviar `%0d%0a` en el nombre de usuario y leer el log.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V16.4.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md · Top 10 A09:2025 https://owasp.org/Top10/2025/A09_2025-Security_Logging_and_Alerting_Failures/

### SEC-LOG-04 — Los archivos de log nunca son accesibles por HTTP, y siempre se envían a un sistema separado de la aplicación
*Si no:* lectura pública de logs con datos personales y tokens; un atacante que compromete la aplicación borra sus huellas.  
*Verificación:* `for p in storage/logs/laravel.log logs/ debug.log error_log app.log; do curl -s -o /dev/null -w "%{http_code} $p\n" https://host/$p; done` → 404 o 403; existencia de un destino externo de logs.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V16.4.2, V16.4.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md

### SEC-LOG-05 — Toda operación que mueve dinero, cambia permisos o concede valor siempre deja un registro de auditoría de solo-añadir con actor, objeto, acción y resultado
*Si no:* fraude y abuso imposibles de detectar y de reconstruir; el actor puede negar la acción.  
*Verificación:* tabla o flujo de auditoría sin rutas de actualización ni borrado; cada handler de pago, reembolso, cambio de rol y emisión de saldo escribe en ella dentro de la misma transacción.  
*Severidad:* media  
*Fuente:* Top 10 A09:2025 §How to prevent https://owasp.org/Top10/2025/A09_2025-Security_Logging_and_Alerting_Failures/ · Business Logic Security Cheat Sheet §What to Log https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html

### SEC-LOG-06 — Los eventos de seguridad repetidos siempre generan una alerta; no solo una línea de log
Eventos: fallos de login en serie, accesos denegados en serie, firmas de webhook inválidas, errores 5xx en ráfaga.  
*Si no:* el ataque queda registrado y nadie se entera hasta que el daño es visible.  
*Verificación:* solo revisión manual de las reglas de alerta configuradas; test: provocar N fallos y confirmar que llega la notificación.  
*Severidad:* media  
*Fuente:* Top 10 A09:2025 https://owasp.org/Top10/2025/A09_2025-Security_Logging_and_Alerting_Failures/ · ASVS 5.0.0 V16.4.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x25-V16-Security-Logging-and-Error-Handling.md

## 16. Deserialización e integridad de datos (DES)

### SEC-DES-01 — Nunca se deserializan datos no confiables con formatos nativos que instancian objetos; solo con formatos de datos puros como JSON
Formatos nativos: `unserialize`, `pickle`, `yaml.load` sin cargador seguro, `Marshal`.  
*Si no:* inyección de objetos: ejecución remota de código mediante cadenas de *gadgets*, o denegación de servicio.  
*Verificación:* `rg -n "\bunserialize\(|pickle\.loads?\(|cPickle|yaml\.load\(|unsafe_load|jsonpickle|marshal\.loads|node-serialize"`; cada uso procesa datos propios y firmados, o usa el modo seguro del lenguaje.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V1.5.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x10-V1-Encoding-and-Sanitization.md · Deserialization Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html · Top 10 A08:2025 (CWE-502) https://owasp.org/Top10/2025/A08_2025-Software_or_Data_Integrity_Failures/

### SEC-DES-02 — Todo estado que sale al cliente y vuelve (cookies propias, campos ocultos, tokens caseros, parámetros de retorno) siempre lleva firma o MAC, que se verifica antes de usarlo
*Si no:* manipulación del precio, identificador o rol que viaja en ese estado; reenvío de un estado antiguo.  
*Verificación:* `rg -n "base64_decode\(\$(request|_COOKIE|_GET|_POST)|json\.loads\(base64|b64decode\(request|atob\("`; cookies excluidas del cifrado del framework; los enlaces firmados se verifican en el handler.  
*Severidad:* alta  
*Fuente:* Top 10 A08:2025 §How to prevent (CWE-565) https://owasp.org/Top10/2025/A08_2025-Software_or_Data_Integrity_Failures/ · Deserialization Cheat Sheet §Only Deserialize Signed Data https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html

## 17. Redirecciones (RED)

### SEC-RED-01 — Una redirección nunca usa una URL aportada por el usuario sin validarla contra una allowlist de destinos o restringirla a rutas relativas del propio origen
Mejor: el usuario envía un identificador corto que el servidor traduce a la URL.  
*Si no:* phishing con el dominio legítimo como trampolín; robo de códigos o tokens que viajan en la URL de retorno.  
*Verificación:* `rg -n "redirect\w*\(\s*(\$request|request\.|req\.)|redirect\(\)->(to|away)\(\$|http\.Redirect\([^)]*(Query|FormValue)|res\.redirect\(req\.|navigateTo\([^)]*query|location(\.href)?\s*=\s*[^;]*(query|params|search)"`; parámetros `next`, `return`, `return_to`, `redirect`, `url`, `continue`; test: `?next=https://evil.test`, `?next=//evil.test`, `?next=/\evil.test`.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V3.7.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · Unvalidated Redirects and Forwards Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html · Top 10 A01:2025 (CWE-601) https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/

## 18. Lógica de negocio (BIZ)

### SEC-BIZ-01 — Precios, totales, descuentos, impuestos y costes de envío siempre se recalculan en el servidor a partir de identificadores y cantidades; nunca se aceptan del cliente
El cliente envía identificador de producto, cantidad y código de cupón. Nada más.  
*Si no:* compra a precio arbitrario (un céntimo, cero, negativo) y descuentos inventados.  
*Verificación:* `rg -n -i "(request|req|input|body|payload|validated)\S*(price|amount|total|subtotal|discount|tax|shipping)"` y seguir cada valor hasta la creación del cobro: debe salir de la base de datos; test: alterar el importe en la petición.  
*Severidad:* crítica  
*Fuente:* Business Logic Security Cheat Sheet §Prices and Totals https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html · Top 10 A06:2025 https://owasp.org/Top10/2025/A06_2025-Insecure_Design/

### SEC-BIZ-02 — Un pedido solo pasa a pagado tras la confirmación servidor-a-servidor del proveedor de pagos; nunca por la redirección de éxito ni por un parámetro del cliente
*Si no:* obtener el producto o servicio sin pagar abriendo directamente la URL de "pago completado".  
*Verificación:* leer el handler de la URL de retorno: no cambia el estado, o consulta al proveedor el estado real con el identificador guardado en servidor; test: abrir la URL de éxito sin haber pagado.  
*Severidad:* crítica  
*Fuente:* Business Logic Security Cheat Sheet §Common Examples — Workflow https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html · Transaction Authorization Cheat Sheet §2.8 https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html · ASVS 5.0.0 V2.3.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md

### SEC-BIZ-03 — Todo webhook entrante siempre verifica la firma del emisor antes de procesar, y procesa cada evento una sola vez
La firma se calcula sobre el cuerpo crudo y se compara en tiempo constante. Las fuentes no nombran "webhook": es aplicación directa de sus principios de integridad e idempotencia.  
*Si no:* cualquiera marca pedidos como pagados o concede saldo con un POST falsificado; los reintentos del proveedor duplican abonos.  
*Verificación:* leer el handler: verificación con el secreto del proveedor antes de cualquier efecto; registro de eventos procesados con restricción de unicidad sobre el identificador del evento; test: POST sin firma o con firma inválida → 400; reenviar el mismo evento → sin efecto.  
*Severidad:* crítica  
*Fuente:* Top 10 A08:2025 §How to prevent https://owasp.org/Top10/2025/A08_2025-Software_or_Data_Integrity_Failures/ · Top 10 A04:2025 (CWE-347) https://owasp.org/Top10/2025/A04_2025-Cryptographic_Failures/ · Business Logic Security Cheat Sheet §Use Idempotency Keys for External Actions https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html

### SEC-BIZ-04 — Toda llamada externa no idempotente (cobro, reembolso, transferencia, emisión de vale) siempre lleva una clave de idempotencia
Los endpoints propios que disparan esas acciones aceptan y almacenan también una clave.  
*Si no:* doble cobro o doble reembolso por reintento, tiempo de espera agotado o doble clic.  
*Verificación:* `rg -n -i "(PaymentIntent|Charge|Refund|Transfer|Payout)\S*create|paymentIntents\.create|refunds\.create"` → cada llamada con clave de idempotencia derivada de la operación, no aleatoria por intento.  
*Severidad:* alta  
*Fuente:* Business Logic Security Cheat Sheet §Use Idempotency Keys for External Actions https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html

### SEC-BIZ-05 — Toda operación de comprobar-y-actuar sobre saldo, existencias, cupones, cupos o límites siempre es atómica; nunca se lee, se decide en la aplicación y se escribe
Formas válidas: bloqueo de fila dentro de transacción, actualización condicional comprobando filas afectadas, o restricción de unicidad en base de datos. "La ventana es de microsegundos" no es defensa.  
*Si no:* condición de carrera: doble gasto, saldo negativo, cupón de un uso canjeado N veces, sobreventa.  
*Verificación:* `rg -n -i "balance|stock|quantity|credits|uses|redeemed|remaining|seats"` y localizar cada lectura seguida de escritura: usa `FOR UPDATE`, `UPDATE … WHERE valor >= x` o índice único; test de concurrencia: 20 peticiones simultáneas y comprobar la invariante.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V2.3.4 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md, V15.4.2 (L3) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md · Business Logic Security Cheat Sheet §Prevent Race Conditions on Sensitive Operations https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html · Top 10 A06:2025 (CWE-362) https://owasp.org/Top10/2025/A06_2025-Insecure_Design/

### SEC-BIZ-06 — Toda operación de negocio de varias escrituras siempre se ejecuta en una transacción que se revierte entera ante cualquier error
*Si no:* estados inconsistentes explotables: saldo descontado sin pedido, pedido creado sin cobro, permisos a medias.  
*Verificación:* los handlers con dos o más escrituras relacionadas están envueltos en una transacción; las llamadas externas quedan fuera de ella o tienen compensación; test: forzar el fallo de la segunda escritura y comprobar que la primera no persiste.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V2.3.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md · Top 10 A10:2025 https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/

### SEC-BIZ-07 — Los flujos de varios pasos siempre guardan su estado en el servidor, y cada paso solo se ejecuta si el estado actual lo permite
Un campo oculto, una cookie legible o el orden de las pantallas no son control. Un paso completado no se puede repetir.  
*Si no:* saltarse la verificación de email, el pago o la aprobación llamando directamente al último paso; repetir pasos que conceden valor.  
*Verificación:* por cada flujo (alta y verificación, compra, aprobación, recuperación) existe una columna de estado y su comprobación al inicio del handler; `rg -n -i "name=\"step\"|current_step|hidden[^>]*step"`; test: llamar al paso final directamente y repetir un paso completado.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V2.3.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md · Business Logic Security Cheat Sheet §Enforce Workflows as Explicit State Machines https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html · Transaction Authorization Cheat Sheet §2.5 https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html

### SEC-BIZ-08 — Cantidades, importes, fechas y combinaciones de campos siempre se validan contra su rango de negocio; nunca solo por formato
Positivo, máximo, existencias disponibles, coherencia entre campos (fin posterior a inicio, moneda fija durante la transacción).  
*Si no:* cantidad negativa que resta del total, importes desbordados, cambio de moneda a mitad de transacción, reservas imposibles.  
*Verificación:* reglas con mínimo, máximo y relaciones entre campos en el esquema de entrada; test: cantidad `-1`, `0`, `999999999`, decimales en campos enteros, fecha de fin anterior a la de inicio.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V2.2.3, V2.3.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md · Business Logic Security Cheat Sheet §Validate Inputs for Business Meaning, Not Just Format https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html

### SEC-BIZ-09 — Ningún recurso es ilimitado: toda función que envía mensajes, concede valor o consume recursos costosos siempre tiene su propio límite de uso, y todo listado tiene paginación con tope
Un límite global en el borde no basta: registro, recuperación, reenvío de verificación, invitaciones, canje de promociones y exportaciones necesitan el suyo.  
*Si no:* bombardeo de correo o SMS a terceros con coste propio, extracción masiva de datos, denegación de servicio, facturas de proveedor disparadas.  
*Verificación:* límite específico en cada una de esas rutas; `rg -n "per_page|page_size|limit"` → tope máximo impuesto en servidor; `rg -n "->get\(\)|\.all\(\)|findMany\(\)|\.Find\(&"` sin límite en endpoints accesibles.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V2.4.1 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md, V15.2.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md · Top 10 A10:2025 https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/ · Business Logic Security Cheat Sheet §Protect Abuse-friendly Features https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html

### SEC-BIZ-10 — La autorización de una acción siempre considera el estado del objeto y la relación del actor con él; nunca solo el rol
Ejemplos: no aprobar la propia solicitud, no cancelar tras el envío, no reembolsar dos veces.  
*Si no:* autoaprobación, cancelaciones y reembolsos fuera de plazo, modificación de recursos ya cerrados.  
*Verificación:* solo revisión manual guiada: por cada acción sensible, enumerar sus reglas de contexto y localizar la comprobación y el test que intenta violarla.  
*Severidad:* alta  
*Fuente:* Business Logic Security Cheat Sheet §Contextual Authorization https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html

### SEC-BIZ-11 — Todo punto de entrada a una operación sensible (web, API, móvil, comando, trabajo en cola, webhook, componente reactivo) siempre aplica las mismas reglas de autorización y de negocio
Las reglas viven en la capa compartida, no en el controlador de una de las entradas.  
*Si no:* salto por el camino menos protegido: una versión antigua de la API, el endpoint de la app móvil o una acción pública de un componente.  
*Verificación:* por cada operación sensible, listar sus llamadores y comparar los controles de cada uno; comparar el middleware de las rutas web, las de API y las versiones anteriores.  
*Severidad:* alta  
*Fuente:* Business Logic Security Cheat Sheet §Avoid "Implicit" Permissions https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html · ASVS 5.0.0 V6.3.4 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md · Authorization Cheat Sheet §Validate the Permissions on Every Request https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

## 19. Configuración insegura (CFG)

### SEC-CFG-01 — El despliegue nunca expone metadatos de control de versiones, archivos de entorno, copias de seguridad ni listados de directorio
*Si no:* descarga del código fuente completo y de todos los secretos de la aplicación.  
*Verificación:* `for p in .git/HEAD .git/config .env .env.backup backup.sql dump.sql composer.json package.json storage/ vendor/; do curl -s -o /dev/null -w "%{http_code} $p\n" https://host/$p; done` → 404 o 403 en todos; el webroot apunta solo al directorio público.  
*Severidad:* crítica  
*Fuente:* ASVS 5.0.0 V13.4.1 (L1), V13.4.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md · Top 10 A01:2025 §How to prevent https://owasp.org/Top10/2025/A01_2025-Broken_Access_Control/

### SEC-CFG-02 — Las herramientas de depuración, la documentación de API, los paneles de monitorización y el código de prueba nunca son accesibles en producción sin autenticación
*Si no:* exposición de peticiones, consultas, trabajos en cola y variables de entorno; superficie de ataque regalada.  
*Verificación:* `for p in telescope horizon _debugbar _ignition/health-check docs redoc openapi.json swagger debug/pprof/ metrics phpinfo.php adminer.php; do curl -s -o /dev/null -w "%{http_code} $p\n" https://host/$p; done`; `rg -n "phpinfo\(|\bdd\(|var_dump\(|debugger;|net/http/pprof"`; rutas de test y siembra desactivadas por entorno.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V13.4.5 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x22-V13-Configuration.md, V15.2.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md · Top 10 A02:2025 https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/

### SEC-CFG-03 — Las cabeceras que fija el proxy (`X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Host`, `X-User-*`) solo se aceptan cuando vienen del proxy de confianza; nunca del cliente final
*Si no:* evasión de límites de uso y bloqueos por IP, logs con IP falsificada, envenenamiento de URL generadas, suplantación si una cabecera transporta identidad.  
*Verificación:* leer la configuración de proxies de confianza (no "todos" salvo red cerrada); `rg -n -i "x-forwarded-for|x-real-ip|HTTP_X_FORWARDED"` leídas a mano en el código; test: `curl -H 'X-Forwarded-For: 1.2.3.4'` y ver qué IP se registra y se limita.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V4.1.3 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x13-V4-API-and-Web-Service.md, V15.3.4 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md

### SEC-CFG-04 — Toda respuesta siempre lleva `X-Content-Type-Options: nosniff`, un `Content-Type` con charset, una política `frame-ancestors` y una `Referrer-Policy`; las respuestas con datos sensibles llevan además `Cache-Control: no-store`
`X-Frame-Options` está obsoleta según ASVS: no cuenta como control.  
*Si no:* interpretación del contenido como otro tipo (XSS), clickjacking, fuga de URL con tokens a terceros, datos privados en cachés del navegador o compartidas.  
*Verificación:* `curl -sI https://host/` y sobre un endpoint autenticado, filtrando `x-content-type-options|content-security-policy|referrer-policy|cache-control|content-type`.  
*Severidad:* media  
*Fuente:* ASVS 5.0.0 V3.4.4, V3.4.5, V3.4.6 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md, V4.1.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x13-V4-API-and-Web-Service.md, V14.3.2 (L2) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x23-V14-Data-Protection.md · HTTP Security Response Headers Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

### SEC-CFG-05 — Los buckets y discos de almacenamiento nunca son públicos por defecto; el acceso público solo se concede a prefijos concretos de contenido público
*Si no:* descarga y enumeración de todos los archivos de los usuarios.  
*Verificación:* consultar la política anónima del bucket con la CLI del proveedor; `curl` a la URL directa de un objeto privado y al listado del bucket → 403.  
*Severidad:* alta  
*Fuente:* Top 10 A02:2025 §How to prevent https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/ · Authorization Cheat Sheet §Enforce Authorization Checks on Static Resources https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

## 20. Componentes vulnerables (DEP)

### SEC-DEP-01 — Las dependencias siempre se instalan con versiones fijadas por un lockfile versionado, y solo desde repositorios oficiales
El lockfile como implementación de "elegir deliberadamente la versión" es derivación; la fuente no lo nombra.  
*Si no:* build no reproducible que arrastra una versión comprometida; confusión de dependencias; paquetes con nombre casi idéntico al legítimo.  
*Verificación:* `git ls-files | rg "composer\.lock|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|uv\.lock|poetry\.lock|pubspec\.lock"`; el build usa el modo de instalación congelada; `rg -n "\"repositories\"|registry=|index-url|^replace |git\+https|github:" composer.json .npmrc package.json pyproject.toml go.mod`.  
*Severidad:* media  
*Fuente:* Top 10 A03:2025 §How to prevent https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/ · Top 10 A08:2025 https://owasp.org/Top10/2025/A08_2025-Software_or_Data_Integrity_Failures/ · ASVS 5.0.0 V15.1.2 (L2), V15.2.4 (L3) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md

### SEC-DEP-02 — Nunca permanece en producción una dependencia con vulnerabilidad conocida o sin soporte más allá del plazo de remediación documentado
ASVS exige que ese plazo esté escrito (V15.1.1).  
*Si no:* explotación de vulnerabilidades públicas con exploit disponible.  
*Verificación:* `composer audit`; `npm audit --omit=dev`; `govulncheck ./...`; `pip-audit`; `osv-scanner -r .`; versiones de lenguaje y framework dentro de su ventana de soporte; existe el documento con los plazos.  
*Severidad:* alta  
*Fuente:* ASVS 5.0.0 V15.1.1, V15.2.1 (L1) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x24-V15-Secure-Coding-and-Architecture.md · Top 10 A03:2025 https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/ · Vulnerable Dependency Management Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Vulnerable_Dependency_Management_Cheat_Sheet.html · Proactive Controls 2024 C6 https://top10proactive.owasp.org/archive/2024/the-top-10/c6-use-secure-dependencies/

### SEC-DEP-03 — Los scripts y estilos de terceros solo se cargan autoalojados o con Subresource Integrity sobre una versión fija
*Si no:* el compromiso del CDN o del proveedor ejecuta código en todos los usuarios: robo de datos de formularios de pago y de sesión.  
*Verificación:* `rg -n "<(script|link)[^>]+(src|href)=\"https?://"` → cada uno con `integrity=` y `crossorigin`, sin URL de versión flotante (`@latest`).  
*Severidad:* media  
*Fuente:* Third Party JavaScript Management Cheat Sheet §Subresource Integrity https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html · ASVS 5.0.0 V3.6.1 (L3) https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md · Top 10 A08:2025 https://owasp.org/Top10/2025/A08_2025-Software_or_Data_Integrity_Failures/

---

## 21. Divergencias entre fuentes

| Tema | Fuente A | Fuente B | Decisión en el catálogo |
|---|---|---|---|
| Entropía del identificador de sesión | Session Management CS: mínimo 64 bits (128 si se genera a mano) | ASVS V7.2.3: 128 bits | 128 bits (SES-05) |
| Token de sesión en almacenamiento del navegador | ASVS V14.3.3: admite el token de sesión | Session Management CS: prohibido | Prohibido (SES-04) |
| bcrypt | Password Storage CS: "solo en sistemas heredados", coste ≥ 10 | Top 10 A04:2025: "para sistemas heredados con bcrypt, ver la cheat sheet" | Se admite con coste ≥ 10 y límite de 72 bytes (AUTH-01, AUTH-02) |
| Lista de contraseñas comunes | ASVS V6.2.4: las 3 000 más usadas (L1), filtradas (L2) | Top 10 A07:2025: las 10 000 peores | Lista de comunes más comprobación de filtradas (AUTH-02) |
| Longitud mínima de contraseña | ASVS V6.2.1: 8, recomienda 15 | Authentication CS: 8 con MFA, 15 sin MFA | 8 como mínimo exigible; 15 sin MFA como recomendación (AUTH-02) |
| `SameSite` como defensa CSRF | CSRF CS: defensa en profundidad, suficiente solo bajo cinco condiciones | ASVS V3.5.x: exige token, cabecera o Fetch Metadata | No cuenta como defensa única (CSRF-01) |
| Referencia a NIST | Top 10 A07:2025 enlaza SP 800-63-3 | Authentication CS enlaza SP 800-63-4 | Se sigue la cheat sheet (más reciente) |

## 22. Requisitos ASVS L1/L2 que no se convirtieron en regla

- **Requisitos de documentación** (V2.1.x, V5.1.1, V6.1.x, V7.1.x, V8.1.x, V11.1.x, V13.1.1, V14.1.x, V15.1.3, V16.1.1): exigen que algo esté escrito, no que el código haga algo. Solo V15.1.1 entra, dentro de DEP-02.
- **Servidor de autorización OAuth y proveedor OpenID** (V10.4.x, V10.6.x, V10.7.x): aplican si la aplicación emite tokens para terceros. Investigador 2.
- **Fuera del stack**: LDAP, XPath, LaTeX, JNDI, memcache, cadenas de formato, seguridad de memoria (V1.2.6–V1.2.8, V1.3.8–V1.3.10, V1.4.x); SAML (V6.8.3); WebRTC (V17); tecnologías de cliente obsoletas (V3.7.1).
- **Infraestructura** (investigador 4): versiones y suites de TLS (V12.1.x), TLS entre servicios internos (V12.3.x), desincronización de peticiones HTTP (V4.2.1), método TRACE (V13.4.4), allowlist de salida de red (V13.2.5), antivirus sobre archivos (V5.4.3).
- **API** (investigador 2): GraphQL (V4.3.x), redirección HTTP→HTTPS en endpoints no navegables (V4.1.2), audiencia y tipo de token (V9.2.2, V9.2.4, V10.3.x).
- **Sin verificación mecánica razonable**: canonicalización única antes de validar (V1.1.1), contaminación de parámetros HTTP (V15.3.7), escape de expresiones regulares (V1.2.9), inyección en cabeceras de correo (V1.3.11), `postMessage` (V3.5.5), separación de aplicaciones por hostname (V3.5.4), limpieza de datos del cliente al cerrar sesión (V14.3.1), gestión de sesiones concurrentes (V7.4.5, V7.5.2). Candidatos a una segunda tanda.

## 23. Dudas y huecos

1. **Fecha oficial de publicación del Top 10:2025: sin verificar.** Solo consta que el aviso de *release candidate* se retiró del repositorio el 2025-12-24 y que el sitio del proyecto lo declara "most current released version".
2. **Proactive Controls**: la edición vigente es 2024; hay un borrador "Future Top 10 (WIP)" publicado en el mismo sitio. No se usó el borrador. Fecha original de publicación de la edición 2024: sin verificar.
3. **Reglas con derivación propia** (el principio está en la fuente, la aplicación concreta no): AUTH-08 (extensión a todo enlace por correo), SSRF-02 (conectar a la IP validada), BIZ-03 (webhooks), DEP-01 (lockfile), SECR-02 (bundle del cliente). Están marcadas en el texto de cada una.
4. **Sin cheat sheet dedicada localizada**: inyección de plantillas en servidor (INJ-05 se apoya solo en ASVS V1.3.7) y contaminación de prototipo (INJ-08, solo ASVS V15.3.6).
5. **Abuse Case Cheat Sheet** figura como "Historical" (archivada): no se usó. La fuente vigente para lógica de negocio es Business Logic Security Cheat Sheet.
6. **Cheat sheets sin versión**: son documentos vivos. Lo citado corresponde a `master` del 2026-10-02 (`063e9df7b0`); los nombres de sección pueden cambiar.
7. **No cubierto por las fuentes leídas** y relevante para el stack: SSRF a través de generadores de PDF o capturas que renderizan HTML del usuario; importes monetarios en coma flotante; saneado de datos enviados al servicio externo de errores más allá de LOG-02. Ninguna fuente primaria lo enuncia de forma citable: quedaron fuera.
8. **Patrones de `rg`**: no se ejecutaron contra ningún repositorio del usuario. Son puntos de partida a calibrar por stack (investigador 2) y generarán falsos positivos.
