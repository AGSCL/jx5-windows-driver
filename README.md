# JX-05 en Windows

## Estado confirmado en el PC

- La sesión GATT se mantuvo activa durante 60 segundos en una prueba real.
- Windows descubre el servicio HID `1812`, pero devuelve `DENIED_BY_SYSTEM`
  al solicitar acceso desde WinRT. No se llegó a suscribir informes.
- La API nativa Win32 sí abrió el dispositivo y enumeró 12 características HID,
  incluidas seis Report con capacidad de notificación. Aún no se han suscrito.
- El registro de callbacks por el handle del dispositivo falló en los seis Report
  con `0x80070001`. No apareció una interfaz del servicio HID y no se habilitaron
  notificaciones. El bloqueo pendiente es acceder a esa interfaz de servicio.
- El controlador HID `hidbthle.inf` sigue con código 10 y estado `0xC00000E5`.
- Se probó temporalmente el genérico ATT: inició sin errores y expuso interfaces
  HID, pero su apertura de lectura/escritura devolvió «acceso denegado». Al
  recrearse la instancia del anillo, Windows volvió a seleccionar `hidbthle.inf`.
- Hay un prototipo KMDF compilado y firmado para pruebas que intenta negociar
  MTU 23 solo en la conexión del anillo. No está instalado ni ha recibido botones;
  su eficacia sigue sin comprobarse. Véase [driver/README.md](driver/README.md).
- El observador Bleak consiguió suscribirse a AE02 y AE42. Tras las pulsaciones
  confirmadas (derecha, arriba, arriba) no recibió paquetes; se detuvo esta vía.
  Hubo que ejecutarlo fuera del entorno restringido del agente para acceder al
  dispositivo. El pasador de diapositivas sigue sin funcionar.

Los resultados y la salida del diagnóstico están en
[INVESTIGACION.md](INVESTIGACION.md). La vía AE02/AE42 se detuvo sin recibir datos.
La siguiente prueba propuesta es el filtro MTU experimental, que necesita
aprobación para intervenir en el adaptador y habilitar carga de prueba con reinicio.
Mantener GATT activo no corrige por sí
solo el error HID. El trabajo continúa con el PC y el anillo actuales, sin
modificar el firmware ni añadir hardware.

## Monitor continuo del JX-05

La validación de la captura original encontró Report Reference de entradas IDs
1–6 y salida ID 1. El prefijo HID de 126 bytes solo define entradas 1 y 3; aún
no es un mapa validado para un filtro corrector. El analizador y las pruebas
con bytes reales están descritos en [INVESTIGACION.md](INVESTIGACION.md).

`tools/monitor_jx05.py --run` conecta al anillo `B7:FC:01:C6:F3:7E`, redescubre
las características AE02/AE42 y solicita notificaciones por objeto con Bleak.
Usa el Python y Bleak existentes; no requiere SDK ni elevación. No instala ni
reaplica controladores, no envía comandos propietarios y no emite teclas.
La suscripción sí solicita al dispositivo habilitar notificaciones GATT.
Cada paquete se registra con hora UTC, UUID, handle actual y bytes completos.
Los paquetes repetidos se conservan para identificar pulsación, gesto y liberación.

Inicio oculto, consulta y parada desde esta carpeta:

```powershell
$monitorScript = Join-Path (Get-Location) 'tools/monitor_jx05.py'
Start-Process 'C:\ProgramData\anaconda3\pythonw.exe' -ArgumentList ('"' + $monitorScript + '" --run') -WindowStyle Hidden
& 'C:\ProgramData\anaconda3\python.exe' tools/monitor_jx05.py --status
& 'C:\ProgramData\anaconda3\python.exe' tools/monitor_jx05.py --stop
```

El estado está en `.jx05-monitor/status.json`; el registro rotativo, en
`.jx05-monitor/events.log` (2 MB y dos copias). Comprueba la fecha `updated`.
`ESCUCHANDO` confirma al menos una suscripción; `subscriptions` identifica cuáles.
`BLOQUEADO` indica que ninguna se aceptó y el registro detalla los errores.
`packets` cuenta notificaciones, no botones identificados. Un escaneo fallido
no demuestra denegación de acceso. La reconexión espera 2, 4, 8… hasta 60 segundos;
una conexión de al menos 60 segundos restablece esa espera. `--stop` también
interrumpe el escaneo, la suscripción y la espera. Un mutex impide dos monitores
en la misma sesión de Windows.

Antes de pedir una pulsación hay que comprobar `ESCUCHANDO`. Se prueba un botón
cada vez y se espera confirmación del usuario; apagar/encender requiere también
su confirmación antes de reanudar. Si no hay paquetes correlacionados, se detiene
esta vía con `--stop`. No se cambia automáticamente a otro controlador.

El modo presentador permanece desactivado (`presenter_enabled=false`). Todavía
no se implementa SendInput: falta identificar paquetes reales y sus liberaciones.
El botón central no tiene asignación. Quedan pendientes diez avances y diez
retrocesos en cada entorno (PowerPoint, xaringan y Google Slides en primer plano),
cinco minutos de uso y recuperación tras apagar/encender.

La ejecución en segundo plano dura hasta detenerla, cerrar la sesión de Windows
o reiniciar el equipo; no se instaló inicio automático. Pararla libera GATT y
conserva el controlador asociado. Para restaurar la asociación HID original, detén primero
el monitor y usa `tools/select_ring_driver.py --instance <instancia> --apply restore`
como administrador, con la instancia exacta indicada en el estado. Restaurar
el controlador original puede devolver el error de controlador observado antes.

`tools/monitor_logon.ps1` prepara una tarea por usuario llamada **JX05 Monitor**,
con `pythonw.exe`, sin consola y sin privilegios elevados. El registro requiere
confirmación del usuario; por ahora solo se ha preparado el script. Se puede
revisar sin registrar nada:

```powershell
./tools/monitor_logon.ps1 -Action Install -WhatIf
```

Tras confirmar, `-Action Install` la registra para el siguiente inicio de sesión.
No sustituye una tarea existente. Para desinstalar, solicita primero `--stop` y
espera `running=false`; luego ejecuta `./tools/monitor_logon.ps1 -Action Uninstall`.
La desinstalación conserva los registros y no cambia controladores. Si Windows
deniega el registro de tareas, el inicio manual oculto sigue disponible.

## Prueba experimental de acceso directo (GATT)

Para comprobar primero la estabilidad de una sesión GATT en Windows:

```powershell
python tools/probe_gatt_session.py
```

Enciende el anillo antes de iniciar. El programa espera un anuncio del JX-05,
utiliza el tipo de dirección anunciado y solicita `GattSession.MaintainConnection`.
Espera hasta 30 segundos por la activación y mide 60 segundos desde `ACTIVE`.
`SESION_ESTABLE` confirma esa duración; `SESION_PERDIDA` informa cuánto duró.
Al terminar libera su sesión. Esta prueba no suscribe informes ni solicita leer
Report Map; Windows puede iniciar HID por su cuenta. Requiere las mismas
dependencias indicadas abajo. Se puede seleccionar el anillo con `--address`.

Para comprobar el acceso al servicio HID al activar la sesión:

```powershell
python tools/probe_gatt_session.py --check-hid
```

Esta opción consulta el servicio 1812, solicita acceso y enumera sus
características. Muestra los estados de Windows, incluidos `ACCESS_DENIED` o
`DENIED_BY_SYSTEM` cuando correspondan. No lee valores ni habilita notificaciones.
`HID_ENUMERADO` confirma la enumeración; aún no demuestra recepción de botones.

Esta prueba intenta suscribirse a los informes del anillo. Todavía no controla
PowerPoint. Windows puede reservar el servicio HID o desconectar el dispositivo;
el resultado permite decidir si una aplicación puede recibir los botones.

Desde la carpeta del repositorio, con Python instalado, ejecuta por separado:

```powershell
python -m pip install "bleak>=1,<3"
```

```powershell
python tools/probe_gatt.py
```

Enciende el anillo, activa Bluetooth en Windows y desconecta el anillo del teléfono.
Mantén su emparejamiento con Windows si ya existe. Si no se detecta, ponlo en modo
de emparejamiento. Cuando aparezca `ESCUCHANDO`, pulsa cada botón por separado
durante los 60 segundos de la prueba. Copia la salida completa. `INFORME` indica
datos recibidos; `HID_NO_VISIBLE`, errores de acceso o desconexiones son resultados
relevantes, no una indicación para repetir indefinidamente la prueba.

El programa habilita notificaciones GATT y cierra su conexión al terminar. No
solicita leer Report Map, pero Windows puede leerlo automáticamente durante la
conexión. Las pruebas automatizadas usan simulaciones: la conexión real debe
validarse en Windows con el anillo. Si tu Python no está en PATH, sustituye
`python` por `& "ruta\a\python.exe"` en PowerShell.

Base de diagnóstico para el mando Bluetooth ALLOYSEED JX-05. El manual disponible no documenta sus descriptores HID ni los códigos que transmite; por tanto, todavía no se puede determinar si necesita un controlador adicional ni implementar un mapeo fiable. Windows puede reconocer dispositivos Bluetooth HID mediante sus controladores integrados.

## Primer diagnóstico en Windows 10/11

1. Carga el anillo, mantén pulsado el botón central hasta que parpadee y empareja **JX-05** en Configuración > Bluetooth y dispositivos.
2. Abre PowerShell en la carpeta del proyecto y ejecuta:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\diagnostico.ps1
   ```

3. Selecciona la ventana de diagnóstico. Pulsa y mantén cada botón por separado y anota qué botón produce cada línea. Prueba también la doble pulsación central.
4. Para inspeccionar los dispositivos detectados, ejecuta `Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match 'JX-05' } | Format-List FriendlyName,Class,InstanceId,Status` en PowerShell. El nombre puede no aparecer en cada interfaz HID asociada.

La ventana solo muestra eventos de teclado recibidos mientras tiene el foco. No distingue el anillo de otros teclados y puede no mostrar eventos multimedia, ratón, táctiles o informes HID propietarios. La ausencia de eventos no demuestra que el dispositivo esté averiado. No se instala ningún controlador ni se modifican ajustes del sistema.

Comparte los resultados de cada botón y los identificadores de dispositivo para decidir si basta una aplicación de remapeo o se necesita investigar informes HID adicionales. La prueba de teclado no se ha validado con eventos del anillo; las pruebas GATT reales se documentan en INVESTIGACION.md.

## Registro de desconexión en tiempo real

En Windows, abre PowerShell en esta carpeta y ejecuta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\registro-bluetooth.ps1 -Segundos 120
```

Mientras corre, intenta emparejar o conectar el anillo y espera a que Windows lo desconecte. Se mostrarán eventos disponibles de Bluetooth y Plug and Play y cambios de estado de dispositivos llamados JX-05; también se guardarán en un archivo `jx05-log-*.txt` en la carpeta actual. Algunos canales pueden estar desactivados o requerir permisos de administrador: el script indica cuáles puede leer y no cambia su configuración. Si es necesario, vuelve a ejecutarlo desde PowerShell como administrador. Los eventos incluyen información de otros dispositivos y pueden contener identificadores: revisa el archivo antes de compartirlo. El registro depende de los eventos que Windows emita y no garantiza revelar la causa. No ha sido probado en Windows ni con el dispositivo.
