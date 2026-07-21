# Documentación Técnica — PatitasBigotes

> Auditoría y documentación integral del repositorio, generada a partir de la lectura completa del código fuente
> (284 archivos versionados, ~38.200 líneas). Última actualización: **2026-07-21**, commit base `ee3aa54`.

Esta documentación está pensada para que una persona desarrolladora nueva pueda **comprender, mantener y evolucionar
el sistema sin necesidad de recorrer el código fuente primero**. Cada afirmación está anclada a un archivo y, cuando
aporta valor, a una línea concreta. Todo lo que es inferencia y no verificación directa está marcado como
`**Hipótesis:**`.

---

## Índice de documentos

| # | Documento | Niveles cubiertos | Para quién |
|---|---|---|---|
| 01 | [Resumen Ejecutivo](01_Resumen.md) | 1 | Todos — empezar aquí |
| 02 | [Arquitectura](02_Arquitectura.md) | 2 | Arquitectura, tech leads |
| 03 | [Árbol del Proyecto](03_ArbolProyecto.md) | 3 | Onboarding |
| 04 | [Backend — archivo por archivo y función por función](04_Backend.md) | 4, 5, 6 | Backend |
| 05 | [Frontend](05_Frontend.md) | 9 (+4 para frontend) | Frontend |
| 06 | [Panel Admin](06_PanelAdmin.md) | 10 | Frontend, producto |
| 07 | [API](07_API.md) | 8 | Backend, frontend, integraciones |
| 08 | [Base de Datos](08_BaseDatos.md) | 7 | Backend, DBA |
| 09 | [Reglas de Negocio](09_ReglasNegocio.md) | 11 | Producto, QA, todos |
| 10 | [Flujos Completos](10_Flujos.md) | 12 | Todos |
| 11 | [Seguridad](11_Seguridad.md) | 13 | Seguridad, backend |
| 12 | [Performance](12_Performance.md) | 14 | Backend, frontend |
| 13 | [Calidad de Código](13_CalidadCodigo.md) | 15 | Tech leads |
| 14 | [Dependencias](14_Dependencias.md) | 16 | Todos |
| 15 | [Configuración](15_Configuracion.md) | 17 | DevOps, onboarding |
| 16 | [Testing](16_Testing.md) | 18 | QA, backend, frontend |
| 17 | [Production Readiness](17_ProductionReadiness.md) | 19 | DevOps, SRE |
| 18 | [Roadmap](18_Roadmap.md) | 20 | Tech leads, producto |
| 19 | [Glosario](19_Glosario.md) | 21 | Todos |
| 20 | [Diccionario de Objetos](20_DiccionarioObjetos.md) | 22 | Backend |
| 21 | [Mapa de Dependencias entre Módulos](21_MapaDependencias.md) | 23 | Arquitectura |
| 22 | [Índice de Lectura](22_IndiceLectura.md) | 24 | Onboarding |

Los diagramas Mermaid usados en los documentos también viven sueltos en [`diagrams/`](diagrams/) para poder
reutilizarlos o renderizarlos de forma independiente.

### Decisiones de arquitectura (ADR)

| # | Decisión | Estado |
|---|---|---|
| [0001](adr/0001-organizacion-de-servicios-por-vista.md) | Organización de servicios por vista de consumidor | Aceptada |

Documentos de trabajo del refactor asociado: [spec](spec-refactor-servicios.md) (qué y para quién) y
[plan](refactor-servicios-plan.md) (tabla símbolo→destino, checkboxes, hallazgos).

---

## Cómo leer esta documentación

- **Si es tu primer día:** seguí el orden propuesto en [22_IndiceLectura.md](22_IndiceLectura.md).
- **Si venís a arreglar un bug de pagos:** [09_ReglasNegocio.md](09_ReglasNegocio.md) →
  [10_Flujos.md](10_Flujos.md) → [04_Backend.md](04_Backend.md#payment_spy).
- **Si venís a agregar un endpoint:** [07_API.md](07_API.md) → [04_Backend.md](04_Backend.md) →
  [16_Testing.md](16_Testing.md).
- **Si venís a desplegar:** [15_Configuracion.md](15_Configuracion.md) →
  [17_ProductionReadiness.md](17_ProductionReadiness.md) → `DEPLOYMENT.md` y `DEPLOYMENT_WALKTHROUGH.md` en la raíz.

## Convenciones usadas

| Marca | Significado |
|---|---|
| `**Hipótesis:**` | Inferencia razonable pero **no** verificable directamente en el código. |
| ⚠️ | Riesgo, deuda técnica o comportamiento contraintuitivo detectado. |
| 🔒 | Nota de seguridad. |
| ⚡ | Nota de performance. |
| `archivo.py:123` | Referencia a archivo y línea, relativa a la raíz del repositorio. |

## Renderizado

Los diagramas están en Mermaid y se renderizan nativamente en GitHub, GitLab y VS Code
(extensión *Markdown Preview Mermaid Support*). Para exportar a PDF, ver la nota al pie de
[22_IndiceLectura.md](22_IndiceLectura.md#exportar-a-pdf).
