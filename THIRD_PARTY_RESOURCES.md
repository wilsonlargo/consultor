# Recursos de terceros — Consultor App v20

Consultor App utiliza recursos bíblicos como **fuentes de contexto**. No cambia
la autoría ni elimina las atribuciones de los materiales.

## Free Use Bible API — HelloAO

API utilizada para consultar de forma estructurada los comentarios y Tyndale
Open Study Notes por libro/capítulo:

https://bible.helloao.org/

Documentación de comentarios:

https://bible.helloao.org/docs/reference/commentaries/

La API proporciona en cada recurso sus campos de licencia, sitio web y
atribución.

### Tyndale Open Study Notes

Fuente original:

https://tyndaleopenresources.com/

Licencia:

Creative Commons Attribution-ShareAlike 4.0 International
(CC BY-SA 4.0)

Consultor App las identifica como **notas de estudio/contexto**, no como notas
de traducción.

### Adam Clarke Bible Commentary

Licencia informada por HelloAO:

Public Domain Mark 1.0 / Dominio público.

### Jamieson-Fausset-Brown Bible Commentary

Licencia informada por HelloAO:

Public Domain Mark 1.0 / Dominio público.

### John Calvin's Commentaries

HelloAO documenta las ediciones inglesas de Calvin Translation Society / CCEL
como dominio público.

### John Gill Bible Commentary

Licencia informada por HelloAO:

Public Domain Mark 1.0 / Dominio público.

### Keil & Delitzsch Old Testament Commentary

Licencia informada por HelloAO:

Public Domain Mark 1.0 / Dominio público.

### Matthew Henry Bible Commentary

Licencia informada por HelloAO:

Public Domain Mark 1.0 / Dominio público.

## Darby Translation Notes (DTN)

Recurso:

Notes to J. N. Darby's Translation of the Bible.

CrossWire / The SWORD Project identifica el módulo:

```text
Module Name: DTN
Book Name: Darby Translation Notes
Module Type: Commentary
Distribution License: Public Domain
```

Referencia:

https://crosswire.org/sword/modules/ModInfo.jsp?modName=DTN

El contenido se utiliza como notas históricas de traducción.

Consultor App no presenta estas notas como análisis propio ni cambia su
atribución.

La implementación actual consulta por capítulo una representación pública del
texto de DTN y conserva una caché local por VerseRef. La licencia que se muestra
al usuario es la licencia del contenido DTN documentada por CrossWire.

## Recursos anteriores

Las atribuciones de STEPBible-Data, OpenBible.info, Nave's Topical Bible y los
demás recursos de v19 continúan aplicándose.

## Recursos excluidos

Consultor App v20 NO distribuye:

- NET Translator's Notes;
- manuales comerciales;
- contenido protegido de Paratext;
- contenido con permiso de distribución limitado a CrossWire u otro
  distribuidor;
- materiales cuyo estatus de reutilización no esté suficientemente claro.

## Notas privadas

Los archivos importados en `Notas privadas` son responsabilidad del usuario y
permanecen en su almacenamiento local. Consultor App no los redistribuye.


## pyspellchecker

Consultor App v21 utiliza opcionalmente `pyspellchecker` para revisión
ortográfica local en varios idiomas.

Proyecto:

https://github.com/barrust/pyspellchecker

El paquete es software abierto y se instala como dependencia mediante
`requirements.txt`. Consultor App no envía el contenido de las notas a ningún
servicio remoto para realizar la revisión ortográfica.

Los vocabularios personalizados importados por el usuario permanecen en la
configuración local de Consultor App.
