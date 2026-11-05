# Investigación del JX-05 en Windows — 5 de noviembre de 2026

## Conclusión

La captura contiene una anomalía reproducible en la lectura larga del descriptor
HID. Es una explicación plausible del fallo de inicio, no una prueba definitiva
de su causa interna. Bluepad32 proporciona un antecedente para interpretar los
botones, pero el issue aportado no describe una solución al fallo de conexión en
Windows. Todavía no existe en este proyecto un controlador Windows funcional.

Las pruebas posteriores en el PC confirman que una sesión GATT puede mantenerse
activa durante 60 segundos, pero Windows devuelve `DENIED_BY_SYSTEM` al solicitar
acceso al servicio HID `1812`. El controlador HID sigue mostrando código 10.
Son tres resultados distintos: conexión GATT posible, acceso HID denegado y
controlador HID que no inicia. La ruta WinRT probada no permite recibir informes
HID en estas condiciones. No se ha demostrado que reemplazar el controlador
elimine la denegación.

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
| Aplicación que reciba informes por GATT | La sesión GATT se mantuvo activa durante 60 segundos | Acceso al servicio HID denegado con `DENIED_BY_SYSTEM`; no se llegó a enumerar características ni a suscribir Report |
| Controlador específico de Windows | Podría reemplazar o adaptar el transporte y suministrar una descripción válida | Requiere acceso documentado al transporte, implementación WDK, firma y pruebas en Windows. Un filtro que solo cambie teclas no corrige esta etapa |
| Puente receptor con pila Bluetooth propia | Evitaría la inicialización HID Bluetooth de Windows | Fuera del alcance acordado: el usuario no dispone de hardware adicional |
| Corrección del firmware del anillo | Podría resolver la respuesta ATT incorrecta si nace allí | Fuera del alcance acordado: no modificar el firmware del anillo |

## Experimentos realizados para una solución directa en Windows

Antes de escribir un controlador de kernel, comprobar si una aplicación puede
abrir el servicio HID `0x1812` y suscribirse a las características Report `0x2A4D`
del dispositivo emparejado mediante las API documentadas. Registrar explícitamente
si devuelve AccessDenied, si se reciben notificaciones y si Windows cierra la
conexión. La prueba de suscripción se intentó, pero falló antes de abrir GATT:
Windows no entregó el objeto del dispositivo. Ese resultado no demuestra una
denegación de acceso al servicio HID.

### Prueba posterior de sesión GATT en Windows

`tools/probe_gatt_session.py` recibió un anuncio del anillo con dirección de tipo
`PUBLIC`, abrió `BluetoothLEDevice` y solicitó `GattSession.MaintainConnection`.
La sesión pasó de `CLOSED` a `ACTIVE`, pero volvió a `CLOSED` tras **10,593
segundos**, antes de completar la medición prevista de 60 segundos. El evento de
cierre indicó error GATT 0; ese valor no explica el motivo del cierre. No se
solicitó leer Report Map ni suscribir informes. La consulta posterior no encontró
eventos Kernel-PnP/Configuration de los últimos cinco minutos ni nodos presentes
del anillo. No se puede atribuir este cierre concreto al error HID solo con esos
datos. La sesión se liberó al terminar la prueba.

En un segundo intento, después de que el usuario indicara que el anillo estaba
listo, la sesión permaneció `ACTIVE` durante **60 segundos completos** y el
programa terminó con `SESION_ESTABLE` (código 0). Al terminar liberó la sesión
deliberadamente. Esto demuestra que una sesión GATT puede mantenerse durante
ese intervalo en este PC; no confirma acceso al servicio HID ni corrige su
descriptor. Los dos intentos impiden concluir que el cierre sea inevitable.

### Acceso al servicio HID desde la sesión activa

Prueba ejecutada por el usuario:

```powershell
& "C:\ProgramData\anaconda3\python.exe" tools/probe_gatt_session.py --address B7:FC:01:C6:F3:7E --check-hid
```

Salida relevante, conservada literalmente:

```text
ANUNCIO: direccion=B7FC01C6F37E tipo=PUBLIC
DISPOSITIVO: JX-05 enlace=DISCONNECTED
ESTADO_SESION: CLOSED error=inicial
ESTADO_SESION: ACTIVE error=0
CONSULTANDO_HID: servicio 1812, sin leer valores de caracteristicas.
DESCUBRIMIENTO_HID: SUCCESS protocolo=None
ACCESO_HID: DENIED_BY_SYSTEM
```

`DISCONNECTED` corresponde al estado anterior a activar la sesión. El
descubrimiento del servicio terminó correctamente; `RequestAccessAsync` devolvió
la denegación. No se enumeraron características ni se solicitaron valores o
notificaciones. Esta denegación no es un fallo de detección del anillo ni prueba
que el anillo rechace las notificaciones: Windows impidió llegar a esa etapa.
Tampoco demuestra que ejecutar como administrador o reemplazar el controlador
vaya a conceder acceso. El aviso de obsolescencia de la API es independiente:
la apertura del dispositivo y la activación de sesión sí funcionaron.

### Estado del controlador y prueba de deshabilitación

Consultas PnP posteriores confirmaron `hidbthle.inf`, código de problema 10 y
estado `0xC00000E5`. El servicio usa, entre otros, el identificador:

```text
BTHLEDevice\{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&0105ac_PID&0220_REV&0110
```

Se intentó deshabilitar únicamente su instancia HID. La orden devolvió un error
genérico, aunque una consulta inmediata mostró `CM_PROB_DISABLED`. Después esa
instancia desapareció y Windows creó otra. No se obtuvo una prueba controlada
de conexión estable con HID deshabilitado. No presentar ese intento como una
solución ni como prueba de que deshabilitarlo sea inútil. No se sustituyó el
controlador del adaptador Bluetooth.

## Pasos siguientes, con el PC y el anillo actuales

### Resultado de la investigación del paso 1

Se encontró una API pública adicional a WinRT: las funciones nativas Win32
`BluetoothGATTGetServices`, `BluetoothGATTGetCharacteristics` y
`BluetoothGATTRegisterEvent`. Aceptan handles de dispositivo o servicio según la
operación y permiten enumerar GATT y registrar callbacks. El encabezado público
`bluetoothleapis.h` declara expresamente entorno **User mode**; la implementación
se importa de `BluetoothApis.dll`. Por tanto, estas funciones no son una DDI de
kernel ni justifican por sí solas un controlador KMDF. La palabra «profile drivers»
en sus comentarios no demuestra lo contrario.

La referencia oficial define dos clases de interfaz que permiten localizar los
endpoints nativos:

| Interfaz | GUID |
| --- | --- |
| Dispositivo Bluetooth LE | `781aee18-7733-4ce4-add0-91f41c67b592` |
| Servicio GATT | `6e3bb679-4372-40c8-9eaa-4509df260cd8` |

Una consulta exploratoria con `CM_Get_Device_Interface_ListW`, limitada a
interfaces presentes y filtrada por la dirección del anillo, devolvió cero
interfaces de ambas clases. No había una sesión GATT mantenida por esa consulta;
el resultado no demuestra denegación de acceso nativo ni ausencia permanente de
interfaz. Aún no se ha obtenido un handle ni invocado `BluetoothGATTGetCharacteristics`
para el HID del anillo mediante esa ruta.

**Decisión:** antes de instalar WDK o sustituir controladores, preparar una prueba
nativa que mantenga la sesión GATT ya verificada, enumere las interfaces y abra
solo la del JX-05 mediante `CreateFileW`. Consultar servicios y características
con `BluetoothGATT*`, registrando errores Win32/HRESULT por etapa. No leer Report
Map ni escribir valores para comprobar inicialmente el acceso. Si no existe un
endpoint de servicio utilizable, comprobar la alternativa documentada de handle
del dispositivo y estructura de servicio devuelta por la API; no inventar handles
de atributo a partir de la captura.

La API nativa también puede estar restringida: la documentación consultada no
garantiza acceso al servicio HID reservado ni una excepción a `DENIED_BY_SYSTEM`.
Si falla, conservar el código concreto y distinguir apertura, enumeración y acceso.
No interpretar automáticamente un error como motivo para instalar un driver.

La revisión de las interfaces y muestras públicas de Microsoft no identificó una
DDI de kernel documentada y verificada que permita a nuestro reemplazo del HID
recibir ATT crudo de este periférico LE. Las muestras Echo L2CAP y las interfaces
BRB/SDP no prueban esa capacidad. Esto deja la sustitución del controlador como
**viabilidad pendiente**, no como siguiente implementación ya autorizada por la
evidencia. No se ha demostrado que un INF genérico o un filtro de teclas resuelva
la inicialización.

Fuentes primarias revisadas:

- [Referencia Bluetooth: GUID de interfaces](https://learn.microsoft.com/en-us/windows/win32/api/_bltooth/).
- [BluetoothGATTGetServices](https://learn.microsoft.com/en-us/windows/win32/api/bluetoothleapis/nf-bluetoothleapis-bluetoothgattgetservices).
- [BluetoothGATTGetCharacteristics](https://learn.microsoft.com/en-us/windows/win32/api/bluetoothleapis/nf-bluetoothleapis-bluetoothgattgetcharacteristics).
- [BluetoothGATTRegisterEvent](https://learn.microsoft.com/en-us/windows/win32/api/bluetoothleapis/nf-bluetoothleapis-bluetoothgattregisterevent).
- [Encabezado público de Microsoft: bluetoothleapis.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/bluetoothleapis.h).
- [Muestras de controladores Bluetooth de Microsoft](https://github.com/MicrosoftDocs/windows-driver-docs/blob/staging/windows-driver-docs-pr/samples/bluetooth-driver-samples.md).

### Secuencia de trabajo

1. Probar la API nativa `BluetoothGATT*` con la sesión GATT activa, según el
   resultado de investigación anterior. Si tampoco permite acceso, investigar una
   DDI o ejemplo documentado para el reemplazo específico del servicio HID.
   La existencia de dispositivos PnP por servicio no garantiza acceso al transporte
   ni elimina la restricción WinRT. Resolver esa viabilidad antes de instalar WDK.
2. Si existe esa vía, definir una prueba mínima: abrir el servicio y registrar
   informes originales, sin mapear teclas ni asumir que el prefijo recuperado sea
   el descriptor completo. Si no existe evidencia suficiente, documentar el
   bloqueo y no fabricar un INF que prometa resolverlo.
3. Antes de instalar un prototipo, preparar su coincidencia de identificadores,
   procedimiento de firma y recuperación del controlador original. El identificador
   de hardware anterior puede coincidir con otros ejemplares iguales; no equivale
   a la dirección de un único anillo. Resolver ese alcance antes de instalar.
4. Solo tras demostrar el acceso, preparar las herramientas de compilación y un
   prototipo con instalación y reversión revisables. Comprobar arranque, conexión
   sostenida y recepción de informes en el PC real. No desactivar globalmente
   Bluetooth ni sustituir el controlador del adaptador para esta prueba.
5. Únicamente con informes reales recibidos, capturar cada botón y desarrollar
   su traducción a acciones de PowerPoint.

No repetir indefinidamente el mismo `--check-hid`: ya documentó la denegación en
esta configuración. Quedan excluidos firmware del anillo y hardware adicional.
No hay todavía un paquete de controlador instalable ni una solución funcional.

### Referencias de arquitectura

- [Microsoft: Bluetooth LE overview](https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/bluetooth-low-energy-overview): representación del dispositivo y servicios primarios mediante objetos de dispositivo.
- [Microsoft: Bluetooth GATT Client](https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-client): API GATT y solicitud de mantenimiento de conexión; no ofrece acceso al transporte crudo.
- [Microsoft: Bluetooth driver stack](https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/bluetooth-driver-stack): BthLEEnum implementa ATT/GATT. No extrapolar las interfaces de Bluetooth clásico como prueba de acceso LE.

Estas referencias fundamentan la investigación de arquitectura; no documentan
una corrección específica para este JX-05 ni garantizan un reemplazo viable.

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
