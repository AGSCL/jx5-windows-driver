# JX05 MTU: prototipo experimental para este PC

Existe un controlador KMDF x64 compilado y firmado con un certificado local
de prueba. **No está instalado ni se ha probado en el kernel. No es todavía
un pasador de diapositivas.**

La hipótesis es evitar la lectura larga defectuosa negociando ATT MTU 23 en
ambos extremos de la conexión. Si el mapa mide 126 bytes, las respuestas
serían de 22, 22, 22, 22, 22 y 16 bytes: no se pediría el bloque que empieza
justo en 126. No se sustituye el descriptor por uno supuesto ni se modifica
el firmware. Que el anillo responda correctamente con ese MTU sigue pendiente.

## Alcance del filtro

El INF de extensión conserva BTHUSB y el filtro MediaTek existente. Añade un
filtro inferior USB al hardware `USB\VID_13D3&PID_3567&REV_0100&MI_00`, el del
adaptador de este PC. Esto afecta a la pila del **adaptador**, aunque el código
solo cambia los dos bytes de MTU en intercambios ATT de la dirección pública
`B7:FC:01:C6:F3:7E`. No es un filtro instalado únicamente sobre el nodo del anillo.

Aprende los pipes de eventos/ACL de la configuración USB. Solo activa la
corrección al observar una conexión LE exitosa de esa dirección. Desconexión,
reinicio, reutilización del handle y errores de transferencia invalidan el
seguimiento. Otros paquetes se reenvían. No expone IOCTL públicos, escribe
teclas, inicia programas ni cambia el inicio de sesión.

Limitaciones: solo HCI USB estándar, dirección pública, eventos LE Connection
Complete y Enhanced Connection Complete v1. Paquetes USB/HCI fragmentados,
MDL encadenados y buffers ACL superiores a 4096 bytes pasan sin corregir.
Enhanced Connection Complete v2 desactiva el seguimiento. Los casos no
soportados pueden impedir que la negociación funcione; hay que comprobarla
en una captura real. También falta verificar la interacción con MTKBTFilterX64,
los ciclos de energía y las cancelaciones concurrentes bajo Driver Verifier.

## Compilación y comprobaciones locales

Desde la raíz del repositorio:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File driver/build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File driver/sign-test.ps1
```

Se usan MSVC 14.44.35207, SDK/WDK NuGet 10.0.26100.6584, KMDF 1.15 y
AddressSanitizer, ubicados en `.toolchain/`. Build Tools terminó con código 0.
El SDK/WDK procede de NuGet de Microsoft y el instalador de VS de
`https://aka.ms/vs/17/release/vs_BuildTools.exe` (firma Microsoft comprobada).
No se descarga nada al ejecutar estos scripts.

`build.ps1` compila y ejecuta `tests/test_mtu.c` con AddressSanitizer; comprueba
negociaciones en ambos sentidos, aislamiento de otras conexiones, buffers
truncados, desconexión, reutilización y 100.000 buffers aleatorios. Compila el
kernel con `/W4 /WX /analyze`, CFG, NX y GS, valida el INF con InfVerif `/u` y
genera el catálogo con Inf2Cat para Windows 11 x64 24H2. Todos pasaron el
2026-11-05. `kernel-analysis.xml` no contiene defectos. No equivalen a HLK ni
a pruebas del controlador cargado.

`sign-test.ps1` crea un certificado local, firma SYS y CAT y verifica la firma
criptográfica del catálogo. Elimina el PFX temporal. No importa certificados
en almacenes de confianza, no instala el paquete ni modifica BCD. En el entorno
restringido del agente la firma necesitó ejecución fuera del sandbox.
La firma no tiene confianza Microsoft; Windows informa raíz no confiable.
Cada ejecución genera un certificado nuevo. Volver a compilar requiere volver
a firmar; `hashes.json` identifica siempre la última salida.

Archivos preparados en `build/jx05mtu/`:

- `package/jx05mtu.sys`, `package/jx05mtu.inf`, `package/jx05mtu.cat`.
- `jx05-test.cer`: certificado público de esta compilación.
- `hashes.json`: SHA-256 de los tres archivos y del certificado.
- `jx05mtu.pdb`, `kernel-analysis.xml`, `mtu-tests.exe`: evidencia de compilación.

## Procedimiento de activación

Hace falta autorización porque la prueba amplía el alcance al adaptador,
interrumpe sus conexiones (incluido el ratón Bluetooth), habilita firmas de
prueba y requiere reiniciar Windows. Un defecto de kernel puede provocar
pérdida de Bluetooth o un pantallazo azul. Preparar el paquete no ha realizado
ninguna de estas acciones. La aprobación de crear el controlador ya se recibió;
lo pendiente es aprobar estos efectos concretos de probarlo.

Actualización: el usuario autorizó la suspensión de BitLocker por un reinicio,
pero pidió confirmar antes de reiniciar. Ya se importó el certificado de prueba,
se suspendió BitLocker con `RebootCount=1` y se configuró `testsigning on`.
No se ha reiniciado ni instalado el filtro. La protección sigue suspendida
hasta el próximo reinicio; comprobar su reanudación al volver. No repetir los
pasos ya realizados ni reiniciar sin la confirmación pendiente. El estado está
en `.jx05-monitor/activation-20261105-151900/state.json`.

Tras esa autorización, guardar el trabajo y disponer del teclado/touchpad
integrados. Guardar la salida de `bcdedit /enum '{current}'`, la pila del
adaptador y `pnputil /enum-drivers`. No sustituir `oem4.inf` ni eliminar
`MTKBTFilterX64`. No desactivar Secure Boot ni Integridad de memoria para
forzar la carga; si impiden la prueba, registrar el bloqueo.

En PowerShell como administrador, desde la raíz, el procedimiento previsto es:

```powershell
Import-Certificate -FilePath build/jx05mtu/jx05-test.cer -CertStoreLocation Cert:\LocalMachine\Root
Import-Certificate -FilePath build/jx05mtu/jx05-test.cer -CertStoreLocation Cert:\LocalMachine\TrustedPublisher
bcdedit /set '{current}' testsigning on
```

Reiniciar con autorización explícita. Después comprobar que el modo de prueba
está activo y agregar la extensión:

```powershell
pnputil /add-driver build/jx05mtu/package/jx05mtu.inf /install
pnputil /enum-drivers
```

Anotar el **nombre publicado oemN.inf de jx05mtu.inf**, su proveedor
`JX05 local experiment` y el thumbprint del certificado. No confundirlo con el
INF base del adaptador. Si PnP pide reiniciar, esperar autorización para ello.
Si hace falta reiniciar solo el dispositivo, la instancia observada es:

```powershell
pnputil /restart-device 'USB\VID_13D3&PID_3567&MI_00\7&2AF7C8F&0&0000'
```

Verificar primero que esa instancia sigue siendo la del adaptador. No ejecutar
el reinicio mientras el usuario dependa del ratón Bluetooth para guardar trabajo.

## Captura y criterio de aceptación

El proveedor ETW `{671c3451-d89a-47c8-b2dd-8bd5f0a149c3}` emite eventos con un
ULONG de datos: ID 1 configuración USB observada; ID 2 handle del anillo o
65535 al perderlo; ID 3/4 número de cambios MTU de salida/entrada. Es diagnóstico
sin manifiesto y no registra pulsaciones. La captura BTHPORT existente permite
comprobar el MTU que ve Windows; el evento del filtro acredita el cambio de salida.

Antes de pulsar botones: comprobar que el filtro está cargado, que ambos lados
negocian 23, que Report Map termina sin respuesta excesiva y que HID inicia sin
código 10. Si no ocurre, detener la prueba y retirar la extensión. No ampliar
automáticamente el filtro a otros dispositivos ni inventar un mapa fijo.

Solo después capturar cada botón por separado y esperar confirmación del
usuario. Falta implementar la traducción de informes identificados a Right/Left,
sin repeticiones al mantener pulsado, con modo presentador desactivado al inicio.
Siguen pendientes diez avances y diez retrocesos en PowerPoint, xaringan y
Google Slides, cinco minutos de uso y recuperación al apagar/encender el anillo.

## Reversión prevista

Eliminar solo el nombre publicado que se anotó para esta extensión:

```powershell
# Sustituir oemN.inf por el nombre confirmado de jx05mtu.inf.
pnputil /delete-driver oemN.inf /uninstall
```

Si Windows requiere reiniciar, hacerlo después de guardar el trabajo. Para un
fallo de carga, utilizar el modo seguro y retirar ese mismo paquete. No borrar
el INF MediaTek ni cambiar listas globales de filtros. Después de desinstalar,
comprobar BTHUSB + MTKBTFilterX64 y ausencia de Jx05Mtu en la pila.

Retirar únicamente el certificado de prueba importado en esta sesión:

```powershell
$testCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path build/jx05mtu/jx05-test.cer).Path)
$testThumbprint = $testCert.Thumbprint
Remove-Item -LiteralPath "Cert:\LocalMachine\Root\$testThumbprint"
Remove-Item -LiteralPath "Cert:\LocalMachine\TrustedPublisher\$testThumbprint"
bcdedit /deletevalue '{current}' testsigning
```

Esto presupone el estado inicial observado: sin estos certificados y sin valor
`testsigning` en BCD. Si ese estado cambia antes de la prueba, restaurar lo
guardado, no aplicar esta reversión a ciegas. Reiniciar para volver al arranque
normal. No volver a firmar entre instalación y retirada del certificado; guardar
el thumbprint importado independientemente del archivo.

## Fundamento

- [Extensiones INF y desinstalación](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/using-an-extension-inf-file).
- [Filtros por dispositivo](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/inf-addfilter-directive).
- [Contrato de URB bulk/interrupt](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usb/ns-usb-_urb_bulk_or_interrupt_transfer).
- [Código HOGP de Jieli](https://github.com/Jieli-Tech/fw-AC63_BT_SDK/blob/master/apps/hid/modules/bt/ble_hogp.c): el caso Report Map puede devolver la longitud total al alcanzar el final sin copiar datos. Coincide con una hipótesis del fallo capturado; no identifica inequívocamente el firmware de esta unidad.
