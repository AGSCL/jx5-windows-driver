# JX-05 en Windows

## Estado confirmado en el PC

- La sesión GATT se mantuvo activa durante 60 segundos en una prueba real.
- Windows descubre el servicio HID `1812`, pero devuelve `DENIED_BY_SYSTEM`
  al solicitar acceso desde WinRT. No se llegó a suscribir informes.
- El controlador HID `hidbthle.inf` sigue con código 10 y estado `0xC00000E5`.
- Todavía no hay un controlador propio ni recepción de botones comprobada.

Los resultados y la salida del diagnóstico están en
[INVESTIGACION.md](INVESTIGACION.md). El siguiente paso es comprobar una vía
documentada para un controlador específico del servicio, antes de instalar
herramientas o cambiar controladores. Mantener GATT activo no corrige por sí
solo el error HID. El trabajo continúa con el PC y el anillo actuales, sin
modificar el firmware ni añadir hardware.

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
