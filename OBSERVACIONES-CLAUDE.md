# Observaciones de revisión de Claude — 2026-11-08

Estas observaciones se revisaron en el código; quedan registradas para futuras pruebas de paquetes y hardware.

1. **Errores del transporte Bumble:** el bucle de reapertura reintentaba sin reflejar la causa en el estado y podía ocultar errores de firmware. Se registra la causa del reintento, se limpia al quedar listo y los errores de archivos durante el encendido se propagan.
2. **Posible falta de colorama en el lock:** Claude planteó que Click lo requiere en Windows. El wheel fijado de Click 8.5.1 no declara dependencias `Requires-Dist`, por lo que esta hipótesis no quedó confirmada y el lock no se cambió. No se ejecutó una compilación completa del paquete Bumble.
3. **Backend elegido por firmware residual:** al instalar la variante driver sobre Bumble podía quedar `rtk-firmware/` y seleccionar el backend incorrecto. Cada variante ahora incluye `backend.txt` y el monitor lo usa para seleccionar el backend.
4. **Parada durante conexión:** el encendido y la conexión podían exceder los diez segundos que esperan instalación y desinstalación. La parada cancela la tarea de transporte y se limita la espera de desconexión. Falta verificar el comportamiento con el dongle y el anillo físicos; el cierre del transporte también depende de Bumble y del controlador.
5. **Nombres de firmware duplicados:** la autocomprobación repetía los nombres del descargador. El paquete Bumble incluye ahora el módulo del descargador y consulta su lista.

La suite de Python pasó con 67 pruebas después de los cambios. No se reprodujeron todos los escenarios originales en hardware ni se validó una actualización real entre variantes.
