# Investigación del JX-05 en Windows — 5 de noviembre de 2026

## Conclusión

**Actualización: vía AE02/AE42, 13:44 UTC−03.** Windows aceptó ambas
suscripciones Bleak por objetos redescubiertos: AE42 en el servicio AE40,
handle 77 (0x004D), y AE02 en AE00, handle 131 (0x0083). El monitor solo observa:
no cambia controladores y no emite teclas. La captura se preparó antes de pedir
una pulsación. El usuario confirmó la secuencia derecha, arriba, arriba;
con ambas suscripciones activas se recibieron **cero paquetes**. Se detuvo esta
vía según el criterio acordado. No hay códigos de botón con los que implementar
un mapeo fiable.
**El pasador de diapositivas sigue sin estar resuelto.** Los intentos anteriores
con `BleakDeviceNotFoundError` se hicieron dentro del entorno restringido;
fuera de él la misma implementación sí conectó y suscribió ambos canales.

La Fase 0 ya contrastó el mapa con los Report Reference de la captura original,
localizada en el Escritorio. Los seis Report notificables anuncian entradas IDs
1–6, y otro Report anuncia salida ID 1. El prefijo de 126 bytes solo define
entradas IDs 1 y 3. La respuesta adicional no es repetición ni rotación del
prefijo, y concatenarla produce un ítem HID reservado. **No está validado el
mapa fijo de 126 bytes propuesto para un filtro corrector.** El detalle y las
pruebas reproducibles están en «Fase 0: resultado con la captura original».

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

### Comprobación de la premisa del mapa fijo, sin instalar herramientas

Se compararon los valores ATT reales de `hid-start-att.json`, quitando el byte
de opcode: las dos primeras respuestas forman un prefijo de 126 bytes; la
tercera contiene otros 126 bytes.

- La tercera respuesta NO es idéntica a `prefix[0:126]`.
- No coincide con ninguna de las 126 rotaciones cíclicas del prefijo.
- Solo coinciden tres bytes en la misma posición. Sus primeros 18 bytes sí
  coinciden con `prefix[63:81]`; el siguiente byte ya difiere.
- Sus últimos 63 bytes contienen 57 ceros. Hay contenido diferente, pero estos
  datos no bastan para distinguir una continuación válida de corrupción.

Una inspección de ítems HID cortos del prefijo (tamaños 0, 1, 2, 4 según los
dos bits bajos; límites de ítem y balance de colecciones comprobados) encontró
tres Collection y tres End Collection, sin truncamientos. Define Report IDs
1 y 3: Input ID 1 suma 32 bits; Input ID 3 suma 24 bits, incluidos bits de
relleno y sin contar el byte de Report ID. Esto es una validación estructural
limitada, no prueba de que el mapa esté completo.

La misma captura contiene únicamente las tres solicitudes de lectura del
atributo `0x0042` y sus respuestas. No contiene lecturas de Report Reference
`0x2908`: no se pueden extraer de ella los seis pares (Report ID, tipo) ni
afirmar que esos dos IDs cubran todas las características Report. No se
encontró `jx05-amplio.xml` al buscar `jx05*.xml` en Documents y Downloads.

**Resultado de esta comprobación:** «trae bytes distintos», no «repetición del
mapa». Se bloquea la hipótesis de usar ya un mapa fijo de 126 bytes. Tampoco
se concatenará automáticamente la respuesta anómala: antes hay que determinar
qué bytes son válidos y contrastarlos con los Report Reference. No se pasó a
la instalación de herramientas ni a un filtro activo. El usuario expresó
preferencia por evitar instalaciones de SDKs.

### Fase 0: resultado con la captura original

Se encontró `C:\Users\TECH\Desktop\jx05-amplio.xml`. Esto resuelve la búsqueda
pendiente: no estaba en Documents ni Downloads. Se reanalizó sin cambiar el
controlador, el arranque ni instalar dependencias.

Antes se intentó la lectura nativa de Report Reference desde caché. Se
enumeraron los siete descriptores, pero `BluetoothGATTGetDescriptorValue`
devolvió `0x80070005` para todos: **0/7 valores accesibles por esa vía**. El
registro está en `.jx05-monitor/report-references.log`. No se debe confundir
ese resultado con los valores recuperados posteriormente de la captura ATT.

En la captura original se emparejaron solicitudes/respuestas de descubrimiento
de características, descubrimiento de descriptores y lectura de valores. Los
Report Reference `0x2908` contienen estos pares reales:

| Report (handle de valor) | Descriptor | Bytes del valor | Report ID | Tipo |
| --- | --- | --- | ---: | --- |
| `0x0027` | `0x0029` | `01 01` | 1 | Input |
| `0x002B` | `0x002D` | `02 01` | 2 | Input |
| `0x002F` | `0x0030` | `01 02` | 1 | Output |
| `0x0032` | `0x0034` | `03 01` | 3 | Input |
| `0x0036` | `0x0038` | `04 01` | 4 | Input |
| `0x003A` | `0x003C` | `05 01` | 5 | Input |
| `0x003E` | `0x0040` | `06 01` | 6 | Input |

Las lecturas ocurrieron entre 10:15:28.3826609 y 10:15:29.0429387 UTC−03:00.
No se dedujeron IDs de los handles. El Report de salida es el séptimo Report,
sin notificaciones; los otros seis son los notificables.

El parser mínimo incorporado a `tools/analyze_att.py` comprueba límites de
ítems cortos (el tamaño codificado como 3 significa 4 bytes), Collection/End
Collection, Report ID/Size/Count y Push/Pop global. Rechaza ítems truncados,
ítems largos no soportados, main items reservados y pilas sin cerrar. No es
un validador completo de semántica HID. Sigue el formato de la
[especificación HID 1.11, secciones 6.2.2.2 y 6.2.2.7](https://www.usb.org/sites/default/files/hid1_11.pdf).

Resultado del prefijo:

- 126 bytes; tres colecciones abiertas y cerradas.
- Input ID 1: 32 bits; Input ID 3: 24 bits, incluyendo relleno y excluyendo el
  byte Report ID.
- No define Input IDs 2, 4, 5, 6 ni Output ID 1, presentes en la tabla GATT.

Las siete respuestas al desplazamiento 126 de la captura original tienen
126 bytes de valor cada una, con **dos variantes distintas**. Ninguna es igual
al prefijo ni una rotación cíclica de él. Concatenar cualquiera al prefijo
produce `Reserved main item at 126`. La respuesta posterior capturada a las
12:27 tampoco es repetición ni rotación. No basta con llamar «bytes nuevos»
a ese contenido y darlo por continuación válida: puede estar corrupto. Tampoco
la discrepancia con Report Reference permite saber cuáles características
emiten realmente datos al pulsar botones.

**Decisión:** «trae bytes distintos; mapa completo aún no reconstruido».
No se pasa a la Fase 2/3 del filtro con un mapa fijo. Para continuar hace falta
una fuente válida de las definiciones ausentes o una captura que permita
recuperarlas; no se inventarán longitudes ni IDs de informe para rellenarlas.

Pruebas y reproducción:

- `tests/fixtures/jx05_report_map.json`: valores reales de las tres respuestas
  de la captura posterior, con procedencia y SHA-256 de su ETL.
- `tests/fixtures/jx05_att_phase0.json`: 76 mensajes ATT seleccionados de la
  captura original (MTU, enumeración HID, referencias y mapa), con SHA-256 del
  XML; no incluye SMP ni datos de otros servicios.
- Las pruebas verifican los siete pares anteriores, las cinco definiciones
  ausentes, las siete respuestas superiores al MTU, el parser HID y el manejo
  de datos truncados/denegados. **24 pruebas pasaron.**
- `analyze_att.py` ahora informa `report_references`, `report_map_structure` y
  `references_missing_from_prefix`. Si no se capturó negociación MTU, informa
  `null`; no supone MTU 23 ni declara una violación basándose en esa suposición.
- `probe_gatt_session.py --native-references` permite reproducir la consulta
  de caché cuando se recibe un anuncio; no la confunde con lectura ATT real.

```powershell
& 'C:\ProgramData\anaconda3\python.exe' tools/analyze_att.py 'C:\Users\TECH\Desktop\jx05-amplio.xml' --handle 0x200
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -v
```

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

## Implementación del observador AE02/AE42 — 5 de noviembre, 13:35

Alcance: `tools/monitor_jx05.py`, sus pruebas, `tools/monitor_logon.ps1` y la
documentación. Los analizadores y pruebas de la fase HID previa se conservaron.
Se retiraron del monitor las llamadas a selección automática de controlador y
al registro nativo HID; la herramienta manual de controladores sigue separada.

El monitor usa Bleak 2.1.1 ya instalado. En cada conexión solicita descubrimiento
sin caché y selecciona UUID completos AE02/AE42 con propiedad notify/indicate.
Pasa el objeto actual a `start_notify`, según la
[API oficial de Bleak](https://bleak.readthedocs.io/en/latest/api/client.html#bleak.BleakClient.start_notify).
No fija handles ni escribe comandos propietarios. La habilitación estándar de
notificaciones GATT sí forma parte de la suscripción. Registra servicio, UUID,
handle, propiedades, aceptación/error y cada paquete con hora UTC y bytes.
`ESCUCHANDO` significa suscripción, nunca botón identificado.

Conserva el mutex por sesión, estado JSON atómico, registro rotativo (2 MB más
dos copias), consulta y parada. Reconecta con espera 2/4/8/16/32/60 segundos;
tras una conexión de al menos 60 segundos vuelve a 2. Parar cancela también
escaneo/suscripción y libera el cliente. Si ninguna suscripción se acepta,
permanece `BLOQUEADO` hasta desconexión o parada, sin probar otro controlador.

Evidencia real local (`.jx05-monitor/events.log`, excluido de Git):

- 13:31:43: finalizó el monitor anterior; `running=false` antes de sustituirlo.
- 13:34:53: inició el observador oculto con PID 15984 usando `pythonw.exe`.
- 13:35:24: `BleakDeviceNotFoundError`, dirección B7:FC:01:C6:F3:7E no encontrada.
- 13:35:43: parada confirmada, `running=false`, cero suscripciones y paquetes.
- Se pidió al usuario encender y confirmar. No se pidió pulsar botones ni se
  avanzó a una prueba física posterior sin esa respuesta.

Se preparó el inicio al iniciar sesión mediante una tarea **JX05 Monitor** para
el usuario actual, con token interactivo y privilegios limitados, ejecutando
`pythonw.exe`. No se registró ninguna tarea ni se cambió el arranque. El script
incluye desinstalación y `-WhatIf`, y no sobrescribe tareas existentes.
La desinstalación quita el inicio automático; para cerrar un monitor ya iniciado
se usa primero `--stop`. Los registros se conservan.

Validación: **28 pruebas Python aprobadas**, incluyendo reconexión simulada con
objetos/handles nuevos, permisos denegados, suscripción parcial, repetidos y
liberación conservados sin interpretación, parada y límite de espera progresiva.
La prueba PowerShell `tests/test_monitor_logon.ps1` pasó con cmdlets simulados y
comprobó que `-WhatIf` no realiza operaciones. No se validó el registro real:
la construcción inicial de objetos CIM devolvió acceso denegado en este entorno;
el modo `-WhatIf` final evita consultar CIM. Se comprobó `git diff --check`.

Pendiente, condicionado al hardware: recibir y correlacionar un botón cada vez,
identificar liberación/gesto completo, implementar Right/Left mediante SendInput
con habilitación explícita y una acción por pulsación, y dejar el centro sin
asignar. No se añadieron códigos de botón supuestos ni una opción de presentador
que finja funcionar; `presenter_enabled` permanece falso.

No se realizaron los diez avances/diez retrocesos en PowerPoint, xaringan y
Google Slides, ni los cinco minutos de uso ni recuperación física tras apagar y
encender. Los paquetes repetidos de las pruebas son datos sintéticos, no una
calibración del anillo. Si la captura preparada no arroja datos correlacionados,
se documentará y se detendrá esta vía, sin cambiar automáticamente de driver.

### Suscripción real lograda fuera del entorno restringido — 13:41

Tras confirmar el usuario que el anillo estaba encendido, los intentos dentro
del sandbox continuaron con `BleakDeviceNotFoundError`. Una consulta PnP de
solo lectura también devolvió acceso denegado. Se detuvo ese proceso y se
repitió la ejecución del mismo observador fuera del sandbox, sin cambiar
controladores. PnP mostró JX-05 presente y OK. No se debe atribuir el error
anterior necesariamente al escaneo: Bleak usa el mismo tipo de error cuando
Windows no entrega el objeto BluetoothLEDevice.

A las 13:41:02 el PID 29788 confirmó:

| Servicio | Característica | Handle actual (decimal / hex) | Resultado |
| --- | --- | --- | --- |
| AE40 | AE42 | 77 / 0x004D | SUSCRITO, notify |
| AE00 | AE02 | 131 / 0x0083 | SUSCRITO, notify |

El estado pasó a CONNECTED/ESCUCHANDO, sin error y con cero paquetes. Solo
entonces se pidió pulsar y soltar una vez el botón superior y confirmar.
La aceptación de suscripciones no demuestra que estos servicios lleven botones.

Se verificó además el mutex con una segunda ejecución real: terminó con
`Ya existe un monitor activo` antes de abrir otra conexión. El proceso original
conservó la captura. La prueba del botón superior permanece pendiente de la
confirmación del usuario; el silencio mientras se espera no cuenta como una
prueba de pulsación sin datos.

### Resultado de las pulsaciones confirmadas — 13:44

El usuario confirmó: «pulse el de la derecha, despues el de arriba y despues
el de arriba». No fue una prueba aislada por botón; se conserva esa secuencia
exacta como límite de la evidencia. A las 13:44:11 el estado seguía
CONNECTED/ESCUCHANDO en ambas características, `error=null`, `packets=0` y
`last_packet=null`. No se registraron desconexiones durante la escucha ni
notificaciones de ninguna de las pulsaciones comunicadas.

**Resultado: ninguna notificación correlacionada con la secuencia probada.**
Esto no demuestra que los servicios nunca puedan transportar botones bajo otro
protocolo, pero no proporciona datos para mapearlos y no se enviarán comandos
propietarios desconocidos para intentar activarlos. Se detuvo esta vía según
el plan: a las 13:44:29 el monitor confirmó `running=false`, cero suscripciones
activas y conexión liberada. No se cambió de driver ni se registró autoarranque.

La infraestructura de observación queda implementada y probada; SendInput,
calibración por gesto y las validaciones en presentaciones permanecen bloqueados
por falta de paquetes identificados. No se considera resuelto el objetivo.

### Error de controlador comunicado después de la parada

El usuario informó que apareció un error de controlador y el dispositivo se
salió. La consulta PnP posterior confirmó una instancia HID nueva
`A&49E30AC&1F&0023`, presente, con `hidbthle.inf`, código 10 y estado decimal
3221225701 (`0xC00000E5`). Los servicios AE00/AE40 y el nodo Bluetooth principal
aparecieron presentes y OK; ese estado PnP no prueba una conexión de radio activa.

Cronología de Kernel-PnP/Configuration consultada, hora local:

- 13:39:17–18: se eliminaron los nodos anteriores `1E` y el nodo del anillo.
- 13:39:32–36: se crearon los nodos nuevos `1F`; Windows seleccionó
  `hidbthle.inf` para HID (evento 400), que falló a las 13:39:35 (evento 411,
  problema `0xA`, estado `0xC00000E5`). AE00 y AE40 iniciaron correctamente.
- 13:41:02: el observador consiguió ambas suscripciones propietarias pese al
  fallo HID; no capturó paquetes con las pulsaciones comunicadas.
- 13:44:29: se detuvo deliberadamente el observador y se liberó su conexión.

El fallo HID documentado precede a la parada: no es un nuevo error de inicio
causado en ese momento por cerrar el monitor. Liberar GATT deja de mantener la
conexión de la aplicación; no se dispone de una captura de radio que determine
el motivo exacto de la desconexión percibida por el usuario. Esta revisión solo
consultó estado y eventos, sin cambiar controladores ni reiniciar el monitor.

### Desconexión comprobada con captura HCI — 13:57–13:59

Se reprodujo el cierre sin cambiar controladores, con el monitor actualizado y
una sesión ETW temporal BTHPORT limitada a 64 MB. El monitor debía permanecer
CONNECTED/ESCUCHANDO 60 segundos; después se solicitó su parada y se observaron
30 segundos adicionales. La comprobación fallaba explícitamente si se perdía
la conexión antes de solicitar la parada. El proceso y la sesión ETW terminaron.

| Hora local UTC−03 | Evidencia |
| --- | --- |
| 13:57:48.0723481 | HCI LE Connection Complete, estado 0, dirección del anillo B7:FC:01:C6:F3:7E, handle 0x0200 |
| 13:57:51.6057756 | Monitor PID 33720 con ambas suscripciones, CONNECTED/ESCUCHANDO |
| 13:58:52.2766589 | Se completaron 60 segundos de observación conectada |
| 13:58:52.2796585 | Solicitud controlada de parada |
| 13:58:53.075704 | Monitor guardó running=false y liberó el cliente |
| 13:58:56.0814605 | El host envió HCI Disconnect para 0x0200, motivo transmitido 0x13 |
| 13:58:56.2786651 | HCI Disconnection Complete para 0x0200, estado 0, motivo local 0x16 |
| 13:59:23 | Fin de observación posterior y parada de ETW |

**Resultado:** el enlace permaneció activo con el monitor y Windows ordenó su
cierre unos tres segundos después de liberarlo. En esta reproducción no fue una
caída espontánea mientras el monitor mantenía la sesión. El evento local 0x16
identifica terminación por el host local; que el comando envíe 0x13 al otro lado
no implica que el anillo iniciara la desconexión. Es el comportamiento descrito
en la [especificación HCI, comando Disconnect](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-60/out/en/host-controller-interface/host-controller-interface-functional-specification.html).
La prueba reproduce el mecanismo; no recupera retrospectivamente el tráfico
exacto de la desconexión de las 13:44.

PnP mostró que la instancia `1F` había sido eliminada a las 13:56:55 y reemplazada
por `20` antes de esta prueba. El HID `A&49E30AC&20&0023` falló a las 13:57:12
con `hidbthle.inf`, código 10, estado `0xC00000E5`: antes del inicio del monitor
a las 13:57:44. No aparecieron eventos PnP del anillo durante ni después de la
captura al consultar el canal Configuration. El nodo HID seguía con error y los
servicios AE00/AE40 figuraban OK. El cierre del enlace y el fallo de inicio HID
son hechos distintos; mantener GATT conectado no corrige el segundo.

Artefactos locales, excluidos de Git, con prefijo
`.jx05-monitor/disconnect-20261105-135744`:

- `.etl`: SHA-256 `09b778bf2a864eb85f381c94589ef3243cd51be52d61049863a67b0cb7f7d767`.
- `.xml`, `.summary.txt`: 142 eventos procesados, 0 perdidos, 140 paquetes BIP.
  tracerpt avisó de eventos no coincidentes con el esquema; los tres eventos
  HCI utilizados tienen campos BIP decodificados, longitudes y handle verificables.
- `.log`: marcas de inicio, conexión, parada y salida del monitor.
- `.connection.json`: solo conexión/desconexión del handle identificado por
  dirección; no exporta SMP ni material de emparejamiento.
- `.pnp.json`: eventos del anillo en Kernel-PnP/Configuration.

El extractor local `analyze_disconnect.py` incluye aserciones para comando,
evento, dirección y exclusión de paquetes ACL; no se modificó el código del
monitor en esta comprobación. Se conserva parado. No se instalaron controladores
ni tareas de inicio; el pasador de diapositivas sigue sin recepción de botones.

### Revisión de una alternativa existente: jx05presenter

Se revisaron directamente las fuentes públicas de
[savikko/jx05presenter](https://github.com/savikko/jx05presenter), en particular
[windows/src/main.rs](https://github.com/savikko/jx05presenter/blob/main/windows/src/main.rs)
y `windows/Cargo.toml` (versión declarada 1.5.1). No se descargó ni ejecutó su
binario. La versión Windows usa `hidapi::HidApi`, busca por nombre de producto,
abre una interfaz HID existente y lee informes antes de llamar a SendInput.
No contiene un transporte GATT alternativo ni una reparación del inicio HID.

Comprobación nativa de solo lectura con HidD_GetHidGuid y Configuration Manager:
14 interfaces HID presentes; cero candidatas con dirección B7FC01C6F37E o
VID 05AC / PID 0220. Registro local: `.jx05-monitor/hid-interface-check.txt`.
Con el controlador del anillo fallando, no se cumple la precondición de esa
aplicación. Su publicación como compatible con Windows no prueba compatibilidad
con esta unidad y este fallo de inicio.

Además, su parser Windows presupone como mínimo seis bytes, con X/Y de 16 bits
en posiciones fijas. El prefijo descriptor de esta unidad describe cuatro bytes
de payload táctil, con ejes de 12 bits. No se importará ese parser ni sus umbrales
sin paquetes reales del anillo; el nombre de modelo no basta para igualarlos.

### Hipótesis acotada sobre el límite de la lectura larga

Los 126 bytes anteriores a la respuesta defectuosa son exactamente dos bloques
de 63 bytes (MTU 64 menos el opcode). Eso también es compatible con un fallo del
periférico al pedir el bloque siguiente justo al final de su valor. No demuestra
que 126 sea la longitud correcta: siguen sin explicarse las referencias a otros
IDs, y no se dispone de una lectura independiente válida.

Si el valor realmente midiera 126 bytes, un MTU 23 permitiría terminar con un
bloque corto de 16 bytes tras cinco bloques de 22, evitando una solicitud al
desplazamiento 126. Es una hipótesis para una futura prueba de transporte, no
una solución implementada. Windows expone
[GattSession.MaxPduSize](https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.genericattributeprofile.gattsession.maxpdusize?view=winrt-26100)
como propiedad de solo lectura y negocia el MTU automáticamente; no se ha
identificado un ajuste documentado por dispositivo para forzar ese experimento
con las herramientas actuales. No se alteró el adaptador ni el registro.

La preparación de un controlador propio queda pendiente de aclarar el límite
explícito del plan «sin SDKs / no instalar drivers». Se solicitó esa aclaración;
ningún permiso para ampliar herramientas o instalar se presume por silencio.
El objetivo funcional completo se mantiene: recepción verificada de botones y
avance/retroceso real en las tres herramientas de presentación.

### Comprobación de registros adicionales de fallo HID

Las consultas de solo lectura no encontraron canales ni proveedores publicados
con nombre HidOverGatt. `logman query providers` tampoco mostró ese proveedor.
El canal `Microsoft-Windows-DriverFrameworks-UserMode/Operational` está
deshabilitado; no se obtuvieron eventos del proveedor UMDF en System para hoy.
No se habilitaron canales ni se reinició el dispositivo. No hay evidencia
retrospectiva adicional que permita atribuir con certeza el código 10 al mapa
HID, frente a otra etapa interna de inicialización. La consulta de procesos no
encontró python/pythonw activo; el monitor terminó, no es un trabajo pendiente.

Se mantiene el bloqueo para la siguiente etapa: falta aclarar si sigue vigente
el límite sin SDKs ni drivers. La continuación automática del objetivo no se
interpreta como respuesta a esa aclaración. No hay paquete de controlador
preparado, firmado o validado, ni recepción de botones demostrada.

### 2026-11-05: autorización y prototipo propio MTU

El usuario respondió «sí, haz un controladro» a la ampliación para preparar
un controlador propio y herramientas. Queda superada la restricción previa
de no instalar SDKs para este desarrollo. No se interpreta como autorización
para cambiar BCD, reiniciar Windows o intervenir ahora en todo el adaptador.

Se instalaron Build Tools de Visual Studio 2022 (MSVC 14.44.35207 y ASan,
ambos instaladores terminaron con código 0) y se extrajeron los paquetes
oficiales NuGet SDK/WDK 10.0.26100.6584 en `.toolchain/`, excluido de Git.
El bootstrapper tenía firma válida de Microsoft. SHA-256 de los NuGet:

| Paquete | SHA-256 |
| --- | --- |
| Microsoft.Windows.WDK.x64 | C393D03DFB640B5C92F546B32F6770EF68CD3AAF691956E7D66D8E2C28A1B55E |
| Microsoft.Windows.SDK.cpp.x64 | C29CE7A4641CB37EE32EBB8078CC65CFBABC7025076BCFBA869039204B1E960D |
| Microsoft.Windows.SDK.cpp | 5D31B38205BDD9AC761B4CB39FBBC6B7209B01C11194324AFC674D7D119483A0 |

El BthGATTDump del WDK, ejecutado sin forzar lecturas fuera de caché, identifica
fabricante `zhuhai_jieli`, modelo `hid_mouse` y versiones `0.0.1`.
Salida: `.jx05-monitor/wdk-gattdump.txt`. No desbloqueó HID.

El código público de [Jieli ble_hogp.c](https://github.com/Jieli-Tech/fw-AC63_BT_SDK/blob/master/apps/hid/modules/bt/ble_hogp.c)
asigna inicialmente la longitud total del Report Map; en el caso de un offset
al final sale sin copiar bytes y conserva esa longitud como retorno. Esto
ofrece una explicación plausible de la respuesta de 126 bytes al offset 126.
No demuestra que sea la versión exacta de firmware de este anillo.
La [tabla GATT del mismo SDK](https://github.com/Jieli-Tech/fw-AC63_BT_SDK/blob/master/apps/hid/modules/bt/ble_hogp_profile.h)
contiene los seis Input y Output de forma estática, además de los mismos handles
AE42=0x004e y AE02=0x0084 observados. Las referencias a IDs sin usar pueden
proceder de esa tabla; ya no bastan por sí solas para descartar un mapa de 126
bytes. El mapa del ejemplo keypage actual no coincide byte por byte con el
capturado: no se lo ha usado como sustitución.

Inspección local adicional, sin alterar binarios: los símbolos y desensamblado
de HidOverGatt muestran que `HidGetReportDescriptor` accede a un objeto ya
almacenado; `DevicePrepareHardware` realiza inicialización GATT mediante sus
adaptadores privados. No se ha establecido que un filtro de descriptor HID
pueda resolver el fallo anterior de lectura. Evidencia local:
`.jx05-monitor/hogp-symbols.json`, `hogp-disasm.txt` y `read_symbols.py`.

Se implementó una vía distinta y concreta: `driver/jx05mtu.c` es un filtro
inferior USB KMDF y `driver/mtu.c` limita intercambios ATT Exchange MTU a 23,
solo después de observar conexión exitosa de B7:FC:01:C6:F3:7E pública. Corrige
solicitud y respuesta para mantener coherentes los dos extremos. No recorta
Report Map ni inventa descriptores. El INF de extensión corresponde al
adaptador observado `USB\VID_13D3&PID_3567&REV_0100&MI_00`.

Esta arquitectura necesita intervenir en la pila del adaptador, aunque sus
cambios de paquetes se limiten al anillo. Conserva BTHUSB, `oem4.inf` y
MTKBTFilterX64; no es un reemplazo del controlador base. Se preparó únicamente
el paquete, sin instalarlo, para someter ese alcance concreto a aprobación.
Las limitaciones de fragmentación, cancelación/concurrencia y transporte
están en [driver/README.md](driver/README.md), junto con instalación y reversión.

Verificación realizada:

- Compilación x64 con MSVC `/W4 /WX`, análisis estático `/analyze` sin defectos,
  NX, CFG y GS. Entrada FxDriverEntry conforme a las props KMDF del WDK.
- Pruebas C con AddressSanitizer: negociación en ambos sentidos, otras
  conexiones, truncamientos, desconexión, reutilización de handle, reinicio,
  eventos no soportados y 100.000 buffers aleatorios/malformados: pasan.
- InfVerif `/u` y generación de catálogo Inf2Cat Windows 11 24H2 x64:
  cero errores y cero advertencias.
- 28 pruebas Python existentes y prueba PowerShell del inicio automático
  simulado: pasan; no se registró tarea.
- Firma de prueba de SYS y CAT; firma criptográfica CMS del catálogo verificada.
  Certificado `8A60B87510907265DD5187EAE3D6799D2123AE64`, raíz no confiable
  esperada: no se importó a Root ni TrustedPublisher. PFX temporal eliminado.
  La firma requirió salir del sandbox; no cambió confianza del sistema.

Paquete en `build/jx05mtu/package/`; hashes finales en
`build/jx05mtu/hashes.json`. SHA-256 SYS firmado:
`364114EB1204E8B07771CD10EC11DACDE8784247D71EB0D04332B731F75DC7E3`.
Certificado público en `build/jx05mtu/jx05-test.cer`. Scripts reproducibles
`driver/build.ps1` y `driver/sign-test.ps1`.

La comprobación final de solo lectura confirmó BTHUSB, `oem4.inf` y únicamente
MTKBTFilterX64 como LowerFilters; sin `testsigning` en la entrada BCD actual y
sin el certificado de prueba en los dos almacenes de confianza. No hubo
reinicio ni cambios de firmware o de inicio de sesión.

**Pendiente:** aprobar habilitar carga de prueba y reiniciar Windows para
instalar/probar esta extensión sobre el adaptador. Podría interrumpir el ratón
Bluetooth y un defecto de kernel podría causar pantallazo azul. No se ejecutó
Driver Verifier ni se ha cargado el prototipo. No hay evidencia de MTU 23 en
el anillo, desaparición del código 10, recepción de botones ni avance de
diapositivas. El objetivo funcional sigue sin estar resuelto.

### Autorización de activación y comprobación previa de BitLocker

El usuario autorizó instalar el filtro, habilitar modo de prueba y reiniciar
Windows. Se verificaron los cuatro hashes del paquete aprobado y el certificado
8A60B87510907265DD5187EAE3D6799D2123AE64. Se guardó BCD mediante exportación y
listado, la lista de paquetes y el estado del adaptador en
`.jx05-monitor/activation-20261105-151900/`. El puntero a esta sesión está en
`.jx05-monitor/activation-current.txt`.

La consulta detectó C: completamente cifrado, desbloqueado y con protección
BitLocker activa. Secure Boot está desactivado. El ajuste `testsigning` forma
parte del [perfil de validación BCD de BitLocker](https://learn.microsoft.com/en-us/windows/security/operating-system-security/data-protection/bitlocker/bcd-settings-and-bitlocker).
Cambiarlo sin preparar BitLocker puede desencadenar recuperación en el arranque.
Se solicitó autorización adicional y específica para suspender sus protectores
solo durante un reinicio con reactivación automática. No se solicitó ni se
extrajo la clave de recuperación. Hasta recibir respuesta, no se cambió BCD,
no se importó el certificado y no se instaló ni reinició ningún dispositivo.

### BitLocker suspendido y modo de prueba configurado; reinicio pendiente

El usuario autorizó suspender BitLocker y añadió «no reinicies todavía,
pregunta». Se verificaron de nuevo hashes, certificado, Secure Boot desactivado
y protección BitLocker inicialmente activa. Se importó el certificado de prueba
en LocalMachine Root y TrustedPublisher; las firmas de SYS y CAT ahora se
validan como `Valid` con el thumbprint esperado.

Se ejecutó `Suspend-BitLocker -MountPoint C: -RebootCount 1` y se verificó
ProtectionStatus=Off y VolumeStatus=FullyEncrypted. Después se configuró
`bcdedit /set '{current}' testsigning on`; el listado posterior confirma
`testsigning Yes`. Está configurado para el próximo arranque, no demuestra que
el modo de prueba esté activo en el kernel actual.

Registro: `.jx05-monitor/activation-20261105-151900/state.json`, etapa
`awaiting-explicit-restart-confirmation`, y `bcd-after.txt`. No se solicitó ni
programó reinicio. Tampoco se agregó el paquete al Driver Store ni se instaló
el filtro: se hará después del arranque en modo de prueba para evitar un fallo
de firma en la pila Bluetooth actual.

La protección de BitLocker permanece suspendida mientras se espera el reinicio;
el contador solicitado es uno y debe reanudarse automáticamente al reiniciar.
Al volver, verificar explícitamente la reanudación de BitLocker, el nuevo
LastBootUpTime y el modo de prueba antes de instalar el paquete ya autorizado.
El reinicio requiere ahora confirmación expresa del usuario. No hay todavía
recepción de botones ni prueba funcional del controlador.

### Continuación 2026-11-05: HID funcionando y efectos nativos identificados

El usuario autorizó el reinicio («reinicia noams»). Windows arrancó a las
20:22:28, BitLocker reanudó su protección y el kernel confirmó testsigning
activo. No se cambió Secure Boot. Se instaló la extensión Jx05Mtu conservando
BTHUSB, oem4.inf y MTKBTFilterX64.

La primera versión no corregía la oferta MTU de Windows: era 527, superior
al límite 517 que rechazaba el prototipo. La versión 0.1.0.1 acepta cualquier
oferta >=23 y la reduce a 23. La traza confirma lecturas del mapa de 126 bytes
en bloques 22/22/22/22/22/16 y el HID inicia sin código 10. Evidencia local:
`activation-20261105-151900/v011-{filter,bth}.{etl,xml}` y fixture
`tests/fixtures/jx05_report_map_complete.json`.

Se capturaron y confirmaron por separado pulsaciones cortas y mantenidas de
los cuatro botones. Superior/inferior producen gestos verticales; los laterales
producen gestos horizontales. Mantener superior/inferior produce pulsos consumer
de volumen; mantener los laterales produce dos contactos táctiles. El usuario
pidió explícitamente repetición al mantener, sustituyendo el requisito inicial.
Los ocho casos están en `tests/fixtures/jx05_buttons.json`.

El monitor Raw Input emite Left/Right mediante SendInput, empieza desactivado y
admite --presenter-on/--presenter-off. El usuario confirmó movimiento de
diapositivas en PowerPoint, pero también cambios de volumen y selección de
texto. Por tanto, esta versión NO cumple todavía el objetivo. Se desactivó la
emisión y después se detuvo el monitor para actualizar el filtro. No se ha
registrado inicio automático ni se han validado xaringan/Google Slides.

La versión 0.1.0.2 preparada sustituye únicamente los bloques exactos del mapa
capturado por otro de igual longitud, con colección vendor FF00:0001 y los
mismos tamaños de informes (ID1=32 bits, ID3=24 bits). Busca impedir que Windows
los interprete además como pantalla táctil/volumen. No cambia los datos de
botones ni el firmware. Se compila con análisis estático y pruebas C/ASan.
Las 34 pruebas Python pasan, incluidas las ocho capturas con informes duplicados.
El anillo reinicia contactos durante un mismo mantenimiento: se conserva el
límite de repetición de 750 ms entre esos reinicios. Su aplicación en hardware
y la desaparición de efectos secundarios siguen pendientes en este punto.

Se exportó oem3.inf (0.1.0.1) y su certificado a `build/jx05mtu-v011` para
reversión. La firma de 0.1.0.2 usa el certificado
`515214F5FB0AA25C02FC5BD484303F722EC10B35`; aún debe verificarse su instalación.

### 0.1.0.2 agregado, segundo reinicio pendiente y módulo de mapeo

La retirada de 0.1.0.1 solicitó reinicio. Reiniciar únicamente el adaptador
fue rechazado por PnP porque existe una operación pendiente. Se agregó 0.1.0.2
como oem3.inf, resultado 3010; la versión vieja continúa cargada. El nuevo
certificado está importado y las firmas SYS/CAT son Valid. Se conserva el
certificado anterior hasta verificar el nuevo arranque. BitLocker continúa
FullyEncrypted / Protection On. No se reinició ni se cambió BCD en esta
actualización. El monitor está detenido.

El usuario pidió un módulo breve de calibración o mapeo y aclaró que mantener
el central >=3 segundos apaga el anillo. Se añadió `tools/map_jx05.py`: asigna
por separado avanzar/retroceder/ninguna acción a los cuatro direccionales y
guarda un JSON validado. El monitor lo carga al iniciar y al activar emisión.
El decodificador distingue ahora el botón físico de su acción asignada.

Para el central el usuario se inclinó por pantalla completa o iniciar la
presentación. El asistente permite guardar PowerPoint (Shift+F5), Google Slides
(Ctrl+F5) o xaringan (F); el emisor tiene comprobación de pares y limpieza de
modificadores ante fallo parcial. **El central aún no se decodifica ni se emite**:
primero hace falta capturar y confirmar solo su pulsación corta. Su preferencia
inicial sigue sin asignar; mantenerlo no será una función del presentador.

Pasan 38 pruebas Python. La desaparición de efectos, la señal central y el
funcionamiento real de los tres entornos están pendientes. El estado de
activación se guardó como `v012-staged-awaiting-explicit-restart`.

El usuario autorizó el segundo reinicio y preguntó por BitLocker. Se verificó
otra vez C: FullyEncrypted / Protection On y BCD testsigning Yes. No se cambió
BCD ni se suspendió o descifró BitLocker para esta actualización. Se procede
al reinicio autorizado para cargar 0.1.0.2, sin forzar el cierre de aplicaciones.
Al volver se deben verificar la versión cargada, el estado HID y BitLocker
antes de activar captura y solicitar la pulsación corta del central.

### Segundo arranque y aislamiento HID verificado

Windows arrancó el 2026-11-05 a las 21:06:07. Jx05Mtu está RUNNING y su binario
Driver Store tiene SHA-256 6E660BCD4BEC413CA2010FE70ABDE424A0FB3539B18DCE3D8C8881F97AF2ADDF,
igual al firmado 0.1.0.2. BitLocker permanece FullyEncrypted / Protection On.
Se retiró únicamente el certificado anterior 0C26... de Root/TrustedPublisher.

Windows conservaba el mapa HID antiguo en caché. Reiniciar y recrear solo el
nodo HID no generó lecturas ATT. BluetoothGATTGetCharacteristicValue devolvió
80070001 con handle de dispositivo; abrir la interfaz de servicio devolvió
Win32 31. Se renovó únicamente el emparejamiento del JX-05. PairAsync básico
falló; la ceremonia estándar CONFIRM_ONLY con cifrado terminó PAIRED.

La captura `v012-refresh-filter.etl/xml` registra evento 3 (MTU corregido) y
seis eventos 5 con contadores 1..6. `v012-refresh-bth.etl/xml` confirma MTU23
y los 126 bytes vendor. Windows expone una sola colección de proveedor, sin
error, en lugar de consumer y touchscreen. El fixture
`tests/fixtures/jx05_report_map_vendor.json` conserva mapa y hash de la captura.
La instancia HID nueva usa sufijo A&49E30AC&22&0023.

El usuario confirmó derecho mantenido sin selección/movimiento del puntero y
superior mantenido sin cambios de volumen. El monitor recibió respectivamente
gestos táctiles y reportes consumer ahora encapsulados en la colección vendor;
estos últimos llegan con relleno a cinco bytes (`0302000000` / `0300000000`).

La pulsación corta del central confirmada a las 21:15:25 produjo
`0107f40119` y `0100f40119`: x500/y400, contacto y liberación. Se añadió su
reconocimiento por par completo, tolerando duplicados y descartando pares
incompletos/interrumpidos. No se probó mantener el central por su apagado físico.
La captura no permite garantizar si su firmware emite también este par al
comenzar una pulsación larga; el software no genera repetición para el central.

El monitor actualizado arrancó como PID11584. La configuración local asigna
central=powerpoint y conserva superior/izquierdo=previous, inferior/derecho=next.
Tras confirmar el usuario PowerPoint en primer plano, se activó el modo
presentador a las 21:18:53. La prueba funcional del central está en curso.

### Validación de PowerPoint y central como conmutador

El usuario confirmó que el central iniciaba la presentación y pidió que una
segunda pulsación saliera. Se corrigió `send_key`: para el perfil PowerPoint
consulta la clase de la ventana en primer plano; screenClass/PodiumParent
reciben Escape, edición recibe Shift+F5. No mantiene un contador que se pueda
desincronizar al salir con el teclado. El usuario confirmó entrada y salida.

Con el monitor PID7780, el usuario confirmó diez avances correctos con derecho
y diez retrocesos con izquierdo, volviendo al punto de partida y sin saltos
extra. El registro conserva diez GESTO right entre 21:25:05 y 21:25:13 y la
serie posterior de retrocesos. No hubo errores de emisión. La inspección de
PowerPoint antes de la prueba mostraba diapositiva 1 de 27. La activación por
Computer Use falló; la prueba se ejecutó físicamente con el anillo.

Se desactivó emisión y se preparó central=xaringan mientras el usuario abre
esa aplicación. La validación de xaringan, Google Slides y recuperación tras
apagar/encender sigue pendiente. Se añadieron a las pruebas las capturas vendor
de superior mantenido (relleno a cinco bytes) y derecho mantenido.

### xaringan validado y perfil Google Slides en prueba

El usuario confirmó en xaringan diez avances con inferior, diez retrocesos con
superior y entrada/salida de pantalla completa con central (F). No informó
saltos extra ni cambios de volumen. El monitor se mantuvo activo durante estas
pruebas, sin errores de emisión. Se desactivó temporalmente para cambiar perfil.

Para Google Slides se añadió Ctrl+F5 desde edición y Escape cuando la ventana
en primer plano ocupa el monitor completo sin marco. Se usan límites físicos
DWM para evitar mezclar escalas DPI, comparados con MONITORINFO. La detección
es para presentación a pantalla completa; no identifica una presentación que
se haya dejado en ventana ni diferencia la pantalla completa manual F11.
La función principal de avance/retroceso no depende de esa detección.
Hay pruebas de límites de pantalla, coordenadas negativas, ventana maximizada
con marco y error de consulta. El monitor PID9256 cargó central=google y activó
emisión tras confirmar el usuario Google Slides en primer plano.

El usuario confirmó en Google Slides la entrada con central y salida de
pantalla completa en la segunda pulsación, diez avances con derecho y diez
retrocesos con izquierdo. Los tres entornos han pasado 10 avances y 10
retrocesos cada uno. Se está completando la prueba de repetición/liberación
con inferior mantenido y después la recuperación tras apagar/encender.

La prueba de inferior mantenido en Google Slides encontró un fallo real: no
avanzaba. Raw Input entregaba `0301000019`/`0300000019`, mientras la primera
captura vendor tenía relleno cero. El mapa define ID3 con solo 24 bits: el
quinto byte del paquete de cinco bytes es relleno no especificado y conservaba
0x19 de un informe anterior. El decodificador lo rechazaba equivocadamente.

Se añadió la captura fallida (seis pares) al fixture y se reprodujo el fallo
antes de corregirlo. Ahora ID3 interpreta exclusivamente sus tres bytes de
datos y acepta el tamaño común de Raw Input sin exigir relleno cero. Se
comprueban también los 256 valores posibles del byte de relleno, duplicados
y liberación. No se modificó el kernel. Monitor PID10308 cargó la corrección;
la repetición física se está comprobando de nuevo.

El usuario confirmó que con la corrección el inferior mantenido avanza
repetidamente, deja de avanzar al soltar y no cambia el volumen. Pasan 43
pruebas Python. Se mantuvo el PID10308 y se desactivaron las teclas para
comenzar la prueba de apagado/reconexión con el mismo proceso.

### Reconexión física verificada

El usuario confirmó el apagado; WinRT informó DISCONNECTED y el monitor
PID10308 seguía vivo (inicio 21:36:12), con emisión desactivada. Tras confirmar
el encendido, WinRT informó CONNECTED y el HID vendor siguió OK. No se
reinició el monitor ni se reinstaló/reaplicó el filtro. Llegaron nuevos
informes al mismo proceso. Se reactivó la emisión y el usuario confirmó que
una pulsación del derecho avanzó exactamente una vez en Google Slides.

El inicio automático se revisó con `monitor_logon.ps1 -Action Install -WhatIf`;
no existía tarea JX05 Monitor. Se solicitó la confirmación prevista antes de
registrarla. Falta cerrar el periodo final de uso de cinco minutos.

### Selección automática y música residual (2026-11-05, noche)

El usuario amplió el alcance: presentación prioritaria siempre que PowerPoint,
xaringan o Google Slides estén en primer plano, incluso en edición. Fuera de
ellos: izquierdo/anterior, derecho/siguiente, central pausa/reanuda (también
desde pausa), superior/inferior volumen; mantener direcciones repite. xaringan
se usa local y en webs públicas. Por ahora se excluyen reproductores de navegador.

Se añadió un hilo de selección al monitor y un componente C++ de usuario,
compilado con las herramientas existentes, sin modificar el filtro ni BitLocker.
La URL de la pestaña se consulta por accesibilidad; HTML local/público permite
identificar remark. Ventanas desconocidas quedan inactivas. Las órdenes se
invalidan al desactivar, cambiar de ventana/dispositivo o caducar. Las sesiones
SMTC admiten únicamente tipo Music y procesos ajenos a los navegadores.

VLC instalado es 3.0.24 y no presentó sesión SMTC. Se añadió una vía dirigida
WM_APPCOMMAND, confirmada en el código oficial de VideoLAN:
https://raw.githubusercontent.com/videolan/vlc/3.0.x/modules/gui/qt/main_interface_win32.cpp
Solo se admite una ventana de vlc.exe con título predeterminado de elemento
cargado. No se inspecciona si ese elemento es audio o vídeo: el usuario debe
usar VLC con música. VLC tiene prioridad sobre las sesiones SMTC si está cargado.
No se instalaron plugins ni se cambiaron opciones de VLC.

Una sonda inicial quedó detenida al liberar objetos COM locales al hilo al
salir. Se eliminó ese almacenamiento y se acotó la vida COM a cada llamada.
La sonda nueva terminó normalmente y detectó VLC sin acciones. Se apartó la
DLL antigua bloqueada a build/context/jx05_context-old.dll. La DLL actual tiene
SHA256 EB4A87E10B2E97228F22091AA8259644C362B539A00A56589F00857AB29176D5.
49 pruebas Python pasan: prioridad, mapeo, páginas locales/web, fallo de consulta,
anulación de órdenes en vuelo, música pausada, volumen y regresiones HID.

Se detuvo PID10308 y se inició oculto PID5364 con emisión desactivada, mapa
central=present. El usuario pidió continuar probando antes de descansar; se
activó el control. A las 22:13:51 y 22:13:55 se registraron dos play-pause y el
usuario confirmó que VLC pausa/reanuda. Pistas, volumen y prioridad automática
siguen en validación. La vía SMTC de otros reproductores aún no se ha probado
físicamente; una consulta sin VLC devolvió timeout, por lo que no se da por
validada esa compatibilidad.

El usuario confirmó anterior/siguiente en VLC, repetición del derecho durante
tres segundos y parada al soltar, y superior/inferior para volumen. Manteniendo
VLC abierto, confirmó el cambio automático a Google Slides, xaringan y
PowerPoint: central y avance operaron únicamente en la presentación. El registro
coincide con los contextos google, xaringan y powerpoint. PID5364 operó desde
22:12:50 hasta 22:18, con más de cinco minutos de pruebas y sin errores.

El usuario autorizó registrar JX05 Monitor al iniciar sesión. Se instaló la
tarea Interactive/Limited para Andresito, sin consola y con emisión inicialmente
desactivada. Se detuvo el monitor anterior y se inició desde la tarea: PID14376
arrancó desactivado, luego recibió acciones al habilitarlo. No se reinició Windows.

El usuario indicó que el superior subía poco el volumen. El registro mostraba
órdenes correctas; pidió explícitamente pasos de 5 puntos porcentuales. Se
sustituyeron las teclas de volumen por IAudioEndpointVolume sobre la salida
multimedia predeterminada de Windows, con límites 0..100. No se cambia el volumen
interno de VLC ni se modifica el estado de silencio. Se añadió lectura de volumen
para diagnóstico. También se corrigió la consulta de un servicio SMTC no disponible:
ahora equivale a no tener reproductor, sin desactivar las presentaciones; los
errores al ejecutar órdenes siguen desactivando el control.

Compilación /W4 /WX correcta, DLL SHA256
4C5D0C1A810480033154D7AEBBF09254C8FF696CAC607FAB7C0886B7CD15792F.
Pasan 51 pruebas Python, incluyendo cambio de pestaña en la misma ventana,
consulta multimedia fallida, volumen y regresiones anteriores. La tarea se volvió
a iniciar sin duplicados: PID8140, emisión inicialmente desactivada. Tras
habilitarla, el usuario confirmó «Sí, así está bien» para el paso de volumen.
La lectura inicial era 10%; tras una subida, dos bajadas y otra subida, volvió
a 10%, coherente con las cuatro acciones registradas. Hubo más pruebas manuales
de volumen posteriores, sin errores. El monitor queda activo y habilitado.

Quedan como límites de validación: otros reproductores SMTC y un inicio real
de sesión de Windows; la tarea sí fue probada manualmente con permisos normales.
No se solicitó otro reinicio ni se volvió a suspender BitLocker.

### Aplicación instalable e inicio activo (2026-11-05)

El usuario pidió que arrancase sola y activa, y convertirla en un programa con
su controlador para instalar en otros computadores. Aclaró «Mi mismo anillo
primero». Esta preferencia sustituye el arranque desactivado acordado anteriormente.
No se generalizó el filtro a hardware desconocido: siguen fijados el anillo y el
HWID del adaptador probado. Se explicó que para distribución normal falta firma
Microsoft y validación de otros adaptadores.

Se creó el paquete piloto 0.2.0: JX05.exe (lanzador nativo), runtime CPython privado
3.15.2 x64, módulos existentes, DLL de contexto y driver 0.1.0.2 ya firmado.
Runtime descargado desde python.org y verificado contra SHA256 publicado
D012F3AA29CF07436DAE8AEA1FEC0FD195C2612A0B059B1F915AE0AFB9AD1F62.
Incluye licencia Python. No se instaló Python global ni se compiló/modificó el
kernel. El programa no requiere Anaconda ni el repositorio en el PC de destino.

Install.ps1 comprueba integridad, instala por usuario, conserva mapeo, crea
accesos en Inicio y registro de desinstalación y registra la tarea sin elevación.
El driver se comprueba/instala separadamente con Driver.ps1: verifica hardware,
anillo, hashes y modo de prueba; requiere administrador y confirmación explícita
para importar su certificado e instalar. No cambia BCD, BitLocker ni Secure Boot,
y no reinicia Windows. Se confirmó en solo lectura que el driver cargado coincide
con el paquete; no se reinstaló. El monitor solo registra ahora la colección
vendor FF00:0001; la captura de diagnóstico conserva las colecciones antiguas.

Pasan 53 pruebas Python con el entorno anterior y con el runtime incluido, más
las pruebas PowerShell de inicio, sintaxis de instaladores, WhatIf, rechazo de
binario modificado y hardware desconocido. Se instaló realmente en
%LOCALAPPDATA%\Programs\JX05, con datos en %LOCALAPPDATA%\JX05. Se migró buttons.json.
Se probó también la actualización: conserva exactamente el hash del mapeo,
detiene el monitor previo y vuelve a iniciarlo. Desinstalación comprobada con
WhatIf; no se borraron archivos. La aplicación desinstalada conservaría datos
y controlador; la guía incluye retirada separada del filtro.

La tarea JX05 Monitor apunta a JX05.exe --run --enabled, Interactive/Limited para
Andresito. El estado mostró started_enabled=true y presenter_enabled=true sin
enviar después una orden de activación. BitLocker permaneció On. El usuario
confirmó que el central sigue pausando/reanudando VLC con la aplicación instalada.

Paquete: build/JX05-0.2.0-win-x64.zip, SHA256
19BBFA8A918BDFED54423F8CF77726A4465413640688107588571B15CE4B032C.
Baseline anterior al reinicio real en .jx05-monitor/app-reboot-baseline.json;
tarea exportada en task-installed-app.xml. Se espera el reinicio manual del
usuario para confirmar un inicio real de sesión; no se da esa prueba por hecha.

### Inicio real verificado y volumen independiente (0.2.1)

Tras volver el usuario, Windows informó LastBootUpTime 2026-11-06T01:45:48.500Z,
posterior al baseline 00:06:07.500Z. La tarea corrió a 01:46:00Z y el monitor
PID6544 inició a 01:46:06.850Z, con started_enabled=true, presenter_enabled=true
y sin errores. Ya había recibido 183 informes y ejecutado 17 acciones. Jx05Mtu
seguía Running y BitLocker On. Se actualizó app-reboot-baseline.json con esta
evidencia. No se inició ni habilitó manualmente el monitor para esa comprobación.

El usuario observó que sin VLC no funcionaba el volumen. La regla anterior
condicionaba todos los controles residuales a un reproductor disponible.
0.2.1 permite superior/inferior para volumen en contexto other aunque no haya
sesión musical; evita consultar el servicio multimedia para esas órdenes.
Presentaciones siguen teniendo prioridad, ventanas desconocidas siguen inactivas
y pistas/pausa siguen requiriendo reproductor. Pasan 54 pruebas Python.
Se reconstruyó e instaló el paquete conservando mapeo, tarea y controlador.
ZIP build/JX05-0.2.1-win-x64.zip, SHA256
0BE945E255AE74A6C981D5A6E48351975F1379C3C2DBFDCB72809A0B3BD88652.
Pendiente en este punto confirmar físicamente el volumen sin VLC.

La comprobación física posterior confirmó ambas direcciones sin reproductor
disponible (consulta nativa media=0): el usuario mantuvo inferior unos tres
segundos y confirmó descenso repetido y parada al soltar; también mantuvo
superior y confirmó subida repetida y parada al soltar. El registro contiene
las órdenes volume-down y cinco volume-up durante la pulsación superior de
22:58:46 a 22:58:49, sin errores. Hubo pulsaciones adicionales del usuario,
por lo que no se atribuye el nivel final a una única pulsación.
Pasan las 14 pruebas de gestos/contexto; reproducir las capturas reales de
superior/inferior mantenidos produjo respectivamente 4 y 6 órdenes de volumen
con media_available=False. No se cambiaron código, controlador ni arranque
durante esta validación. La versión 0.2.1 queda activa.

### Piloto 0.2.2: aceleración de volumen

El usuario pidió pasos de 10 puntos por repetición al mantener tres segundos
o más, conservando 5 para pulsaciones cortas. Se mide duración únicamente en
los informes ID3 de repetición de superior/inferior, conservando la cuenta entre
los ceros internos del firmware. Silencio superior a un segundo, cambio de
dirección, otro gesto o reinicio del decodificador reinician la cuenta. No hay
una señal independiente inequívoca de liberación física: el umbral se mide
desde el primer informe de repetición recibido, no desde el contacto mecánico.

Router transporta la duración y aplica paso 10 solo al volumen; las diapositivas
siguen generando una acción por gesto. JxVolume admite dos pasos de 5 puntos en
una única operación Core Audio y conserva límites 0..100. El registro incluye
volume_step, volume_percent y held_seconds. Pasan 56 pruebas, con frontera 2.99/3,
ambas direcciones, regreso a pulsación corta, duplicados y liberaciones internas.
DLL de usuario compilada con /W4 /WX, SHA256
414C0F075B11D2429A7BA9E228B69B08B4A624B9F72DAEF049DB3DC41B1796EA.
Se actualizó la instalación a 0.2.2, PID1980, activa y sin errores; kernel intacto.

En la prueba física solicitada, la captura registró tres descensos de 5 puntos,
40→35→30→25, con duraciones 0, 0.733 y 1.483 segundos. Aunque el usuario contestó
que terminó, esa captura no demuestra alcanzar el umbral de 3 segundos ni el
regreso posterior a 5. Se informó esta limitación y se conserva como pendiente
de validación física, sin darla por aprobada. El usuario pidió cerrar una versión
funcional preliminar empaquetada.

Paquete preliminar: build/JX05-0.2.2-win-x64.zip, SHA256
A9AEBAABDFA617F1826E3C7311097D47D9CF9DB325DD52C9D9EE77C0B8F2312A.
