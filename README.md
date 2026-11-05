# JX-05 en Windows

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

Comparte los resultados de cada botón y los identificadores de dispositivo para decidir si basta una aplicación de remapeo o se necesita investigar informes HID adicionales. No se ha probado con hardware real.

## Registro de desconexión en tiempo real

En Windows, abre PowerShell en esta carpeta y ejecuta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\registro-bluetooth.ps1 -Segundos 120
```

Mientras corre, intenta emparejar o conectar el anillo y espera a que Windows lo desconecte. Se mostrarán eventos disponibles de Bluetooth y Plug and Play y cambios de estado de dispositivos llamados JX-05; también se guardarán en un archivo `jx05-log-*.txt` en la carpeta actual. Algunos canales pueden estar desactivados o requerir permisos de administrador: el script indica cuáles puede leer y no cambia su configuración. Si es necesario, vuelve a ejecutarlo desde PowerShell como administrador. Los eventos incluyen información de otros dispositivos y pueden contener identificadores: revisa el archivo antes de compartirlo. El registro depende de los eventos que Windows emita y no garantiza revelar la causa. No ha sido probado en Windows ni con el dispositivo.
