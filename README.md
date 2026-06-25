# legalize-es

Legislación de España en formato Markdown, versionada como repositorio git.

Cada ley es un archivo; cada reforma es un commit con la fecha real de publicación oficial. El `git log` de cada ley te muestra su historia completa — cuándo se sancionó, qué artículos se modificaron y por qué norma.

Cubre legislación estatal española y normativa de las comunidades autónomas publicada en el BOE, en su versión consolidada (texto vigente con todas sus redacciones). Cada norma es un fichero Markdown y cada reforma es un commit de git con la fecha oficial de publicación. Las normas de ámbito estatal se ubican en el directorio es/ y las autonómicas en directorios por jurisdicción (es-pv/, es-ct/, etc.). Datos obtenidos de la API de datos abiertos del BOE.

## Qué contiene

- **Constitución** (`BOE-A-AAAA-N.md`) — `es/BOE-A-1978-31229.md`
- **Ley orgánica** (`BOE-A-AAAA-N.md`) — Rango: ley_organica.
- **Ley** (`BOE-A-AAAA-N.md`) — `es/BOE-A-2015-11430.md`
- **Real Decreto-ley** (`BOE-A-AAAA-N.md`) — Rango: real_decreto_ley.
- **Real Decreto Legislativo** (`BOE-A-AAAA-N.md`) — `es/BOE-A-1996-8930.md`
- **Real Decreto** (`BOE-A-AAAA-N.md`) — Rango: real_decreto.
- **Otros rangos estatales** (`BOE-A-AAAA-N.md`) — Orden, Resolución, Circular, Instrucción, Acuerdo, Decreto, Acuerdo internacional.
- **Normativa autonómica (foral/regional)** (`es-XX/BOE-A-AAAA-N.md`) — Leyes y decretos de comunidades autónomas, ubicados en directorios por jurisdicción ELI (es-pv, es-ct, es-ga, etc.). Incluye rangos forales: ley foral, decreto legislativo, decreto-ley, decreto-ley foral, decreto foral legislativo.

## Fuente de los datos

- **BOE — Agencia Estatal Boletín Oficial del Estado**
  - Portal: https://www.boe.es
  - Datos abiertos (API): https://www.boe.es/datosabiertos
  - Legislación consolidada: https://www.boe.es/legislacion/legislacion_ava.php
  - Condiciones de reutilización / Aviso legal: https://www.boe.es/informacion/aviso_legal/index.php

## Atribución

> Fuente de los datos: Agencia Estatal Boletín Oficial del Estado (https://www.boe.es). Datos reutilizados conforme a las condiciones de reutilización del BOE (Resolución de 27 de junio de 2024). Este repositorio es una obra derivada basada en datos de la Agencia Estatal Boletín Oficial del Estado.

## Estructura de ficheros

Estructura plana: un directorio por ámbito (es/ para el Estado; es-XX/ por comunidad autónoma según código ELI). El rango de la norma (constitución, ley orgánica, ley, real decreto, etc.) figura en el frontmatter YAML, nunca en la ruta del fichero.

## Limitaciones

Las imágenes del texto original se omiten (el proyecto no incorpora activos binarios). Se conserva el texto, las tablas, el formato enriquecido y los metadatos. El identificador del fichero es el ID oficial del BOE; un cambio de formato implicaría regenerar todo el historial de commits.

## Otros países

Este repositorio es parte del proyecto **Legalize**, que mantiene legislación de múltiples países como repos git. Ver https://legalize.dev para el catálogo completo.

## Apoyar

Legalize es libre y abierto. Si este trabajo te resulta útil, puedes ayudar a sostener su alojamiento y desarrollo: [Apoya este proyecto](https://buymeacoffee.com/legalizedev).

## Licencia

- **Código del pipeline**: MIT (https://github.com/legalize-dev/legalize-pipeline)
- **Datos**: Condiciones de reutilización del BOE — cita obligatoria de la fuente
