# Consultor App v21.1 — Corrector ortográfico con diccionario verificable

La v21 toma la v20 como base estable y añade revisión ortográfica local a los
campos en los que escribe el consultor.

No se modifica automáticamente ningún XML. El corrector únicamente subraya
posibles errores en el editor; el usuario decide si los corrige.

## 1. Dónde funciona

La revisión se activa en:

```text
Mi nota
Respuesta / seguimiento que estoy escribiendo
```

No se aplica a:

```text
respuesta histórica del interlocutor
SFM
texto bíblico
ANTES / ACTUAL
comentarios externos
notas históricas de otros usuarios
```

## 2. Marcadores excluidos

El corrector reconoce como estructura y NO revisa:

```text
COM:
PT:
SUG:
CONT:
IndS:
RES:
```

También excluye:

```text
A)
B)
C)
...
```

y elementos que no son prosa normal, entre ellos:

```text
MRK.8.31
1 Corintios 3:10
\v
\s
DHH
NVI
NTV
XML
SFM
```

Por ejemplo:

```text
SUG: Podrían espresarlo de esta manera.
               ──────────
```

`SUG:` no se revisa. `espresarlo` sí puede aparecer marcado como posible error.

## 3. Interfaz

Junto al selector de marcadores aparece:

```text
[Insertar marcador…] [ABC✓] [Español ▼] [⚙]
```

### ABC✓

Activa o desactiva la revisión mientras se escribe.

### Idioma

Los diccionarios integrados disponibles mediante `pyspellchecker` son:

```text
Español
English
Français
Português
Deutsch
Italiano
Euskara
Nederlands
Русский
العربية
Latviešu
فارسی
```

También aparece:

```text
Diccionario personalizado
```

El idioma elegido se recuerda por proyecto.

## 4. Subrayado

Las palabras que el diccionario considera desconocidas aparecen con subrayado
ortográfico.

El subrayado:

- es únicamente visual;
- no modifica el texto;
- no se escribe en `Notes_*.xml`;
- desaparece cuando se corrige la palabra o se añade a un diccionario.

## 5. Clic derecho

Sobre una palabra marcada puede usar el menú contextual:

```text
sugerencia
sugerir
...
────────────────────────
Agregar «palabra» al diccionario personal
Agregar «palabra» al diccionario del proyecto
Ignorar durante esta sesión
```

Elegir una sugerencia reemplaza solamente la palabra seleccionada.

### Diccionario personal

Acepta la palabra en todos los proyectos.

### Diccionario del proyecto

Acepta la palabra únicamente en el proyecto actual.

Esto resulta útil para:

```text
nombres propios
nombres de pueblos
nombres de lenguas
términos bíblicos
términos técnicos
formas propias del equipo
```

## 6. ⚙ Opciones

El botón de opciones contiene:

```text
Revisar mi nota completa…
Revisar respuesta/seguimiento…
Importar vocabulario al diccionario del proyecto…
Usar lista como diccionario principal…
Restablecer palabras ignoradas en esta sesión
```

## 7. Revisar nota completa

`Revisar mi nota completa…` muestra una tabla:

```text
Palabra        Veces    Sugerencias
────────────────────────────────────────────
sujerencia       2      sugerencia
versiculo        1      versículo
espresarlo       1      expresarlo
```

Los marcadores y referencias se excluyen también de este análisis.

## 8. Vocabulario del proyecto

Puede importar una lista:

```text
namtrik
Yukpa
Cuicateco
...
```

desde un archivo `.txt`.

También acepta la lista base de un archivo `.dic` de Hunspell: ignora la primera
línea numérica y los flags `/ABC`.

En este modo las palabras importadas **complementan** el idioma principal.

Ejemplo:

```text
Idioma principal: Español
Vocabulario del proyecto:
    Yukpa
    wanapsa
    ...
```

## 9. Diccionario personalizado para otra lengua

Si trabaja en una lengua que no tiene un diccionario integrado, use:

```text
⚙
→ Usar lista como diccionario principal…
```

y seleccione un `.txt` o `.dic`.

Consultor App utiliza esa lista como diccionario principal del proyecto.

Esta modalidad realiza comprobación por palabras registradas y sugerencias por
similitud. No interpreta reglas morfológicas de un archivo `.aff` de Hunspell.

Por tanto, para una lengua con morfología productiva es mejor alimentar el
diccionario con las formas válidas necesarias o, en una fase posterior,
incorporar un analizador Hunspell completo para esa lengua.

## 10. Dependencia nueva

La v21 añade:

```text
pyspellchecker>=0.8.2
```

Después de copiar esta versión sobre el proyecto, ejecute una vez:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Luego:

```bash
python3 app.py
```

Si `pyspellchecker` no está instalado, Consultor App no se cierra ni produce un
error fatal: el corrector indica que no tiene diccionario integrado. Los
diccionarios personalizados siguen siendo una alternativa.

## 11. Privacidad

La revisión ortográfica es local.

El contenido de las notas no se envía a un servicio de corrección web ni a una
API externa.

## 12. Persistencia

Consultor App recuerda:

```text
corrector activado/desactivado
idioma del proyecto
palabras del diccionario personal
palabras del diccionario del proyecto
diccionario personalizado del proyecto
```

Las palabras ignoradas mediante `Ignorar durante esta sesión` se olvidan al
cerrar la sesión.

## 13. Funciones anteriores

Se conservan todas las funciones de la v20, incluyendo:

- Notas y Comentarios abiertos;
- historial de referencias ↶ / desplegable / ↷;
- Texto fuente;
- Léxico;
- Referencias;
- Temas;
- Lugares;
- recursos flotantes y multimonitor;
- Modo Revisión;
- notas XML y backups;
- ChatGPT;
- BibleGateway;
- búsqueda y edición de notas;
- detección de cambios externos.

## Ejecución

Primera vez después de actualizar:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Después:

```bash
source .venv/bin/activate
python3 app.py
```


## Corrección v21.1 — diccionario realmente cargado

La v21 permitía que la aplicación continuara funcionando cuando
`pyspellchecker` no estaba instalado, pero ese modo aceptaba todas las palabras
para evitar falsos errores. Como consecuencia, `ABC✓` podía parecer activo
aunque no existiera un diccionario.

La v21.1 corrige ese comportamiento visual:

```text
ES ✓
```

significa que existe un diccionario cargado.

```text
ES !
```

significa que el corrector está activado pero **no existe un diccionario
disponible**.

En ese caso:

```text
⚙
→ Instalar diccionario integrado…
```

instala `pyspellchecker` utilizando el mismo Python/entorno virtual con el que
se está ejecutando Consultor App. Cuando termina, el backend se recarga sin
tener que cerrar la aplicación.

Antes de instalar nada, Consultor App también busca diccionarios del sistema en:

```text
/usr/share/hunspell
/usr/share/myspell
/usr/share/myspell/dicts
/usr/local/share/hunspell
```

Si encuentra, por ejemplo, `es_ES.dic`, lo utiliza automáticamente como
fallback local.

El fallback de un `.dic` del sistema trabaja con la lista de palabras contenida
en el archivo. El backend `pyspellchecker` sigue siendo la opción preferida para
la revisión integrada.
