# Prompt: estrategia para que el JX-05 funcione en Windows

Copia todo lo que está debajo de la línea en una sesión nueva de Claude Code (en el PC con Windows y el anillo).

---

Trabajas en el repo `jx5-windows-driver`. Lee `README.md` e `INVESTIGACION.md` antes de nada. No repitas experimentos ya documentados. Límites fijos: no tocar el firmware del anillo, no usar hardware extra, no tocar el controlador del adaptador Bluetooth.

## Lo que ya está demostrado (no lo vuelvas a probar)

- La sesión GATT se mantiene activa. Win32 enumera 7 servicios y 12 características HID (Report Map en el handle `0x0042`, 6 Report con notificación).
- El acceso desde modo usuario al servicio HID `1812` está **bloqueado por diseño**: WinRT da `DENIED_BY_SYSTEM`; Win32 da `0x80070001` con el handle del dispositivo y `0x80070005` con el handle del servicio, aunque la DACL dé FA a los administradores. El bloqueo sale de la pila (BthLEEnum), no de la DACL. **No sigas por esa vía** (ni bleak, ni DACL, ni otros modos de `CreateFileW`).
- El genérico `bthleenum.inf` (UmPass) arranca, pero no da acceso al HID. Windows vuelve a elegir `hidbthle.inf` cuando recrea la instancia.
- `hidbthle.inf` (UMDF `Microsoft.Bluetooth.Profiles.HidOverGatt.dll`, servicio `mshidumdf`, filtro inferior `WUDFRd`) falla con código 10 / `0xC00000E5`. Justo antes, en dos capturas independientes, las lecturas del Report Map son: offset 0 → 63 bytes, offset 63 → 63 bytes, offset 126 → **126 bytes en una PDU de 127 bytes con MTU 64**.

## Hipótesis central (compruébala primero, es barata)

El Report Map real mide **exactamente 126 bytes**: el prefijo recuperado ya está sintácticamente cerrado (Consumer Control con ID 3 y Touch Screen con ID 1). Como la segunda respuesta llenó el MTU (63 = MTU−1), Windows tiene que pedir un Read Blob con offset 126 == longitud. Un servidor correcto respondería un valor vacío. El firmware responde mal (parece que devuelve el mapa entero otra vez), la PDU supera el MTU, Windows la rechaza y HidOverGatt no arranca. Por eso el intercambio no supera los 126 bytes en ninguna de las siete repeticiones.

Si esto se confirma, todo el arreglo se reduce a una cosa: **entregarle a HidOverGatt el Report Map de 126 bytes (o una respuesta vacía para el offset 126) en lugar de dejar pasar el error**. El controlador HID de Microsoft hace el resto: suscribe los Report y crea las colecciones HID.

## Plan por fases. Cada fase tiene criterio de salida y se detiene si este falla.

### Fase 0: confirmar la hipótesis sin conexión (solo Python, sin Windows)
1. Amplía `tools/analyze_att.py` para guardar en hex el valor de cada respuesta del Report Map que supere el MTU. Son bytes ATT del handle `0x0042`. No exportes nada de SMP.
2. Ejecútalo sobre `.jx05-monitor/hid-start.xml` y sobre `jx05-amplio.xml` (archivos locales, no están en Git).
3. Compara la respuesta de 126 bytes con el prefijo: ¿es idéntica a `prefix[0:126]`? ¿Es una rotación, o trae bytes nuevos?
4. Valida con un parser mínimo de ítems HID (short items: el tamaño sale de los 2 bits bajos) que el prefijo de 126 bytes abre y cierra todas las colecciones y define los Report IDs que referencian los 6 Report.
5. Extrae de la misma captura las lecturas de los descriptores Report Reference (`0x2908`) de los 6 Report: el par (Report ID, tipo) de cada uno. Así sabes qué características usa el mapa.
6. Añade un test con los bytes reales (son públicos, no tienen nada sensible).

**Salida:** documento en `INVESTIGACION.md` con «respuesta = repetición del mapa → mapa de 126 bytes completo» (seguir) o «trae bytes nuevos» (reconstruir el mapa completo con esos bytes antes de la Fase 2).

### Fase 1: preparar el entorno (requiere al usuario; pídele permiso explícito)
- Instalar Visual Studio Build Tools + WDK (el SDK/WDK no está instalado).
- La firma de prueba exige **desactivar Secure Boot** en la BIOS/UEFI y ejecutar `bcdedit /set testsigning on`. Explícale el coste antes de hacerlo (afecta a BitLocker y a anti-cheat, y aparece una marca de agua) y no lo hagas sin su sí.
- Crear un punto de restauración. Deja documentada la reversión: borrar el valor `LowerFilters` de la instancia (también desde el modo seguro), `sc delete jx05filt`, `bcdedit /set testsigning off`.

### Fase 2: filtro KMDF inferior en modo PASIVO (solo observa)
- Driver KMDF mínimo `jx05filt.sys`, filtro inferior **solo en la instancia HID del anillo**. Se coloca debajo de `WUDFRd` y encima del PDO de BthLEEnum, con `SetupDiSetDeviceRegistryProperty(SPDRP_LOWERFILTERS)` sobre esa instancia. Comprueba en el registro el orden real de `LowerFilters` (el primero de la lista queda más cerca del PDO). Nada de filtro de clase, nada de INF que coincida con el hardware ID (otros anillos iguales usan el mismo).
- El servicio se crea con `sc create jx05filt type= kernel start= demand binPath= ...`. Reutiliza `tools/select_ring_driver.py` (ya valida dirección/VID/PID/UUID y rechaza otras instancias): añádele `--apply filter` y `--apply unfilter`. No escribas una herramienta nueva.
- El filtro solo registra (con `DbgPrint` o ETW, y DebugView para verlo) cada `IRP_MJ_INTERNAL_DEVICE_CONTROL` / `IRP_MJ_DEVICE_CONTROL` que pase hacia abajo: código IOCTL, tamaños y los primeros bytes de entrada y salida al completarse, y su estado NTSTATUS. Todo lo demás pasa sin tocarse.
- Fuerza el arranque con `hidbthle.inf` (`--apply restore`) y captura la secuencia.

**Salida:** identificar la petición que lee la característica `0x0042` (aparecerá el handle `0x42` o el UUID `2A4B` en la entrada) y el NTSTATUS con que vuelve. Si en el log no aparece ninguna lectura reconocible, para y documenta: la interposición en este punto no es viable, y no se pasa a la Fase 3.

### Fase 3: filtro ACTIVO, con un único cambio
- Al completarse la lectura del Report Map, si el buffer de salida trae un error o una longitud incorrecta, rellénalo con el Report Map validado en la Fase 0 (`static const UCHAR` de 126 bytes), con la estructura de salida exacta que observaste, y complétalo con éxito. Si la lectura sale bien, déjala intacta (`shortcut: mapa fijo de 126 bytes; si el fabricante cambia el firmware, el filtro solo actúa cuando hay error`).
- No traduzcas teclas en el kernel ni toques las notificaciones.
- Prueba: el estado PnP pasa a `OK` (sin código 10), aparecen dispositivos HID hijos (`Get-PnpDevice -Class HIDClass`) y la conexión dura más de 5 minutos.

**Salida:** HID arranca y se mantiene. Si arranca pero Windows trata el mapa como pantalla táctil y eso molesta, la siguiente iteración cambia en el mapa servido solo el Usage Page de la colección táctil a vendor (`0xFF00`). No hay que tocar nada más.

### Fase 4: mapeo a PowerPoint (solo modo usuario, sin driver)
- Con HID funcionando, captura cada botón con Raw Input (`RegisterRawInputDevices` para Consumer Control `0x0C/0x01` y para la colección vendor o táctil) y anota qué informe produce cada botón y gesto.
- Script pequeño en Python (ctypes, el mismo estilo que `probe_native_gatt.py`) que traduce: siguiente → `Right`/`PageDown`, anterior → `Left`/`PageUp`, central → `B` o `F5`, con `SendInput`. Usa la idea de Bluepad32: un gesto completo produce una sola acción. No copies sus offsets.
- Integra el reaplicado del filtro en `tools/monitor_jx05.py`, que ya detecta las instancias nuevas: hoy aplica el genérico, pasa a aplicar `--apply filter`. Deja de forzar el genérico.

## Reglas de trabajo
- El cambio más pequeño que funcione: reutiliza las herramientas del repo, no metas dependencias nuevas en Python y deja un test por cada parser nuevo.
- Antes de cualquier paso que cambie el sistema (driver, bcdedit, Secure Boot), di qué hace y cómo se revierte, y espera confirmación.
- Registra en `INVESTIGACION.md` el resultado real de cada fase, aunque sea negativo, sin presentarlo como solución hasta que el botón mueva una diapositiva.
- Si una fase falla, no improvises otro driver: documenta el bloqueo y propón el siguiente punto de interposición. El candidato sería un filtro UMDF dentro del host de HidOverGatt, con menos riesgo de pantallazo azul pero una configuración menos documentada.
