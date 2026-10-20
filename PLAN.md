# Plan: Ford Transit modelado a mano (subdivisión), sin fotos proyectadas

Objetivo: que el modelo coincida con las 12 capturas en silueta, proporciones y detalle,
con geometría real (no texturas que simulen piezas). La pintura Clerk sigue siendo un atlas
aplicado al panel pintado; todo lo demás es malla.

## 1. Qué se reutiliza de la Crafter (ya extraído o extraíble con `tools/extract_parts.py`)

| Pieza | Estado | Notas |
| --- | --- | --- |
| Ruedas: llanta de acero, neumático, disco, buje (`Crafter_Wheel`) | reutilizar | ya escaladas a 235/65R16; la Transit usa llanta de acero de 16" muy parecida |
| Espejos: carcasa, brazos, cristal (`Crafter_MirrorL/R`) | reutilizar con retoque | la carcasa Transit es más cuadrada; aceptable, o re-esculpir si sobra tiempo |
| Manillas de puerta exteriores | reutilizar | 4 unidades + manilla trasera |
| Bisagras exteriores de las puertas traseras | reutilizar | la Transit las tiene vistas igual |
| Interior (salpicadero, asientos, volante, paneles de puerta) | reutilizar escalado | solo se ve a través del cristal |
| Limpiaparabrisas, antena | reutilizar | mallas pequeñas |
| Carrocería, capó, parrilla, faros, pilotos, parachoques, cristales, techo | **NO** | formas de Crafter; hay que modelar las de Transit |

## 2. Qué hay que modelar de nuevo (por panel, en orden de construcción)

1. **Jaula de carrocería (cage)**: malla base de cuadriláteros (~3-5k quads) con Mirror + SubSurf nivel 2-3.
   Se construye por lofting de curvas maestras medidas en las capturas: perfil lateral, planta
   (estrechamiento de la nariz, techo más estrecho), secciones frontal y trasera. Esta es la
   pieza que define el 90 % del parecido: largo 5.59, ancho 2.03, alto 2.12, batalla 3.30,
   voladizos 1.03/1.26, cintura 1.30, umbral 0.57, caída del capó, pendiente del parabrisas.
2. **Líneas de panel**: los loops de la jaula se colocan sobre las juntas reales (capó, puertas
   delanteras, corredera, puertas traseras, pilares A/B/C). Cada panel se separa por islas de
   caras; Solidify da grosor; Bevel redondea cantos. Así las puertas son piezas de verdad.
3. **Huecos**: parabrisas, ventanas de puerta delantera (con su triángulo fijo), parrilla,
   faros y pilotos se abren como insets/loops en la jaula (no booleanas) para que SubSurf no
   pellizque. Booleanas solo para rejilla inferior, nichos antiniebla y vano de matrícula.
4. **Frontal**: parrilla hexagonal ancha (marco cromado + 3 barras + óvalo Ford), faros
   envolventes (carcasa, dos proyectores redondos, intermitente ámbar, lente clara), capó con
   nervios, parachoques en 3 piezas (negro abajo), cofre inferior con toma de aire.
5. **Trasera**: dos puertas con nervio horizontal, pilotos verticales de dos celdas,
   parachoques negro con escalón, luz de freno alta, matrícula con marco.
6. **Lateral**: nervio de cintura y nervio bajo (la Transit tiene dos líneas de prensado),
   pasos de rueda con moldura, faldón, escalón blanco bajo la puerta, carril de la corredera,
   canalón del techo, nervios del techo.
7. **Bajos**: suelo, ejes, escape, depósito simplificados (se ven en vistas bajas).
8. **Cristales**: con grosor y material vidrio real; el parabrisas con su serigrafía oscura.

## 3. Método y herramientas

* Script único `tools/model_transit.py` (bpy + bmesh, headless con Blender 4.2), paramétrico:
  todas las cotas en un diccionario en metros para poder ajustarlas tras cada comparación.
* Pipeline de modelado tomada de las skills encontradas (vendidas en `references/skills/`, MIT):
  pila de modificadores Mirror → Solidify → Bevel → SubSurf; Bevel siempre antes de SubSurf;
  piezas que se tocan se solapan 5-15 mm; limpiar booleanas (remove doubles, normales);
  nombrar todo; construir por partes con un build_plan (skill `blender-coordinator`).
* Referencias: capturas con chroma eliminado como planos de fondo en el .blend
  (`references/views/*_keyed.png`) y, si se compra, el blueprint vectorial F/T/R/S de
  getoutlines (24 USD, único plano 2015-2019 130" WB Low Roof que existe; no hay gratuito).
* Bucle de control de calidad medible: `render_turntable.py compare` + nueva métrica
  `tools/silhouette_iou.py` que recorta la silueta de cada captura por chroma, renderiza el modelo
  con la misma cámara y calcula IoU de siluetas y superposición de bordes. Meta: IoU > 0.95 en
  las 8 vistas antes de pasar a detalles.
* Pintura: atlas actual (logo oficial, Inter, QR) proyectado solo sobre paneles pintados;
  cristal, cromo, plástico y goma como materiales PBR propios. Sin fotos proyectadas.
* Rig y exportación: sin cambios (mismos nombres de nodos, clips, luces).

## 4. Secuencia de trabajo y entregables

| Fase | Resultado verificable |
| --- | --- |
| A. Curvas maestras + jaula | compare sheet: silueta lateral/frontal/trasera coinciden, IoU > 0.9 |
| B. Paneles y huecos | puertas separadas, ventanas y parrilla abiertas, IoU > 0.95 |
| C. Frontal y trasera en detalle | close-ups de faro, parrilla, piloto frente a capturas |
| D. Lateral, techo, bajos | vistas 3/4 completas |
| E. Piezas Crafter integradas + interior | puertas abren mostrando interior |
| F. Materiales, livery, rig, export | web/Godot/Blender verificados, turntable |

## 5. Decisiones que necesito

1. Comprar el blueprint de getoutlines (24 USD, vectorial, 4 vistas): recomendado; sin él trabajo
   con las capturas y las cotas publicadas (más iteraciones).
2. Entorno: seguir headless (Blender en background, yo renderizo y comparo) — recomendado —
   o instalar el plugin `claude-3d-harness` + blender-mcp, que exige Blender abierto en pantalla.
3. Tope de polígonos del entregable (propuesta: jaula ~5k quads, SubSurf 2 → ~80-120k caras
   en el GLB; versión alta con SubSurf 3 para renders).
