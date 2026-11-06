# JX-05 como pasador en Windows 11

Prototipo para este anillo y este PC. El filtro 0.1.0.1 permitió iniciar HID y
recibir botones; el usuario confirmó movimiento de diapositivas en PowerPoint,
pero aparecieron cambios de volumen y selección de texto. La versión 0.1.0.2
está cargada como **oem3.inf**. Tras renovar el emparejamiento, Windows reconoce
la colección vendor corregida. El usuario confirmó que mantener el derecho ya
no selecciona texto/mueve el puntero y mantener el superior no cambia volumen.
PowerPoint, xaringan y Google Slides pasaron diez avances y diez retrocesos
cada uno. El usuario confirmó también la función del central en los tres.
La recuperación tras apagar/encender y la prueba final de repetición siguen
pendientes en este punto.

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

Siempre arranca con emisión desactivada. Antes de activarla, pon la presentación
en primer plano: las teclas van a la ventana activa. Superior/izquierdo
retroceden; inferior/derecho avanzan. Mantener pulsado repite aproximadamente
cada 750 ms mientras llegan informes. Soltar detiene la repetición. La
identificación se basa en ocho capturas confirmadas, no en códigos supuestos.

Raw Input escucha en una ventana oculta y sigue los cambios de dispositivos;
Windows gestiona la reconexión HID. Se descartan gestos incompletos al cambiar
dispositivo o tras un intervalo sin informes. La recuperación real tras apagar
el anillo sigue pendiente. El antiguo observador Bleak se conserva como ayuda
de diagnóstico, pero --run ya utiliza HID, no AE02/AE42.

El estado está en `.jx05-monitor/status.json`, y el registro rotativo en
`.jx05-monitor/events.log` (2 MB, dos copias). Revisa `running`, `updated`,
`presenter_enabled`, `packets`, `actions`, `error` y `mapping`.
`ESCUCHANDO_HID` acredita el registro de escucha, no que están llegando botones.
Un mutex evita dos monitores simultáneos. `--stop` debe terminar en running=false.

## Módulo breve de mapeo

```powershell
& 'C:\ProgramData\anaconda3\python.exe' tools/map_jx05.py
& 'C:\ProgramData\anaconda3\python.exe' tools/map_jx05.py --show
```

El asistente permite asignar avanzar, retroceder o ninguna función a cada
botón direccional, con el teclado del PC; no hay que pulsar el anillo.
Guarda `.jx05-monitor/buttons.json`. Para aplicar cambios al monitor activo,
desactiva y vuelve a activar el modo presentador. Un mapa inválido impide la
emisión en lugar de aplicar funciones inesperadas.

Para el central permite guardar una preferencia: entrar/salir de PowerPoint
(Shift+F5 desde la diapositiva actual, Escape para salir), presentar Google Slides
(Ctrl+F5; Escape si está a pantalla completa) o alternar
pantalla completa en xaringan (F). La señal corta del central está calibrada
con una captura confirmada y se reconoce al completar el par de informes.
Se debe elegir la
aplicación apropiada; no existe detección automática. El central empieza sin
asignar. Mantenerlo tres segundos o más apaga físicamente el anillo, según el
usuario: no se utiliza como gesto de presentación ni se pide probarlo mantenido.
En Google Slides la salida se detecta por pantalla completa, no por el contenido
de la página: no cubre presentaciones en ventana ni distingue el F11 manual del
navegador. Usa el perfil con la presentación en primer plano.

Fuentes de los atajos: [PowerPoint](https://support.microsoft.com/en-us/accessibility/powerpoint/use-keyboard-shortcuts-to-deliver-powerpoint-presentations),
[Google Slides](https://support.google.com/docs/answer/1696717/keyboard-shortcuts-for-google-slides-computer),
[remark/xaringan](https://github.com/gnab/remark/wiki/Keyboard-shortcuts).

## Inicio de sesión y verificación

No hay tarea de inicio instalada. `tools/monitor_logon.ps1` prepara la tarea
por usuario JX05 Monitor, sin consola ni elevación. Requiere autorización antes
de registrarla. Se puede revisar con `-Action Install -WhatIf`; tras aprobación,
`-Action Install` registra y `-Action Uninstall` retira solo esa tarea.
El monitor empieza desactivado también al iniciar sesión.

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests
```

Pruebas automatizadas: informes reales, duplicados, liberaciones, pausas y
reinicios de contactos durante una pulsación mantenida, mapeo y envío de teclas
con limpieza de modificadores ante un envío parcial. La compilación del filtro
incluye pruebas C con AddressSanitizer y análisis estático.

Pendiente: cerrar la prueba de uso/repetición y recuperación tras apagar/encender.
No confundir una prueba de decodificación con una prueba de presentación real.

[Investigación y evidencia](INVESTIGACION.md) · [Filtro, instalación y reversión](driver/README.md)
