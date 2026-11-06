# JX-05 como pasador en Windows 11

## Aplicación instalable 0.2.2 preliminar

Paquete piloto: `build/JX05-0.2.2-win-x64.zip`. Extrae todo y ejecuta
`Instalar.cmd` con tu usuario habitual. Incluye `JX05.exe`, Python privado,
el componente de contexto y el controlador firmado de prueba 0.1.0.2.
No requiere Anaconda ni herramientas de desarrollo en el equipo de destino.

La aplicación se instala en `%LOCALAPPDATA%\Programs\JX05`; datos y mapeo en
`%LOCALAPPDATA%\JX05`. En Inicio > JX05 están Iniciar, Activar, Pausar, Estado y
Botones. La tarea **JX05 Monitor inicia con los controles activos** al entrar en
Windows, según la nueva preferencia del usuario. No hace falta abrir una terminal.
La instalación y actualización están probadas aquí; se conservó el mapeo.
La desinstalación de la aplicación conserva datos y controlador.

Este piloto admite **el mismo anillo B7:FC:01:C6:F3:7E** y el adaptador probado
**USB 13D3:3567 rev0100 MI00**. `Driver.ps1` comprueba compatibilidad sin cambios;
`Instalar-controlador.cmd`, como administrador, permite instalarlo cuando Windows
ya está preparado para firma de prueba. Rechaza hardware distinto y no modifica
Secure Boot, BitLocker ni BCD. La aplicación solo traduce la interfaz vendor
corregida. Instalar la aplicación sola no corrige el HID original en otro PC.

Para otros adaptadores falta validación y para distribución normal falta firma
Microsoft. No es todavía un instalador universal o comercial. Consulta
`packaging/LEEME.txt` para requisitos y retirada del controlador.

Compilación reproducible del paquete: `tools/build_app.ps1`, con el runtime
oficial fijado y verificado por SHA-256, la DLL ya compilada y el paquete del
controlador ya firmado. El script no recompila ni vuelve a firmar el kernel.

Prototipo para este anillo y este PC. El filtro 0.1.0.1 permitió iniciar HID y
recibir botones; el usuario confirmó movimiento de diapositivas en PowerPoint,
pero aparecieron cambios de volumen y selección de texto. La versión 0.1.0.2
está cargada como **oem3.inf**. Tras renovar el emparejamiento, Windows reconoce
la colección vendor corregida. El usuario confirmó que mantener el derecho ya
no selecciona texto/mueve el puntero y mantener el superior no cambia volumen.
PowerPoint, xaringan y Google Slides pasaron diez avances y diez retrocesos
cada uno. El usuario confirmó también la función del central en los tres.
La repetición y la recuperación tras apagar/encender también fueron confirmadas.
La selección automática dio prioridad a los tres entornos mientras VLC estaba
abierto. En VLC se confirmaron pausa/reanudación, anterior/siguiente, repetición
y volumen.

El filtro mantiene el controlador MediaTek existente y corrige la lectura HID.
El monitor convierte los informes del anillo en teclas de la aplicación en
primer plano. No modifica el firmware. El monitor no instala filtros ni cambia
el arranque. La instalación experimental sí requirió herramientas WDK y modo
de firma de prueba, autorizados por el usuario. BitLocker está protegido.

## Uso del monitor

Desde esta carpeta, con el Python existente:

```powershell
$monitorScript = Join-Path (Get-Location) 'tools/monitor_jx05.py'
Start-Process 'C:\ProgramData\anaconda3\pythonw.exe' -ArgumentList ('"' + $monitorScript + '" --run') -WindowStyle Hidden
& 'C:\ProgramData\anaconda3\python.exe' tools/monitor_jx05.py --status
& 'C:\ProgramData\anaconda3\python.exe' tools/monitor_jx05.py --presenter-on
& 'C:\ProgramData\anaconda3\python.exe' tools/monitor_jx05.py --presenter-off
& 'C:\ProgramData\anaconda3\python.exe' tools/monitor_jx05.py --stop
```

En ejecución desde el código fuente, `--run` arranca desactivado y
`--run --enabled` arranca activo. La aplicación instalada usa la segunda opción.
`--presenter-on` habilita tanto las
presentaciones como la música residual; `--presenter-off` desactiva ambas.
Con una presentación reconocida en primer plano, superior/izquierdo
retroceden; inferior/derecho avanzan. Mantener pulsado repite aproximadamente
cada 750 ms mientras llegan informes. Soltar detiene la repetición. La
identificación se basa en ocho capturas confirmadas, no en códigos supuestos.

Raw Input escucha en una ventana oculta y sigue los cambios de dispositivos;
Windows gestiona la reconexión HID. Se descartan gestos incompletos al cambiar
dispositivo o tras un intervalo sin informes. La recuperación real tras apagar
el anillo fue confirmada con el mismo proceso. El antiguo observador Bleak se conserva como ayuda
de diagnóstico, pero --run ya utiliza HID, no AE02/AE42.

El estado está en `.jx05-monitor/status.json`, y el registro rotativo en
`.jx05-monitor/events.log` (2 MB, dos copias). Revisa `running`, `updated`,
`presenter_enabled`, `control_context`, `media_available`, `packets`, `actions`, `error` y `mapping`.
`ESCUCHANDO_HID` acredita el registro de escucha, no que están llegando botones.
Un mutex evita dos monitores simultáneos. `--stop` debe terminar en running=false.

## Módulo breve de mapeo

```powershell
& 'C:\ProgramData\anaconda3\python.exe' tools/map_jx05.py
& 'C:\ProgramData\anaconda3\python.exe' tools/map_jx05.py --show
```

El asistente permite asignar avanzar, retroceder o ninguna función a cada
botón direccional, con el teclado del PC; no hay que pulsar el anillo.
Guarda `%LOCALAPPDATA%\JX05\buttons.json` en la aplicación instalada o
`.jx05-monitor/buttons.json` al ejecutar desde el repositorio. Para aplicar cambios al monitor activo,
desactiva y vuelve a activar el modo presentador. Un mapa inválido impide la
emisión en lugar de aplicar funciones inesperadas.

Para el central permite guardar una preferencia: entrar/salir de PowerPoint
(Shift+F5 desde la diapositiva actual, Escape para salir), presentar Google Slides
(Ctrl+F5; Escape si está a pantalla completa) o alternar
pantalla completa en xaringan (F). La señal corta del central está calibrada
con una captura confirmada y se reconoce al completar el par de informes.
La opción 6 del asistente elige automáticamente según la aplicación en primer
plano; está seleccionada en este PC. El central empieza sin
asignar. Mantenerlo tres segundos o más apaga físicamente el anillo, según el
usuario: no se utiliza como gesto de presentación ni se pide probarlo mantenido.
En Google Slides la salida se detecta por pantalla completa, no por el contenido
de la página: no cubre presentaciones en ventana ni distingue el F11 manual del
navegador. Usa el perfil con la presentación en primer plano.

## Música residual y prioridad automática

PowerPoint y las pestañas reconocidas de Google Slides o xaringan tienen
prioridad, incluso en edición. Se reconoce PowerPoint por su proceso y las
pestañas por la URL visible mediante accesibilidad de Windows. Para xaringan
se lee el HTML local o público buscando marcadores de remark; las consultas
web no usan cookies ni credenciales y se guardan en memoria durante un minuto.
No se registran URLs, contenido de páginas ni títulos de canciones. Si no se
puede identificar una pestaña, el control queda inactivo en ella.

Fuera de las presentaciones, superior/inferior controlan el volumen de Windows
también sin reproductor abierto (desde 0.2.1). Si hay un reproductor compatible abierto con música
reproduciéndose o pausada: izquierdo/anterior, derecho/siguiente, central corto
pausa/reanuda y superior/inferior suben/bajan el volumen general de Windows
en 5 puntos porcentuales, limitado entre 0 y 100. Mantener los direccionales
durante tres segundos de informes continuos cambia el paso de volumen a 10 puntos
(0.2.2). El tiempo se mide desde el primer informe de repetición recibido.
Una pulsación corta vuelve a 5; una pausa de más de un segundo o un gesto distinto
reinicia la cuenta. El firmware envía liberaciones internas entre repeticiones,
por lo que no se puede tratar cada liberación como el fin de una pulsación física.
La aceleración pasó pruebas automáticas y queda pendiente de confirmación física
completa. Mantener los direccionales
repite; el central no repite. Se descartan órdenes al cambiar de ventana,
desactivar el control o superar un segundo de antigüedad.

La vía general usa sesiones musicales SMTC de Windows y excluye navegadores y
sesiones de tipo desconocido o vídeo. Los reproductores deben publicar esa
información. VLC 3 usa una vía específica de mensajes dirigidos a su ventana,
pues no publica SMTC: se admite una única ventana VLC con un elemento cargado
y título predeterminado. En VLC se supone que el elemento es música; esta vía
no inspecciona el tipo del archivo y también podría controlar un vídeo cargado.
VLC tiene prioridad si coexiste con otro reproductor; no se envían teclas
multimedia globales para cambiar pistas o pausar.

`tools/context_windows.cpp` es un componente de usuario, no un nuevo controlador.
`tools/build_context.ps1` lo compila con las herramientas ya presentes y deja
`build/context/jx05_context.dll`. Debe acompañar al monitor. No requiere reinicio
ni cambios de BitLocker. Detén el monitor antes de recompilarlo.

Fuentes de los atajos: [PowerPoint](https://support.microsoft.com/en-us/accessibility/powerpoint/use-keyboard-shortcuts-to-deliver-powerpoint-presentations),
[Google Slides](https://support.google.com/docs/answer/1696717/keyboard-shortcuts-for-google-slides-computer),
[remark/xaringan](https://github.com/gnab/remark/wiki/Keyboard-shortcuts).

## Inicio de sesión y verificación

La tarea de inicio JX05 Monitor quedó registrada con autorización del usuario,
sin consola ni elevación, apuntando a la aplicación instalada con `--run --enabled`.
`tools/monitor_logon.ps1` permite administrarla.
Se puede revisar con `-Action Install -WhatIf`; tras aprobación,
`-Action Install` registra y `-Action Uninstall` retira solo esa tarea.
La opción `-EnableControls` habilita las órdenes automáticamente al iniciar sesión.
`-Application` selecciona el ejecutable instalado; se mantiene la opción de Python
para trabajar desde el código fuente.

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests
```

Pruebas automatizadas: informes reales, duplicados, liberaciones, pausas y
reinicios de contactos durante una pulsación mantenida, mapeo y envío de teclas
con limpieza de modificadores ante un envío parcial. La compilación del filtro
incluye pruebas C con AddressSanitizer y análisis estático.

La versión 0.2.0 pasó 53 pruebas Python con Anaconda y con el Python privado del paquete;
0.2.1 pasó 54 pruebas y 0.2.2 pasa 56, incluyendo aceleración a los tres segundos,
prioridad de presentaciones, volumen sin reproductor y regreso a 5 puntos. Se
comprobaron además los scripts PowerShell, rechazo de archivos alterados y
hardware incompatible, instalación, actualización conservando el mapeo y la
desinstalación con `-WhatIf` (sin borrar).

La sesión de prueba de la selección automática y VLC duró más de cinco minutos
sin errores registrados. Después se ajustó el paso de volumen a 5 puntos y el
usuario confirmó que así está bien. Otros reproductores SMTC siguen pendientes de prueba
física. El arranque real de sesión quedó verificado después del reinicio del
2026-11-05 a las 22:45:48: JX05 inició solo y activo a las 22:46:06, con el
controlador funcionando y BitLocker protegido.
No confundir una prueba de decodificación con una prueba de presentación real.

[Investigación y evidencia](INVESTIGACION.md) · [Filtro, instalación y reversión](driver/README.md)
