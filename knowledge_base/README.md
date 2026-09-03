# Engineering Knowledge Base - UDS Pan Energy
Base de conocimiento de ingeniería para el MCP PETEX v2.

## Estructura
```
knowledge_base/
  correlations/     → Qué correlaciones usar según formación/fluido
  pvt/              → Parámetros PVT por área/formación
  field_rules/      → Reglas operativas y rangos válidos
  lessons_learned/  → Experiencias positivas y negativas
  templates/        → Modelos .Out pre-validados como base
```

## Cómo se usa
El MCP consulta esta base ANTES de armar un modelo.
Ejemplo: si el usuario dice "pozo horizontal en Vaca Muerta",
el MCP busca en esta base y sabe que debe usar PE2, API~35, GOR~800, etc.
