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

### Resultado real de la prueba nativa con sesión activa

Comando ejecutado en el PC:

```powershell
& "C:\ProgramData\anaconda3\python.exe" tools/probe_gatt_session.py --address B7:FC:01:C6:F3:7E --native-hid
```

La sesión llegó a `ACTIVE`. La API de Configuration Manager encontró una interfaz
del dispositivo LE del anillo y ninguna interfaz de servicio HID de la clase
consultada. `CreateFileW` abrió el dispositivo con acceso de lectura. A través de
ese handle, `BluetoothGATTGetServices` devolvió siete servicios, incluido HID, y
`BluetoothGATTGetCharacteristics` devolvió doce características del servicio HID.
Ambas consultas finales terminaron con `HRESULT=0x00000000`. Las consultas previas
de tamaño devolvieron `0x800700EA`, el resultado esperado para solicitar buffers.

Los Report `2A4D` con `IsNotifiable=1` tienen handles de valor `0x0027`, `0x002B`,
`0x0032`, `0x0036`, `0x003A` y `0x003E`. También se enumeró Report Map `2A4B`,
handle de valor `0x0042`, sin leer su contenido. El programa terminó con
`HID_NATIVO_ENUMERADO` y liberó sus handles y sesión. Las 13 pruebas automatizadas
pasaron, incluida la comprobación de tamaños y offsets de las estructuras nativas.

**Alcance:** Win32 permite abrir el dispositivo y enumerar los metadatos HID en
esta configuración, aunque WinRT deniegue `RequestAccessAsync`. La enumeración
puede utilizar la caché de Windows; no demuestra transferencia actual de informes
ni que se pueda habilitar el CCCD o registrar callbacks. Aún no se llamó a
`BluetoothGATTRegisterEvent` ni se escribieron descriptores. La ausencia de una
interfaz de servicio es relevante: la documentación de registro de eventos pide
un handle de servicio; comprobar ese requisito antes de prometer recepción usando
solo el handle del dispositivo. No hay motivo demostrado para reemplazar el
controlador antes de resolver esa prueba.

Para repetir esta enumeración se añadió `--native-hid` al diagnóstico existente.
No instala controladores, no lee valores y no habilita notificaciones.

### Prueba de registro de notificaciones nativas

Se ejecutó `tools/probe_gatt_session.py --address B7:FC:01:C6:F3:7E
--native-register`. Con la sesión `ACTIVE`, `CreateFileW` abrió la interfaz del
dispositivo con lectura y escritura; la enumeración de los siete servicios y las
doce características HID volvió a funcionar. Se pasaron a
`BluetoothGATTRegisterEvent` las estructuras originales de los seis Report con
notificaciones, una por registro. Los seis devolvieron **`0x80070001`
(HRESULT_FROM_WIN32(ERROR_INVALID_FUNCTION))**. No se aceptó ningún callback.

No apareció una interfaz de servicio HID ni bajo la clase genérica de servicios
GATT ni bajo el UUID `1812` usado como clase de interfaz. Se probó por tanto el
handle del dispositivo, aunque la documentación de registro requiere uno de
servicio. Este resultado demuestra que ese handle no permite el registro en esta
configuración; no demuestra que el periférico rechace notificaciones.

No se escribieron CCCD ni otros atributos: no hubo una suscripción habilitada,
ni escucha de botones. El diagnóstico nuevo verifica únicamente la precondición
de registro y libera inmediatamente cualquier registro que pudiera aceptar una
configuración distinta. Pasaron 14 pruebas automatizadas, incluida la estructura
de registro y el manejo de un registro rechazado.

El siguiente bloqueo concreto es obtener una interfaz de servicio HID utilizable
sin depender de su inicio fallido, o documentar un transporte alternativo. Repetir
el registro con el mismo handle no lo resuelve. No se ha validado un reemplazo
de controlador que proporcione esa interfaz.

### Secuencia de trabajo actualizada

La inspección de los INF instalados aporta una hipótesis concreta para la siguiente
prueba. `C:\Windows\INF\bthleenum.inf` (10.0.26100.9711) asigna el identificador
compatible `BTHLEDevice\GenericATTService` a `AttGenericService`, que incluye
`umpass.inf`. El servicio HID del anillo ya informó ese identificador compatible.
`C:\Windows\INF\hidbthle.inf` (10.0.26100.9549) asigna el UUID `1812` al
controlador HID que falla. `umpass.inf` describe el controlador Microsoft UmPass
y las secciones que otros INF deben incluir; no contiene por sí mismo una
promesa de acceso a HID ni una corrección para este periférico.

**Prueba candidata:** comprobar si Windows ofrece el controlador genérico ATT
ya instalado como alternativa compatible para la instancia del servicio HID del
JX-05. Si la selección por instancia y la reversión a `hidbthle.inf` están
verificadas, cambiar solo esa asociación temporalmente y repetir la búsqueda de
interfaz de servicio y registro de callbacks. La hipótesis es evitar el inicio de
HidOverGatt y obtener el acceso genérico. Que exista el identificador compatible
no garantiza que Windows permita el cambio ni que deje de reservar el UUID HID.
No se ha realizado el cambio. No es necesario inventar un nuevo driver para
comprobar primero la disponibilidad de esta alternativa instalada.

#### Controlador genérico confirmado como candidato

Después de agregar nuevamente el anillo, se ejecutó la consulta de solo lectura
`pnputil /enum-devices /instanceid <instancia HID actual> /drivers`.
La instancia consultada fue:

```text
BTHLEDevice\{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&0105ac_PID&0220_REV&0110_b7fc01c6f37e\a&49e30ac&17&0023
```

Windows devolvió estos dos candidatos:

| Paquete | Versión | Coincidencia | Rango | Estado |
| --- | --- | --- | --- | --- |
| `hidbthle.inf` | 10.0.26100.9549 | UUID HID `1812` | `00FF2000` | Mejor clasificado / instalado |
| `bthleenum.inf` | 10.0.26100.9711 | `BTHLEDevice\GenericATTService` | `00FF2001` | Superado |

Ambos indican proveedor Microsoft y firmante Microsoft Windows. «Superado» es
el estado de clasificación del candidato genérico; no significa que se haya
intentado instalar ni que haya fallado. La presencia del genérico como candidato
compatible queda confirmada para esa instancia. Su funcionamiento con el HID del
anillo y la exposición de una interfaz de servicio siguen pendientes.

No se cambió ninguna asociación. La instancia puede cambiar al quitar y volver
a agregar el anillo. El próximo paso es preparar selección por instancia y
reversión verificable a `hidbthle.inf` antes de efectuar el cambio temporal.

#### Resultado del cambio temporal al genérico ATT

Se aplicó `--apply generic` a la instancia terminada en `A&49E30AC&19&0023`.
`DiInstallDevice` aceptó la instalación sin solicitar reinicio. La comprobación
PnP confirmó `bthleenum.inf`, servicio `UmPass`, estado `OK` y `CM_PROB_NONE`.
Esto verifica que la selección del genérico es posible para esa instancia.

El escaneo posterior no recibió anuncios durante 60 segundos. Se abrió entonces
el dispositivo ya registrado por su dirección conocida y tipo PUBLIC; la sesión
pasó de `CLOSED` a `ACTIVE`. Se repitieron acceso WinRT y registro nativo:

| Operación con genérico instalado | Resultado |
| --- | --- |
| Descubrimiento HID WinRT | `SUCCESS` |
| Solicitud de acceso HID WinRT | `DENIED_BY_SYSTEM` |
| Enumeración nativa mediante handle del dispositivo | 7 servicios, 12 características HID |
| Registro de los seis Report mediante handle del dispositivo | `0x80070001` en todos |
| Interfaz HID bajo clase genérica de servicios | Ahora presente |
| Interfaz bajo UUID HID `1812` | Ahora presente |
| `CreateFileW` con lectura/escritura sobre ambas interfaces de servicio | Error Win32 5: acceso denegado |

No se habilitaron CCCD ni se recibieron informes. El genérico sí hizo aparecer
las interfaces, pero no concedió la apertura de lectura/escritura probada. No se
llegó a comprobar apertura de solo lectura con el genérico antes de la siguiente
reconexión; no extrapolar el resultado a todos los modos de apertura.

El usuario informó que tuvo que volver a conectar el anillo. La consulta posterior
encontró una nueva instancia, terminada en `A&49E30AC&1A&0023`, con `hidbthle.inf`,
servicio `mshidumdf` y código 10. Windows volvió a elegir el controlador original
para esa instancia; el cambio por instancia anterior no se conservó al recrearla.
No se ejecutó `--apply restore` sobre la nueva instancia porque ya tenía el
controlador original. La prueba no consiguió una suscripción funcional.

#### Herramienta y comandos de recuperación

Se creó `tools/select_ring_driver.py`. Por defecto solo enumera y verifica ambos
candidatos con SetupAPI. `--apply generic` selecciona `bthleenum.inf`, sección
`AttGenericService`; `--apply restore` selecciona `hidbthle.inf`, sección
`HidBthLE`, mediante `DiInstallDevice` para una sola instancia. Valida UUID HID,
VID/PID/revisión y dirección del anillo; rechaza otra instancia o candidatos
ambiguos. No modifica los INF ni elimina paquetes. Informa si Windows solicita
reinicio y no reinicia el equipo automáticamente.

La comprobación sin cambios encontró ambos candidatos en la instancia terminada
en `A&49E30AC&19&0023`. Esto verifica la selección, no una reinstalación exitosa:
la recuperación efectiva todavía requiere ejecutar y verificar el controlador.

Comandos para esa instancia, desde la raíz del repositorio en PowerShell con
privilegios de administrador (el identificador cambia si se vuelve a agregar):

```powershell
$ringInstance = 'BTHLEDEVICE\{00001812-0000-1000-8000-00805F9B34FB}_DEV_VID&0105AC_PID&0220_REV&0110_B7FC01C6F37E\A&49E30AC&19&0023'
# Comprobacion sin cambios:
& 'C:\ProgramData\anaconda3\python.exe' tools/select_ring_driver.py --instance $ringInstance
# Cambio temporal:
& 'C:\ProgramData\anaconda3\python.exe' tools/select_ring_driver.py --instance $ringInstance --apply generic
# Restauracion explicita:
& 'C:\ProgramData\anaconda3\python.exe' tools/select_ring_driver.py --instance $ringInstance --apply restore
# Verificar la asociacion y el estado despues de cada cambio:
pnputil /enum-devices /instanceid $ringInstance /drivers
```

La restauración devuelve la asociación original; no corrige el código 10 que
esta ya presentaba. Si se requiere reinicio, completar ese paso antes de valorar
el resultado de acceso GATT. Referencia:
[DiInstallDevice](https://learn.microsoft.com/en-us/windows/win32/api/newdev/nf-newdev-diinstalldevice).

1. Investigar cómo obtener una interfaz de servicio HID utilizable. El registro
   nativo mediante el handle del dispositivo falló. Investigar una
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

## Monitor continuo: 5 de noviembre de 2026

Se añadió `tools/monitor_jx05.py`, con estado JSON y registro rotativo local
en `.jx05-monitor/` (excluido de Git). Mantiene una solicitud GATT, registra
anuncios y cambios de sesión, y aplica el genérico Microsoft únicamente al
servicio HID de la dirección conocida cuando aparece con `hidbthle.inf`.
Cada instancia se intenta una vez por ejecución para evitar reinstalaciones
en bucle. La prueba nativa se repite cada 60 segundos de sesión activa;
sigue siendo una comprobación de registro, sin suscripción sostenida ni CCCD.

Validación real: se observaron cinco anuncios y `SESION ACTIVE` a las 12:16:56
(hora local). Se verificó la parada, que liberó la sesión, y se reinició en
segundo plano. Al aparecer la instancia nueva `A&49E30AC&1E&0023`, el monitor
detectó `hidbthle.inf` con `CM_PROB_FAILED_START`, aplicó `bthleenum.inf` sin
requerir reinicio y confirmó `CM_PROB_NONE`. Se recibió un anuncio con nombre
JX-05 y RSSI -62; la sesión volvió a `ACTIVE` a las 12:17:38.

A las 12:18:08 el estado seguía `CONNECTED` / `ACTIVE`, con seis anuncios
en esa ejecución. El intento nativo de las 12:17:44 registró cero suscripciones:
`0x80070001` usando el handle de dispositivo, y `WIN32=5` al abrir ambas
interfaces de servicio. El estado consultable indicó `REGISTRO_BLOQUEADO`.

Esto demuestra detección, activación de sesión y reasociación automática del
genérico. No demuestra recepción de informes de botones. La apertura nativa
del servicio HID había fallado también con acceso de solo lectura (Win32 5).
No existe todavía controlador propio. Se aprobaron las 17 pruebas automatizadas;
se verificaron inicio y parada reales. El monitor no arranca automáticamente
tras reiniciar Windows; detenerlo conserva la asociación del genérico.

### Apertura mínima y permisos efectivos del servicio

Con la sesión activa y el genérico instalado, una prueba adicional abrió la
interfaz HID real con `CreateFileW`, acceso 0 y, por separado, `READ_CONTROL`.
Ambas aperturas funcionaron. La lectura asíncrona con `GENERIC_READ` devolvió
Win32 5. `GetSecurityInfo` devolvió la siguiente seguridad efectiva:

```text
O:BAG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x1201bf;;;WD)(A;;0x1200a9;;;RC)
```

La DACL concede acceso completo a administradores; el proceso de prueba tenía
ese grupo habilitado e integridad alta. No hay evidencia de que ampliar esa
DACL resuelva la denegación. No se modificó.

Usando el handle de servicio abierto con acceso 0, la API nativa enumeró las
doce características. El registro de los seis informes devolvió `0x80070005`
en cada caso. Esto prueba una denegación también con un handle de servicio,
distinta del `0x80070001` obtenido antes con el handle del dispositivo. No se
habilitó ningún CCCD ni se recibieron informes. La apertura mínima permite
consultas de metadatos según [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew);
no equivale a permiso para notificaciones.

La siguiente línea de investigación es la viabilidad de un filtro específico
que observe la lectura del Report Map y permita comprobar si corregir la
respuesta anómala evita el fallo de inicio HID. Primero se debe identificar
una interfaz de transporte y demostrar observación sin modificar respuestas.
No hay todavía una interfaz de filtro validada ni un prototipo instalable;
no atribuir viabilidad a un simple INF ni prometer que corregir el mapa basta.

### Captura nueva de la inicialización HID (12:27:44–12:28:30)

Se pausó el monitor, se inició una sesión ETW BTHPORT acotada a 64 MB y se
seleccionó temporalmente `hidbthle.inf` en la instancia `1E&0023`. Tras 45
segundos se detuvo ETW, se restauró `bthleenum.inf` y se reinició el monitor.
No se modificaron respuestas ATT ni se instaló un filtro. Es observación del
tráfico, no interceptación con capacidad de corregirlo.

Archivos locales, excluidos de Git:

- `.jx05-monitor/hid-start.etl`: captura original, SHA-256
  `e1f5b36b2f7c08618f2a09d94d8c7e329a7ea6185636c613bcde400e6511eaac`.
- `.jx05-monitor/hid-start.xml`: conversión con `tracerpt`.
- `.jx05-monitor/hid-start-att.json`: seis mensajes ATT reensamblados y resumen;
  no exporta tráfico SMP.
- `.jx05-monitor/hid-start-summary.txt`: 52 eventos procesados, cero perdidos.

La secuencia del handle HCI `0x0200`, atributo `0x0042`, fue:

| Respuesta (UTC−03:00) | Desplazamiento solicitado | Bytes ATT | Bytes de valor |
| --- | ---: | ---: | ---: |
| 12:27:45.2874192 | 0 | 64 | 63 |
| 12:27:45.3173955 | 63 | 64 | 63 |
| 12:27:45.3473953 | 126 | 127 | 126 |

Se reutilizó el reensamblador del repositorio; no hubo paquetes excluidos ni
fragmentos pendientes. Se verificaron mediante aserciones los tres pares de
desplazamiento/longitud. La captura comenzó con una conexión existente: no
incluye su negociación MTU ni un evento Connection Complete con la dirección.
La atribución al JX-05 se apoya en la correlación temporal con su inicio HID y
la coincidencia con la secuencia previa. La identificación de `0x0042` como
Report Map procede de la enumeración nativa anterior. El MTU 64 está demostrado
en la captura anterior; no volver a presentarlo como negociado en esta nueva.

Durante esta misma prueba, PnP informó código 10, `0xC00000E5`, servicio
`mshidumdf`, filtro inferior `WUDFRd` y pila `BthLEEnum`. El INF local usa
`Microsoft.Bluetooth.Profiles.HidOverGatt.dll` en UMDF 2.15. Esta disposición
coincide con el transporte HID LE integrado documentado por
[Microsoft](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/hid-transports).
No se encontró un SDK/WDK en las ubicaciones habituales inspeccionadas y aún
no hay un punto de interposición validado para modificar esta lectura.

El usuario apagó y encendió el anillo después de la captura. El monitor observó
transiciones CLOSED/ACTIVE; a las 12:33:12 volvió a mostrar CONNECTED/ACTIVE,
con el genérico y `REGISTRO_BLOQUEADO`. La detección de encendido/apagado y la
recepción de informes HID siguen siendo resultados separados.

### Evaluación previa a instalar un filtro corrector

La petición de instalar y probar un filtro no se completó: no existe aún un
binario corrector ni un punto de interposición validado. La propuesta anterior
de un filtro debe entenderse como hipótesis de desarrollo, no como solución
disponible para instalar.

Se examinó, sin modificarla, la DLL instalada
`C:\Windows\System32\drivers\UMDF\Microsoft.Bluetooth.Profiles.HidOverGatt.dll`.
Su firma Microsoft es válida. SHA-256:
`09648a6511eea778b3b72a149ddbc585422bed55ab35ac19769c6f065bbd61ad`.
Se descargó del servidor público de símbolos de Microsoft el PDB identificado
en su registro CodeView, GUID `D8DEDB1DC1834E881FF9E2D62C70FEAB`, edad 1.
El resultado reproducible de la inspección está en
`.jx05-monitor/filter-preflight.json` y los símbolos en
`.jx05-monitor/HidOverGatt.pdb`, ambos excluidos de Git.

Los símbolos contienen `HogpGattAdapter::ReadCharacteristicValue`, cuya firma
menciona `IGattClientService`, y `_HIDOVERGATTGetReportDescriptor`. La tabla de
importaciones no contiene llamadas directas `BluetoothGATT*`. Esto identifica
funciones candidatas para depuración, pero no demuestra qué solicitudes pasan
por un filtro de dispositivo ni proporciona una interfaz pública para corregir
las respuestas ATT. No se inyectó código ni se alteró la DLL del sistema.

No se encontraron `cl`, `msbuild`, `inf2cat` o `signtool` en PATH, ni instalaciones
en las ubicaciones habituales de Visual Studio/Windows Kits examinadas.
Secure Boot informó `False`; BCD no tiene `testsigning` habilitado. No se
modificó el arranque. Microsoft documenta que la activación de carga de
[controladores de kernel con firma de prueba](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/the-testsigning-boot-configuration-option)
requiere reiniciar; eso sería una etapa posterior a disponer del paquete.

Tampoco está validado un descriptor completo de sustitución. Recortar la
respuesta o devolver únicamente el prefijo de 126 bytes sería una hipótesis
adicional: las referencias GATT a otros IDs de informe impiden afirmar que ese
prefijo describa todos los botones. No se instaló un filtro que finja corregir
el problema con esos datos incompletos. El monitor y el genérico se conservaron.

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
