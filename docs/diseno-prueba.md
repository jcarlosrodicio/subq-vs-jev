# Diseño de la prueba: SubQ Snap vs Jev

Documento de trabajo. Se congela antes de la ejecución completa; si algo cambia después del piloto, se anota aquí con el motivo.

## Qué queremos responder

1. **¿Importa el contexto largo?** SubQ admite unos 384K tokens; Jev rechaza a partir de unos 32.7K (`max_tokens_exceeded`, medido el 2026-10-10). ¿Mantiene SubQ el acierto al crecer el contexto? ¿Y basta con trocear el texto para Jev?
2. **¿Quién acierta más en igualdad de condiciones?** Hasta 30K, los dos reciben exactamente el mismo payload.
3. **¿Son de fiar sus probabilidades?** Los dos venden "confianza calibrada": cuando dicen 0.8, ¿aciertan el 80 % de las veces?
4. **¿Son robustos?** ¿Cambian de respuesta si se barajan las opciones, se reformula la pregunta o se niega?

## Los datos: el registro de una tienda inventada

Una tienda online ficticia, **Kettle & Co.**, genera un registro de eventos en texto plano, en inglés, con semilla fija. Una línea por evento:

```
2026-03-04 10:12  ORDER_PLACED    order=#48213 customer=C-0412 warehouse=Leeds total=€84.20
2026-03-05 08:40  SHIPPED         order=#48213 warehouse=Leeds
2026-03-19 17:02  RETURNED        order=#48213 reason=damaged
2026-03-21 09:15  REFUND          order=#48213 amount=€84.20
2026-04-02 11:30  ACCOUNT_CLOSED  customer=C-0412
2026-04-03 12:00  TICKET          customer=C-0412 severity=critical topic=billing
```

Son datos inventados de principio a fin: ningún modelo los ha visto al entrenar, y la respuesta correcta la calcula el código que genera el registro.

## Las preguntas (prueba A)

Seis familias, de menos a más difícil. Cada registro lleva 2 preguntas de cada familia (12 en total), enviadas en una sola llamada. Las dos APIs evalúan cada pregunta por separado.

| Id | Familia | Tipo | Ejemplo | Qué exige |
|---|---|---|---|---|
| L1 | Buscar | noul | Was order #48213 returned? | Encontrar una línea |
| L2 | Buscar | choice (5 almacenes) | Which warehouse shipped order #48213? | Encontrar una línea y leer un campo |
| X1 | Cruzar | noul | Did customer C-0412 place an order after closing their account? | Relacionar dos eventos alejados |
| X2 | Cruzar | noul | Was order #48213 refunded a different amount than was paid? | Comparar números en dos líneas |
| A1 | Agregar | choice (5 almacenes) | Which warehouse had the most returns? | Contar en todo el registro (el ganador saca al menos un 50 % de ventaja al segundo) |
| A2 | Agregar | score (None / One / Two or three / Four or more) | How many critical tickets did customer C-0412 open? | Contar y ordenar en una escala |

Reglas de generación:
- Las preguntas de sí o no salen al 50 % sí y al 50 % no.
- En L1, L2, X1 y X2, la línea clave se coloca al 10 %, al 50 % o al 90 % del registro, para detectar si el modelo pierde lo que está en el medio.
- Los textos de las preguntas son neutros y no se ajustan para ninguno de los dos modelos.

**Longitudes:** 2K, 8K, 16K, 30K (los dos modelos), y 64K, 128K, 256K y 360K (solo SubQ).
**Volumen:** 10 registros por longitud, 120 preguntas por longitud y modelo. En total, unas 960 respuestas de SubQ y 480 de Jev.

### Jev troceado (contexto largo sin ventana larga)

A partir de 64K, el registro se parte en trozos de 30K y se le pregunta a Jev por cada trozo:
- **L1 y X2:** se toma el máximo, porque basta con que un trozo diga "sí".
- **L2:** se toma la respuesta del trozo con más confianza.
- **X1, A1 y A2:** no se pueden combinar bien, porque la información queda repartida entre trozos. Se ejecuta igual y se marca como "estructuralmente en desventaja".

Esto responde a la pregunta que se hará todo el mundo: *¿para qué quiero 384K si puedo trocear?*

## Robustez (prueba C)

Con registros de 8K (entran los dos modelos), los mismos 10 registros:

| Id | Prueba | Métrica |
|---|---|---|
| C1 | Barajar el orden de las opciones (3 permutaciones) en L2 y A1 | % de respuestas que cambian |
| C2 | Reformular la instrucción (3 redacciones) en las preguntas de sí o no | % que cruzan 0.5 y dispersión de la probabilidad |
| C3 | Negación: "Was X returned?" frente a "Was X NOT returned?" | \|p + p_neg − 1\| (0 = coherente) |
| C4 | Repetir la misma petición 3 veces | ¿Respuesta idéntica? (determinismo) |

## Métricas

- **Acierto:** sí o no con umbral 0.5, la opción más probable en choice, el nivel exacto en score (más el error medio en niveles). Con intervalo de confianza del 95 %.
- **Calibración:** Brier score, ECE y diagrama de fiabilidad.
- **Cobertura:** % de preguntas que el modelo puede contestar (límite de contexto).
- **Latencia:** p50 y p95 por longitud.
- **Coste:** por cada 1.000 decisiones, a partir de los tokens que devuelve cada API y el precio público.

## Reglas de juego limpio

- El payload es idéntico, byte a byte, para los dos modelos. Se guarda la versión exacta que devuelve cada API (`jev-1.13.0`, `subq-snap-preview`) y la fecha.
- Las peticiones van una a una, desde la misma máquina y la misma red, **alternando qué modelo va primero**.
- Los errores (429, 5xx) se reintentan como máximo 3 veces con espera creciente. Los fallos definitivos se publican, no se esconden.
- Todo va al repo: el generador, el ejecutor, las respuestas en bruto (JSONL) y los resultados. Se reproduce con un solo comando.
- **Piloto primero:** 1 registro por longitud, solo para comprobar que las respuestas correctas lo son y que la prueba no es ni trivial ni imposible. Después se congela este documento y se lanza la prueba completa.
- Aviso en la web: acceso gratuito de SubQ durante la preview; sin relación con ninguna de las dos empresas; sin logos.

## Riesgos y decisiones abiertas

- **Precio de salida de Jev:** devuelve tokens de salida (21 en la prueba) pero no he encontrado su precio publicado. SubQ no cobra la salida.
- **Latencias:** se miden desde España. Se publican como medidas por mí, no como absolutas.
- **SubQ es una preview:** el modelo puede cambiar. Los resultados llevan fecha.

## Cambios tras el piloto (2026-10-10) — diseño congelado

- **Calibración de tokens:** los registros ocupan unos 1.72 caracteres por token, no 2.9. Con la estimación inicial, el registro de "30K" medía 48K y Jev lo rechazaba; el de "360K" medía unos 610K y SubQ respondía `internal_error` en lugar de un error de límite. Se fija `CHARS_PER_TOKEN = 1.70`; ahora "30K" son 28.8K tokens y "360K" son 335K.
- **Motivos de devolución sin espacios** (`wrong-size`), porque rompían el formato `clave=valor`. Lo detectó la prueba de verdad.
- **Dificultad:** hasta 16K los dos modelos aciertan casi todo. No se endurece la prueba después de ver los resultados, para no ajustarla a favor o en contra de ninguno. Las diferencias aparecen al crecer el contexto.
