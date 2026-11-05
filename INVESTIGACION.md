# Investigación del JX-05 en Windows — 5 de noviembre de 2026

## Conclusión

La captura contiene una anomalía reproducible en la lectura larga del descriptor
HID. Es una explicación plausible del fallo de inicio, no una prueba definitiva
de su causa interna. Bluepad32 proporciona un antecedente para interpretar los
botones, pero el issue aportado no describe una solución al fallo de conexión en
Windows. Todavía no existe en este proyecto un controlador Windows funcional.

## Evidencia de la captura del usuario

Fuente: `jx05-amplio.xml`, convertido con tracerpt del ETL del usuario. Horas en
UTC−03:00. La conexión identificada con el anillo usa el handle HCI `0x0200`.

1. A las 10:15:24.385 se establece la conexión Bluetooth.
2. Windows solicita ATT MTU 527 (`02 0f 02`). El periférico responde MTU 64
   (`03 40 00`). El límite efectivo es 64 bytes por mensaje ATT.
3. La enumeración identifica la característica Report Map, UUID `0x2A4B`, en
   el handle de atributo `0x0042`. No confundir este handle con el de conexión.
4. Primera secuencia de lectura:

   | Hora inicial de la respuesta | Desplazamiento solicitado | Bytes ATT | Bytes de valor |
   | --- | ---: | ---: | ---: |
   | 10:15:28.231 | 0 | 64 | 63 |
   | 10:15:28.259 | 63 | 64 | 63 |
   | 10:15:28.286 | 126 | 127 | 126 |

   La tercera respuesta excede el MTU. Repite parte del bloque previo y contiene
   bytes adicionales. Se observan siete secuencias con este mismo patrón, hasta
   las 10:15:34.425. No se deben concatenar esos bytes y tratarlos como un
   descriptor válido.
5. A las 10:15:37.454 el host envía HCI Disconnect para `0x0200`. A las
   10:15:37.651 se recibe Disconnection Complete, razón `0x16`, conexión terminada
   por el host local. Esto identifica quién pidió cerrar la conexión, no su
   motivo interno.
6. El primer registro, de otro intento a las 09:58, contiene Kernel-PnP 411,
   `hidbthle.inf`, `mshidumdf`, problema `0xA` y estado `0xC00000E5`. No se deben
   presentar ambos intentos como una única línea temporal.

### Límites de la evidencia

La fragmentación ACL se reensambló antes de contar bytes ATT. Los siete mensajes
excesivos no son simplemente varios fragmentos interpretados como uno sin tener
en cuenta L2CAP: su longitud L2CAP declarada y el total reensamblado coinciden.
El analizador excluye 14 paquetes ACL cortos o redactados y no exporta material
SMP de emparejamiento. La captura no demuestra la línea de firmware responsable,
ni descarta por sí sola un defecto de otra capa o de instrumentación.

Los 126 bytes anteriores a la anomalía forman un prefijo sintácticamente cerrado
con colecciones Consumer Control (Report ID 3) y Touch Screen (Report ID 1).
El informe táctil describe tres indicadores de un bit, identificador de contacto
de cinco bits y coordenadas X/Y de doce bits cada una: cuatro bytes de carga útil.
No se afirma que ese prefijo sea todo el descriptor pretendido por el fabricante.
Hay además referencias GATT a otros IDs de informe; no se dispone de pulsaciones
capturadas para verificar qué informes utiliza realmente cada botón.

## Qué aporta el issue de Bluepad32

Fuente: texto aportado por el usuario de
https://github.com/ricardoquesada/bluepad32/issues/68.

El autor describe que convirtió secuencias táctiles en flechas y espacio, con
soporte añadido en el commit `b3a0dd1` el 2 de marzo de 2024. El dispositivo del
issue ya se conectaba: su problema era interpretar los botones. El texto no
documenta una corrección de lecturas ATT largas, una solución para Windows, ni
un firmware modificado del anillo.

El ejemplo usa VID `05ac`, PID `022c`; el dispositivo del usuario anuncia VID
`05ac`, PID `0220`. Sus ejemplos incluyen paquetes táctiles de nueve bytes con
ID 2. El prefijo recuperado del usuario tiene otro formato. Es útil reutilizar el
concepto de reconocer un gesto completo y emitir una única acción, pero no copiar
offsets ni tamaños de paquetes sin comprobarlos. Estos identificadores tampoco
prueban que el fabricante real sea Apple.

La descarga del código actual de Bluepad32 no fue posible: el proxy del entorno
rechaza la conexión en el puerto 8080. La lectura directa del commit y la
verificación de documentación actual de Microsoft permanecen pendientes.

## Evaluación de soluciones

| Alternativa | Qué puede resolver | Obstáculo pendiente |
| --- | --- | --- |
| Remapeador de teclado o Raw Input | Traducir eventos ya entregados por Windows | No evita el fallo al iniciar el transporte HID |
| Aplicación que reciba informes por GATT | Podría suscribirse a Report y traducir gestos sin leer Report Map | Windows puede reservar/restringir el servicio HID; hay que comprobar acceso real. No se promete que WinRT/Bleak lo permita |
| Controlador específico de Windows | Podría reemplazar o adaptar el transporte y suministrar una descripción válida | Requiere acceso documentado al transporte, implementación WDK, firma y pruebas en Windows. Un filtro que solo cambie teclas no corrige esta etapa |
| Puente receptor con pila Bluetooth propia | Evita la inicialización HID de Windows y entrega teclado USB al PC | Requiere hardware compatible y firmware de puente. El issue no entrega por sí solo un adaptador USB completo |
| Corrección del firmware del anillo | Resolvería la respuesta ATT incorrecta si nace allí | No hay imagen, código ni método de actualización verificado para este ejemplar |

## Siguiente experimento para una solución directa en Windows

Antes de escribir un controlador de kernel, comprobar si una aplicación puede
abrir el servicio HID `0x1812` y suscribirse a las características Report `0x2A4D`
del dispositivo emparejado mediante las API documentadas. Registrar explícitamente
si devuelve AccessDenied, si se reciben notificaciones y si Windows cierra la
conexión. Este experimento aún no se ha ejecutado y requiere el PC y el anillo.

Si existe acceso, desarrollar un receptor que registre y aprenda los informes,
reconozca un gesto y produzca una acción por pulsación para PowerPoint. Si el
servicio está reservado o la conexión se cierra, descartar ese enfoque: antes de
prometer un driver hay que verificar una interfaz de transporte accesible y las
posibilidades de reemplazar el controlador específico de ese dispositivo. No
desactivar globalmente Bluetooth ni sustituir el controlador del adaptador.

## Reproducir el análisis sin nuevas capturas

Desde la raíz del repositorio, con Python 3.9 o posterior:

```sh
python tools/analyze_att.py /ruta/jx05-amplio.xml --handle 0x200
python -m unittest discover -s tests -v
```

El handle es propio de esta conexión; no debe reutilizarse automáticamente para
otro archivo. El analizador deriva el atributo Report Map de la enumeración GATT.
Verificación realizada: tres pruebas de reensamblado correctas; el archivo real
produce MTU 64, atributo 0x42, prefijo de 126 bytes, 21 respuestas de lectura del
mapa y siete respuestas que exceden el MTU. Esto valida el análisis local, no un
driver ni el funcionamiento del anillo en Windows.
