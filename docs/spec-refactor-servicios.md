# Spec — Organización de servicios por vista de consumidor

- **Estado:** Lista para implementar (`ready-for-agent`)
- **Fecha:** 2026-07-21
- **Decisión de referencia:** [ADR 0001](adr/0001-organizacion-de-servicios-por-vista.md)
- **Plan de ejecución:** [refactor-servicios-plan.md](refactor-servicios-plan.md)

> Nota sobre el formato: esta spec nombra módulos (`payment_core_s`, `products_storefront_s`) porque
> los módulos **son el entregable**, no un detalle de implementación. No incluye números de línea ni
> rutas de directorio, que sí quedan obsoletos.

---

## Problem Statement

El equipo — humano y agentes — no puede auditar la lógica de negocio del backend. Tres módulos de
servicio (`payment_s`, `products_s`, `orders_s`) concentran entre 950 y 1132 líneas cada uno, con hasta
43 funciones en un único namespace plano y sin ninguna señal de qué función es entrada pública, dónde
empieza un flujo ni dónde termina.

El síntoma no es el tamaño. El promedio es de ~22 líneas por función: no hay funciones monstruosas, hay
muchas funciones pequeñas amontonadas sin fronteras. El síntoma real es que **preguntas simples requieren
leer el módulo entero**:

- ¿La vista storefront y el catálogo administrado cotizan un producto igual? (No. Uno aplica descuentos,
  el otro no. Las dos funciones están separadas por 130 líneas y sus nombres no se parecen.)
- ¿Cuántos caminos hacen que una orden pase a pagada? (Dos. La función que los ejecuta está declarada
  como privada, en el primer 12 % de un módulo de 1132 líneas.)

La consecuencia es que **cualquier refactor sobre estos módulos es imposible de justificar**: no se puede
distinguir duplicación accidental (que hay que eliminar) de divergencia legítima (que hay que preservar y
documentar), y el riesgo de romper algo crece con la importancia del módulo. Estos son justamente los
módulos donde vive el dinero y el stock.

## Solution

Partir los tres módulos **por vista de consumidor**, produciendo 2–3 módulos por dominio, mediante un
refactor de **puro movimiento de código**: ninguna función se agrega, se borra ni se modifica.

El corte se aplica solo donde el código ya presenta una costura real, y por eso **cada dominio se parte
con un criterio distinto**:

| Dominio | Módulos resultantes | Costura |
|---|---|---|
| products | `products_s` + `products_storefront_s` | Vista storefront vs catálogo administrado |
| orders | `orders_s` + `orders_public_s` | Público anónimo vs autenticado |
| payments | `payment_s` + `payment_core_s` + `payment_provider_s` | Kernel vs proveedor vs ciclo de vida |

Al terminar, las preguntas de arriba se responden abriendo un archivo. Que la vista storefront cotice
distinto al catálogo administrado deja de parecer un bug latente y pasa a ser una **divergencia legítima**
visible: dos vistas del negocio, dos archivos, dos reglas. Y `apply_order_paid_transition` — el punto por
el que entra el dinero — pasa a ser una función pública, en un módulo llamado kernel de pago, con sus dos
llamadores a la vista.

La garantía de que no se pierde nada no es "lo revisé": es una comparación mecánica de inventario de
símbolos antes y después, que exige partición exacta.

## User Stories

1. Como desarrollador, quiero que la vista storefront viva en su propio módulo, para poder responder "¿qué ve el cliente anónimo?" sin leer el catálogo administrado.
2. Como desarrollador, quiero que el cálculo de precio con descuentos esté separado del cálculo sin descuentos, para poder ver que la divergencia es intencional y no un bug.
3. Como desarrollador, quiero que el kernel de pago sea un módulo nombrado, para saber qué lógica comparten todos los caminos de pago.
4. Como desarrollador, quiero que `apply_order_paid_transition` sea pública, para poder buscarla y encontrar sus llamadores sin leer 1132 líneas.
5. Como desarrollador, quiero que el snapshot público de orden esté aislado, para poder auditar qué datos se exponen sin autenticación.
6. Como auditor de seguridad, quiero que la superficie anónima del sistema esté en módulos identificables, para poder revisarla sin recorrer el código autenticado.
7. Como desarrollador, quiero que todo lo que habla con MercadoPago viva en un módulo, para poder evaluar el impacto de un cambio del proveedor.
8. Como desarrollador, quiero que `webhook_events_s` deje de importar símbolos privados, para que la dependencia entre módulos sea contractual y no accidental.
9. Como desarrollador, quiero que `payment_admin_queries_s` deje de importar símbolos privados, por la misma razón.
10. Como agente de IA, quiero módulos por debajo de las ~800 líneas con una responsabilidad nombrable, para poder cargar el contexto relevante sin leer el dominio entero.
11. Como agente de IA, quiero que el nombre del módulo prediga su contenido, para poder elegir dónde buscar sin abrir varios archivos.
12. Como desarrollador, quiero que los módulos de un mismo dominio queden adyacentes al listar el directorio, para ver de un vistazo cómo está partido ese dominio.
13. Como revisor de código, quiero que el import en el call-site diga en qué vista del dominio estoy parado, para entender un diff sin abrir el servicio.
14. Como desarrollador, quiero que el manejo de ciclo de vida de sesión viva en el módulo de sesión y no dentro del servicio de productos, para encontrarlo donde lo espero.
15. Como desarrollador, quiero que el refactor sea puro movimiento, para poder revisar el diff confiando en que ningún comportamiento cambió.
16. Como desarrollador, quiero una verificación mecánica de que no se perdió ninguna función, porque los tests verdes no prueban eso.
17. Como desarrollador, quiero que cada commit quede verde por sí solo, para poder revertir uno sin perder los demás.
18. Como desarrollador, quiero que el commit de mayor riesgo vaya aislado, para que un revert no arrastre trabajo sano.
19. Como desarrollador, quiero que el refactor empiece por el dominio menos riesgoso, para validar el arnés de verificación antes de aplicarlo donde vive el dinero.
20. Como responsable del proyecto, quiero un punto de control antes de tocar pagos, para decidir si el patrón funcionó antes de asumir el riesgo mayor.
21. Como desarrollador, quiero que `openapi.json` quede byte-idéntico, para tener prueba objetiva de que la API pública no se movió.
22. Como consumidor del frontend, quiero que ningún endpoint, payload ni código de error cambie, para no tener que tocar nada.
23. Como lector futuro, quiero un ADR que explique por qué cada dominio se parte distinto, para no leerlo como una inconsistencia.
24. Como lector futuro, quiero saber qué alternativas se descartaron y por qué, para no reabrir la discusión sin información nueva.
25. Como lector futuro, quiero un criterio explícito de fracaso del corte de pagos, para saber cuándo revisar la decisión.
26. Como desarrollador, quiero que la documentación referencie símbolos y no números de línea, para que siga siendo correcta después del próximo commit.
27. Como desarrollador, quiero que las 149 referencias a estos módulos en la documentación se actualicen, para que la documentación no quede apuntando al vacío.
28. Como desarrollador nuevo, quiero que el glosario del proyecto siga siendo uno solo, para no tener que consultar dos fuentes de verdad.
29. Como desarrollador, quiero los términos de esta reorganización en el glosario existente, para tener vocabulario compartido al discutir estos módulos.
30. Como desarrollador, quiero que la distinción entre divergencia legítima y duplicación accidental esté escrita, para poder auditar duplicación con un criterio y no por intuición.
31. Como desarrollador, quiero que los bugs encontrados durante el movimiento se registren en vez de arreglarse, para preservar la garantía de verificación.
32. Como desarrollador, quiero que los bugs registrados no se pierdan, para poder atenderlos en commits posteriores.
33. Como desarrollador, quiero que la deuda que este refactor no toca quede listada, para que nadie asuma que ya se resolvió.
34. Como desarrollador, quiero que `users_s` quede fuera del alcance, porque partir un módulo de 314 líneas y un solo tema sería granularizar de más.
35. Como desarrollador, quiero que el remanente de productos no se parta más, porque su lógica de producto, variante, categoría y stock está genuinamente entrelazada.
36. Como desarrollador, quiero que las vistas de usuario y admin de órdenes sigan juntas, porque comparten los caminos de creación y las reglas de transición de estado.
37. Como desarrollador, quiero no introducir paquetes con fachada, para que el import en el call-site siga siendo informativo.
38. Como desarrollador, quiero que el test que importa el módulo de productos entero se actualice, para que no rompa al mudarse la vista storefront.
39. Como desarrollador, quiero que el arnés de inventario AST sea descartable, para no dejar un test que falle en cada refactor legítimo futuro.
40. Como desarrollador, quiero que la verificación se apoye en los tests de router existentes, porque son el seam más alto y un movimiento puro les es invisible.

## Implementation Decisions

**Eje del corte: vista de consumidor, no sub-entidad.** Partir por sub-entidad (producto | variante |
categoría | stock) habría dejado los dos cálculos de precio mínimo en el mismo módulo — ambos son
"producto" — sin resolver nada. La divergencia corre sobre el eje de consumidor.

**El eje se aplica solo donde hay costura real, con excepciones explícitas.** En órdenes, la costura es
público/autenticado y **no** usuario/admin: las dos vías de creación de venta comparten el mismo camino
interno y las reglas de transición de estado son comunes. Separar usuario de admin habría producido un
módulo importando media docena de privados del otro.

**El kernel de pago se extrae primero, no como sobra.** Pagos no tenía ningún bloque autocontenido: el
serializador de pago se usa en 18 lugares de todos los grupos. La extracción del kernel es el movimiento
de mayor valor porque hace nombrable el punto de entrada del dinero.

**Promoción de privados a públicos.** Once símbolos del kernel de pago pierden el guion bajo al pasar a
ser API entre módulos. Esa lista es la **única excepción permitida** a la verificación de cuerpos
idénticos; cualquier otro cambio de cuerpo es un error del refactor.

**Módulos hermanos planos, sin paquetes ni fachadas.** Una fachada que re-exporta todo reconstruye el
namespace plano del que se quiere escapar. Con 16 call-sites en total, el ahorro no compensa el segundo
lugar a mantener sincronizado. Se esperan 2–3 módulos por dominio, no 6.

**Nombres: dominio primero, sufijo `_s` conservado.** `products_storefront_s`, no
`storefront_products_s`, para que los módulos de un dominio queden adyacentes al listar. El sufijo `_s`
se conserva pese a estar registrado como deuda (CS-15): cambiarlo implica renombrar los 26 módulos de
servicios y es otro refactor.

**El session scope se muda al módulo de sesión.** Existía solo dentro del servicio de productos, pero es
ciclo de vida de sesión, no lógica de producto. Ambas mitades del split lo necesitan; duplicarlo sería
duplicación accidental. Pierde el guion bajo al pasar a ser API entre módulos.

**Se comparte lo que debe ser consistente, se duplica lo que legítimamente diverge.** El etiquetado de
variante para humanos se importa entre los módulos de órdenes (debe ser consistente en toda vista). El
cálculo de precio no se unifica (diverge por diseño). El import queda acíclico: público depende de core,
nunca al revés.

**Disciplina de puro movimiento.** Durante los commits de movimiento no se arregla ningún bug ni se
aplica ninguna simplificación. Los hallazgos se registran y se atienden después. Esta disciplina es la
condición que hace verificable la garantía de no pérdida.

**Secuencia por riesgo ascendente**, con punto de control humano antes de pagos: session scope →
products → orders → ⏸ → kernel de pago → proveedor de pago → documentación. El arnés de verificación es
código nuevo y también puede estar mal; conviene estrenarlo donde el resultado se verifica a ojo.

**Sin cambios de contrato.** No hay cambios de esquema de base de datos, ni de endpoints, ni de payloads,
ni de códigos de error. El frontend no se toca.

**Documentación por símbolo.** Las 149 referencias en 15 documentos se re-anclan a nombre de símbolo en
vez de número de línea. Re-pinnear líneas compra documentación correcta hasta el próximo commit.

**Un solo glosario.** No se crea `CONTEXT.md`: el proyecto ya tiene glosario con 26 entradas y el mismo
formato. Los términos nuevos se agregan ahí, junto con la corrección de las dos entradas existentes
cuyos punteros se mueven.

## Testing Decisions

**Qué hace bueno a un test acá:** que no sepa nada de la estructura interna de los servicios. Un test que
entra por el router y afirma sobre la respuesta HTTP es ciego a este refactor por construcción — y esa
ceguera es exactamente lo que lo vuelve una prueba válida de que nada cambió. Un test que importa un
helper privado de un servicio no prueba comportamiento: prueba layout, y por eso se rompe.

**Tres seams, dos de ellos ya existentes:**

1. **Tests HTTP de fundamentos, vía router** — el seam más alto disponible y el principal. Ya cubren
   checkout, pagos, CRUD de productos, catálogo, reservas de stock y webhooks de administración. No se
   escriben tests nuevos: la cobertura existente es la prueba.
2. **Exportador de OpenAPI** — ya existe como script. Se regenera y se exige diff vacío contra el
   artefacto versionado. Prueba objetiva de que la superficie pública no se movió.
3. **Inventario AST de símbolos** — seam nuevo, y el único que prueba lo que los tests no pueden: que no
   se perdió ninguna función. Extrae nombres de funciones top-level y cuerpos normalizados antes y
   después, y exige partición exacta.

**El arnés AST es descartable.** Vive fuera del repositorio, se usa durante los commits del refactor y se
tira. Un test versionado de inventario de símbolos congelaría el layout de archivos: fallaría en cada
refactor legítimo futuro y la respuesta siempre sería actualizar el valor esperado — un test que nunca
afirma nada verdadero. Es herramienta de migración, no guard de regresión.

**Cuarto check, no un seam:** el linter con reglas de pyflakes activas detecta nombres indefinidos e
imports sin usar, que son precisamente los errores que produce un movimiento mal hecho.

**Los cuatro checks corren en cada commit**, no solo al final. Un commit no está terminado sin los cuatro.

**Prior art:** los tests HTTP de fundamentos son el patrón establecido del proyecto para verificación de
comportamiento de extremo a extremo, con una clase base compartida. Los tests que importan internals de
servicios son el antipatrón que este refactor deja expuesto — se actualizan sus imports pero **no se
suben de seam**, porque eso sería trabajo fuera del movimiento puro. Queda registrado como hallazgo.

## Out of Scope

- **`users_s`.** 314 líneas, 6 funciones públicas, un solo tema. Partirlo sería granularizar de más.
- **Cualquier arreglo de bug.** Lo que se encuentre se registra, no se toca.
- **Cualquier simplificación o deduplicación.** Incluida la deduplicación real que este refactor deja
  visible: eliminarla es el trabajo *siguiente*, habilitado por este.
- **Sufijo `_s` ambiguo** entre esquemas y servicios (CS-15). Implica renombrar 26 módulos.
- **Plural inconsistente** entre el módulo de pagos y los de órdenes y productos. Decisión explícita de
  no unificar, aun sabiendo que estos módulos se tocan igual.
- **Excepciones HTTP filtrándose desde los servicios** (CS-03).
- **Subir de seam los tests que importan internals.** Se actualizan sus imports, nada más.
- **Introducir una capa de repositorio o abstracción de persistencia.** Registrada como deuda del
  proyecto, ortogonal a este refactor.
- **Cualquier cambio en el frontend, el esquema de base de datos o los contratos de API.**
- **Partir más allá de lo especificado**, en particular el remanente de productos y la separación
  usuario/admin en órdenes. Ambas fueron evaluadas y descartadas con razones registradas en el ADR.

## Further Notes

**El riesgo concentrado está en un solo commit.** La extracción del kernel de pago promueve 11 privados a
públicos y es el único commit con superficie de cambio fuera de su propio dominio. Va aislado
precisamente para que un revert no arrastre el trabajo sano de productos y órdenes.

**Trampa ya identificada:** existe un único test en todo el repositorio que importa un servicio como
módulo completo en vez de importar símbolos, y llama a través de él una función que se muda. Se rompe en
el primer commit. Está en el checklist.

**Criterio de fracaso, escrito por adelantado:** si el kernel de pago supera las ~350 líneas, el corte de
pagos falló — significará que "kernel" fue un cajón para lo que sobra compartido y no una frontera real.
Ese es el momento de revisar el ADR. Un módulo llamado "core" siempre merece esta cláusula.

**Este refactor no mejora ningún comportamiento y no debería.** Su entregable es capacidad de análisis:
habilita el trabajo de deduplicación y trazabilidad que hoy no se puede ni siquiera evaluar. Medir su
éxito por líneas ahorradas o por bugs cerrados sería medir la cosa equivocada.
