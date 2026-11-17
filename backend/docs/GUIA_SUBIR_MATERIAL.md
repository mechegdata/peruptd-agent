# Guía: subir fotos, renders, videos y fichas para que el bot los envíe

El bot busca el material **solo**, por el nombre de las carpetas y de los archivos. No hay que tocar código, ni SQL, ni variables.
Cada archivo nuevo lo empieza a usar como máximo **10 minutos** después de subirlo.

## 1. Organízalo como te sea cómodo — solo respeta 3 reglas

El bot recorre **todo el bucket `recursos`** (todas las carpetas) y entiende los nombres que uses. Solo necesita:

1. **De qué casa es:** que la carpeta o el archivo diga `Casa 1` / `Casa 2` (también entiende `casa1`, `CASA-2`, `c1`, `primera`…).
   Si no dice casa, lo toma como de **las dos** (comparten diseño).
2. **Si tiene muebles que no se entregan:** que la carpeta o el archivo diga `render`, `amoblado`, `muebles` o `3d`.
   Así el bot le agrega "Muebles de referencia: la casa se entrega sin muebles". Lo demás lo presenta como **foto real**.
   La carpeta manda: todo lo que está en una carpeta `fotos` es **foto real**; lo que está en `renders`, **render con muebles**.
3. **Qué ambiente es:** ponlo en el nombre del archivo (`sala`, `comedor`, `cocina`, `dormitorio`/`habitación`/`cuarto`, `baño`,
   `terraza`/`azotea`, `cochera`/`garaje`, `fachada`/`frontis`, `jardín`/`patio`, `lavandería`, `escalera`).
   Si el nombre es otro (`segundo piso.jpg`, `cuarto niños.png`), el bot usa ese mismo nombre como leyenda.
   Los archivos tipo `IMG_2034.jpg` también se envían, pero con una leyenda genérica.

Ejemplo válido (cualquier parecido también sirve):
```
recursos/
└── Proyecto Santa Teresa/
    ├── Casa 1/                 fachada.jpg · dormitorio principal.jpg · Recorrido casa 1.mp4 · Ficha tecnica.pdf
    ├── Casa 2/                 frontis.jpg · baño visitas.jpg · video casa 2.mp4
    └── Renders con muebles/    sala comedor.png · dormitorio.png · terraza parrilla.png
```

> Los renders de cocina están en `santa-teresa/comun/renders/`: `cocina_1.jpg` = Madera Rovere y `cocina_2.jpg` = Gris Grafito. No les cambies el nombre.
> Si alguno falla, el bot busca un render de cocina en las carpetas con `gris`/`grafito` o `madera`/`rovere` en el nombre.

## 2. Formatos que acepta WhatsApp

- **Fotos y renders:** `.jpg` o `.png`. Las del iPhone (`.heic`) no sirven: expórtalas como JPG.
- **Videos:** `.mp4` de **16 MB como máximo** (≈ 1 minuto en 720p). Los `.mov` no sirven.
- **Fichas:** `.pdf` (o una imagen con "ficha" o "plano" en el nombre).

## 3. Sube los archivos

Entra a la carpeta, toca **Upload files** y arrastra los archivos. Listo.

## 4. Verifica que el bot los ve

Abre en tu navegador esta dirección, con tus datos:

```
https://<dirección-de-tu-sague-bot-en-cloud-run>/diagnostico/material?key=<tu VERIFY_TOKEN>
```

- La dirección es la misma que pusiste en el webhook de Meta, pero sin `/webhook`.
- `VERIFY_TOKEN` es la clave que usaste para verificar ese webhook.

La página muestra:
- **`resumen`**: cuántos archivos encontró por casa y tipo (ej. `casa_2 · foto_real: 5`).
- **`archivos`**: cada archivo y cómo lo entendió (casa, tipo, ambiente y la leyenda que usará).
- **`avisos`**: archivos que el bot no va a usar y por qué (por ejemplo, un video muy pesado o una foto `.heic`).

**Si sale `"total": 0`:**
1. Revisa que los archivos estén dentro de alguna carpeta del bucket `recursos` (no sueltos en la raíz).
2. Si lo están, falta darle permiso al bot para listar el bucket. En Supabase entra a **SQL Editor**, pega esto y toca **Run**:
   ```sql
   create policy "bot puede listar recursos" on storage.objects for select using (bucket_id = 'recursos');
   ```

## 5. ¿Cuándo manda el bot cada cosa?

| Momento | Qué manda |
|---|---|
| Primer mensaje a quien llenó el formulario | Planos, el diseño de cocina que eligió y **1 render amoblado** (la sala) |
| Pide información o precio | Fachada + sala amoblada |
| Pide los planos | Planos + 1 render amoblado que aún no haya visto |
| Pregunta cuántos dormitorios / distribución | Planos + dormitorio + terraza |
| "¿Viene amoblada?" / "¿cómo se ve por dentro?" | Hasta 3 renders amoblados |
| "Está muy caro" | Terraza + cochera / jardín ("lo que un depa no te da") |
| "Lo converso con mi esposo / familia" | 2 renders amoblados, "para que se la muestres" |
| Pide fotos | 8 mezcladas (Casa 1, Casa 2 y renders), dice cuántas quedan y pregunta "¿te gustaría ver el recorrido en video?" (o los planos) |
| "¿Tienes más fotos?" / "¿y de la casa 2?" | Las siguientes que no ha visto (o las de esa casa) |
| Pide videos ("las dos casas para mi familia") | 1 video por casa |
| Pregunta la ubicación | Fachada |
| Cita confirmada | Fachada ("para que la reconozcas al llegar") |
| Te dejó en visto (dentro de las 24 h) | 1 imagen que no haya visto |
| 45 min después de la visita | Planos, cocinas y 2 renders amoblados, "para que la vean en familia" |
| No vino a la visita | 1 render amoblado junto con la invitación a reprogramar |
| Día 5 después de la visita | 1 imagen (sala / terraza) |

El bot nunca manda dos veces la misma imagen, salvo que el cliente la pida o que tenga sentido repetirla (para mostrársela a la familia, después de la visita).
