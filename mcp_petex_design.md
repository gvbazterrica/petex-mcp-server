# MCP PETEX v2 - Diseño de Arquitectura
**Autor**: Gonzalo Vidal Bazterrica - UDS Pan Energy  
**Fecha**: 2026-08-27

## 1. Vision

Un MCP server para PETEX IPM que:
- Ejecuta en vivo contra licencia real via OpenServer Python
- Consulta documentacion (RAG) cuando encuentra errores
- Conoce la secuencia correcta de operaciones
- Aprende de errores previos

## 2. Arquitectura

```
              ┌──────────┐
              │ Kiro/LLM │
              └────┬─────┘
                   │ MCP Protocol
              ┌────┴─────┐
              │MCP Server│
              │ (FastMCP)│
              └────┬─────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
  ┌─────┴─────┐ ┌─┴────┐ ┌──┴────────┐
  │OpenServer │ │ RAG  │ │ Workflow  │
  │ Executor  │ │  KB  │ │  Engine   │
  │           │ │      │ │           │
  │DoCmd/Set/ │ │Chroma│ │Templates  │
  │Get+retry  │ │+PDFs │ │validados  │
  └───────────┘ └──────┘ └───────────┘
```

## 3. Componentes Principales

### 3.1 RAG Knowledge Base

Fuentes: openserver.pdf, prosper2.pdf, GAP.pdf, MCP_PETEX_Hallazgos.md

Tech: ChromaDB local + sentence-transformers. Chunks de 500-1000 tokens por seccion.

### 3.2 OpenServer Executor con Retry

Wrapper que si falla con "Variable not found", consulta RAG, encuentra la variable correcta, y reintenta.

### 3.3 Workflow Engine

Secuencias pre-validadas contra IPM 13.5 para cada flujo (crear pozo, crear red, etc).

### 3.4 Engineering Knowledge Base (RAG #2)

Base de conocimiento de ingenieria separada de la doc tecnica:
- Correlaciones recomendadas por formacion/cuenca
- Rangos PVT tipicos por area
- Reglas de validacion operativas
- Lecciones aprendidas de modelos calibrados
- Templates .Out pre-validados

Estructura: `knowledge_base/correlations/`, `knowledge_base/pvt/`, etc.
El equipo UDS la llena con datos reales de campo.

## 4. Hallazgo clave: MBAL.MB.VALIDATE

MBAL tiene un comando `MBAL.MB.VALIDATE` que valida todos los objetos
sin necesidad de interaccion GUI. Esto significa que MBAL es 100%
automatizable via OpenServer.

PROSPER NO tiene un equivalente. El "Done" de Equipment Data no tiene
comando OpenServer. Este sigue siendo el unico blocker para automatizacion
end-to-end de PROSPER.

Workaround recomendado: usar archivos .Out template pre-validados y solo
modificar parametros via OpenServer.

## 5. Documentacion de referencia

| Archivo | Contenido |
|---------|-----------|
| mcp_petex_variables.md | Variables PROSPER verificadas |
| mcp_petex_mbal_variables.md | Variables MBAL verificadas |
| mcp_petex_gap_variables.md | Variables GAP verificadas |
| mcp_petex_workflows.md | Secuencias paso a paso |
| MCP_PETEX_Hallazgos.md | Errores encontrados y correcciones |
| knowledge_base/ | Base de conocimiento de ingenieria |
| mcp_petex_v2_prototype.py | Codigo prototipo del MCP |
