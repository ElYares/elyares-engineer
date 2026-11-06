# Proceso personal (PSP) de la familia elyares

Adaptación de PSP (Watts Humphrey, SEI) a agentes que solo leen. Los agentes
**no miden tu tiempo**; miden lo que ven en el código: qué defectos hay, de qué
tipo y en qué fase entraron. Lo demás (plan contra real, mejoras) lo cierra
`/bitacora`. Los agentes lo leen en `~/.claude/elyares/proceso/psp.md`.

## Fases

`planeación` · `requisitos` · `diseño` · `revisión de diseño` · `código` ·
`revisión de código` · `compilación` · `pruebas` · `postmortem`

Un defecto tiene dos fases: la que lo **metió** y la que lo **encontró**. Un
agente solo ve el diff, así que la fase donde lo encontró es la suya
(«revisión de código»); la que lo metió la deduce del tipo (un defecto de
`Función` casi siempre entró en diseño; uno de `Sintaxis`, en código). Si no
se puede deducir, escribe «entró en: sin determinar»; no la inventes.

## Tipos de defecto

Una sola clasificación para todos los agentes, para que sus conteos sumen.

| Tipo | Es… | Ejemplo |
|---|---|---|
| `Documentación` | comentario, mensaje o texto equivocado | comentario que miente, texto de interfaz con error |
| `Sintaxis` | ortografía o puntuación del lenguaje | paréntesis, import que no existe |
| `Construcción` | build, paquete, versiones, dependencias | lockfile desfasado, target de Makefile roto |
| `Asignación` | declarar, inicializar, alcance | variable sin inicializar, alcance equivocado |
| `Interfaz` | llamadas, parámetros, contratos entre piezas | firma que no coincide con su uso, contrato de API roto |
| `Verificación` | validaciones, condiciones, manejo de errores | falta una guarda, excepción tragada, límite mal comparado |
| `Datos` | estructura o contenido de datos | tipo equivocado, estado como string suelto |
| `Función` | lógica, flujo, algoritmo, regla de negocio | cálculo mal, caso no contemplado |
| `Sistema` | configuración, tiempo, memoria, recursos | fuga, timeout ausente, condición de carrera |
| `Entorno` | herramientas, plataforma, despliegue | imagen sin versión fija, CI distinto de local |

Un hallazgo de seguridad también lleva tipo (un IDOR es `Verificación`; un
secreto en el repo, `Construcción`). Si dudas entre dos tipos, el que
corresponde a **la corrección**: cómo se arregla decide dónde se clasifica.

## Cómo lo reporta un agente que revisa

1. Cada hallazgo añade una línea:
   `Defecto: <tipo> · entró en: <fase> · encontrado en: revisión de código`
2. El informe cierra con un bloque, antes de «Qué revisé»:

```
## Defectos
- Por tipo: <Verificación 3 · Función 1 · …>
- Por fase en que entraron: <diseño 1 · código 3 · sin determinar 0>
- Densidad: <N hallazgos bloquea+conviene> en <M líneas cambiadas> → <N/M×1000> por KLOC
- Para la lista personal: <la comprobación que habría evitado el tipo que más se repite, en una línea; «ninguna» si no se repitió>
```

- Las líneas cambiadas salen de un comando (`git diff --numstat $B`, suma de
  añadidas), no de una estimación. Sin diff (archivo suelto, repo entero), la
  densidad se omite y se dice.
- No cuentes `nota` en la densidad: mide lo que importa, no lo menor.
- Pocos datos no son tendencia. Con menos de ~10 hallazgos, el conteo describe
  esta revisión y nada más; no digas «sueles…».

## Lista de comprobación personal

PSP2 pide revisar con una lista **armada con tus propios defectos**. Vive en la
nota `Checklist-personal` del proyecto en el vault
(`vaultdocs project <nombre>` da la carpeta).

- Un agente que revisa la **lee si existe** y la recorre junto con sus reglas.
  Si el diff rompe una línea de la lista, el hallazgo cita «lista personal:
  <línea>» como regla.
- Un agente **no la edita**. Propone líneas nuevas en «Para la lista
  personal»; las añade `/bitacora` o la sesión principal.
- Cada línea es una pregunta que se contesta con sí o no
  («¿toda entrada externa pasa por una guarda?»), no un consejo. Máximo ~15:
  una lista larga no se usa. Cuando una línea lleva meses sin saltar, se quita.

## Planear (`elyares-architect`)

Antes de diseñar, el plan lleva:

1. **Tamaño estimado** en líneas nuevas y modificadas, por parte (módulo,
   pantalla, endpoint), clasificadas en muy pequeña, pequeña, mediana, grande
   o muy grande.
2. **Contra qué se compara.** Las bitácoras del proyecto en el vault tienen
   tamaños reales de trabajos parecidos; si hay 3 o más, se usan para calibrar
   cada categoría. Si no hay, el plan dice «estimación sin historial» y da un
   rango, nunca un número solo.
3. **Riesgos** que mueven la estimación (lo que no se conoce todavía).
4. **Diseño conceptual** en una página: partes, responsabilidad de cada una y
   cómo se hablan.

No hay regresión estadística: con pocos proyectos no es fiable. El rango y su
historial valen más que una fórmula.

## Revisión de diseño (`elyares-architect`)

Un diseño que se va a construir se revisa con las cuatro vistas de PSP2.1
antes de escribir código; lo que no se puede escribir en una de ellas todavía
no está diseñado:

1. **Operacional:** qué hace la persona o el sistema externo y qué recibe.
2. **Funcional:** entradas, salidas y efectos de cada pieza.
3. **De estados:** qué estados tiene lo que vive más que una petición y cuáles
   son las transiciones válidas (y las imposibles).
4. **Lógica:** reglas y condiciones, incluidos los límites y los casos
   excepcionales.

## Postmortem (`/bitacora`)

Al cerrar un trabajo:

1. **Plan contra real:** tamaño estimado contra líneas reales
   (`git diff --numstat` de la rama); horas estimadas contra horas reales sacadas
   de las fechas de los commits, avisando que son una cota, no un reloj.
2. **Defectos:** los de los informes de la sesión, por tipo y fase.
3. **Una propuesta de mejora (PIP):** una sola, de una línea, sobre el tipo de
   defecto o la desviación que más pesó.
4. **Lista personal:** añadir las líneas propuestas por los agentes, quitar las
   que ya no saltan.

## Lo que no se hace

- Registro de minutos por fase a mano: es la parte de PSP que más se abandona.
- Cifras de calidad inventadas: sin datos reales, el campo se omite.
- PSP3 (desarrollo cíclico).
