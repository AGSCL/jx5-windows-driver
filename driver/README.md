# Filtro experimental JX05Mtu para este PC

Estado al 2026-11-05: **0.1.0.2 cargado como oem3.inf**, después del segundo
reinicio autorizado a las 21:06:07. El binario cargado coincide con el SHA-256
firmado. El emparejamiento del anillo se renovó para descartar el mapa antiguo
almacenado por Windows. Hay una sola colección vendor FF00:0001, sin errores.
BitLocker C: está FullyEncrypted / Protection On; testsigning
permanece activo. Secure Boot ya estaba desactivado y no se modificó.

## Corrección y alcance

La oferta ATT MTU de Windows observada era 527. El filtro reduce ofertas >=23
al mínimo 23 para la dirección pública B7:FC:01:C6:F3:7E. Con 0.1.0.1 se obtuvo
el mapa HID completo de 126 bytes en seis bloques 22/22/22/22/22/16 y desapareció
el código 10. El mapa declara entrada ID1 de 32 bits e ID3 de 24 bits.

Los botones originales son táctiles y consumer: además de nuestra traducción,
Windows producía selección de texto y cambios de volumen. 0.1.0.2 sustituye
los bloques exactos del mapa capturado por una colección vendor FF00:0001 de
igual longitud, conservando los IDs y tamaños. No modifica informes de botones
ni firmware. Solo reescribe respuestas a lecturas del atributo 0x0042 en orden,
con longitud y contenido coincidentes con la captura. La eficacia de este
cambio se verificó en la captura de seis bloques y en el nuevo nodo HID.
El usuario confirmó ausencia de selección con derecho mantenido y de cambios
de volumen con superior mantenido. Falta la validación completa en aplicaciones.

El INF agrega un filtro inferior USB al adaptador
`USB\VID_13D3&PID_3567&REV_0100&MI_00`. Conserva **BTHUSB, oem4.inf y
MTKBTFilterX64**. Aunque las modificaciones de paquetes solo afectan al anillo,
un fallo del filtro puede afectar todo el adaptador o causar un fallo de kernel.
No es un controlador certificado por Microsoft ni validado para distribución.

El filtro aprende los pipes USB y la conexión LE del anillo. Desconexión,
reinicio, reutilización de handle y errores invalidan ese seguimiento. Otros
paquetes se reenvían. No expone IOCTL públicos ni emite teclas ni inicia programas.
Limitaciones: HCI USB estándar, dirección pública, LE Connection Complete y
Enhanced v1. Fragmentos USB/HCI, MDL encadenados y buffers >4096 bytes pasan
sin corregir. Enhanced v2 desactiva el seguimiento. Falta Driver Verifier,
pruebas de energía/concurrencia y HLK.

## Compilación y firma

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File driver/build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File driver/sign-test.ps1
```

Herramientas locales en `.toolchain`: MSVC 14.44.35207, SDK/WDK oficial NuGet
10.0.26100.6584, KMDF 1.15. Los scripts no descargan herramientas.
La compilación ejecuta `tests/test_mtu.c` con ASan, incluyendo negociación,
aislamiento, truncamientos, mapa y 100.000 buffers aleatorios. Kernel con
/W4 /WX /analyze, CFG, NX y GS; INF con InfVerif /u y catálogo con Inf2Cat.
Estas comprobaciones pasaron para 0.1.0.2. No sustituyen pruebas cargado en kernel.

La firma crea un certificado efímero nuevo por ejecución, firma SYS/CAT,
verifica la firma criptográfica y elimina el PFX temporal. No importa confianza
ni instala nada. En el sandbox del agente, signtool necesita elevación externa.
Volver a compilar invalida la firma: hay que volver a firmar e importar el nuevo
certificado si se decide instalar. No recompilar sobre el paquete instalado
sin conservar previamente una copia para reversión.

Salida: `build/jx05mtu/package/{jx05mtu.sys,jx05mtu.inf,jx05mtu.cat}`,
`jx05-test.cer`, `hashes.json`, PDB y `kernel-analysis.xml`.
Certificado 0.1.0.2: `515214F5FB0AA25C02FC5BD484303F722EC10B35`, importado en
LocalMachine Root y TrustedPublisher. SYS/CAT verificaron Valid.
La copia anterior está en `build/jx05mtu-v011`, exportada desde Driver Store.
Su certificado `0C26A79EB0B08017507FBAD615579F1763B8915C` se retiró de Root y
TrustedPublisher después de comprobar la nueva versión cargada. La copia
pública exportada se conserva para una eventual reversión.

## Activación actual y siguiente comprobación

El usuario autorizó el controlador, la instalación, testsigning, la suspensión
de BitLocker por un reinicio y después el primer reinicio. Este ocurrió a las
20:22:28 y BitLocker reanudó su protección. No repetir esos cambios.

Se desinstaló 0.1.0.1, conservando copia para reversión, y se agregó 0.1.0.2.
Ambas operaciones pidieron reiniciar. El intento de reiniciar solo el adaptador
fue rechazado por la operación pendiente. La versión antigua siguió cargada
hasta el segundo reinicio autorizado. No forzar descargas del filtro ni
reiniciar Windows sin la confirmación solicitada por el usuario.

El segundo reinicio ya se autorizó y ejecutó. El registro está en
`.jx05-monitor/activation-20261105-151900/state.json` y `install-v012.txt`.
El reinicio y la recreación del nodo HID no descartaron la caché antigua;
la lectura nativa tampoco pudo refrescarla. Desemparejar y volver a emparejar
solo el JX-05 con confirmación estándar y cifrado provocó las seis lecturas
corregidas. No se cambiaron asociaciones globales de drivers.

Proveedor ETW `{671c3451-d89a-47c8-b2dd-8bd5f0a149c3}`: evento 1 configuración
USB; 2 handle del anillo o 65535 al perderlo; 3/4 modificaciones MTU salida/entrada;
5 número acumulado de bloques del mapa sustituidos en la conexión. Los seis
bloques y la colección vendor deben verificarse antes de la prueba funcional.
BTHPORT `{8a1f9517-3a8c-4a9e-a018-4f17a200f277}` permite contrastar el tráfico.

## Reversión

Verificar primero que el INF publicado corresponde a `jx05mtu.inf`, proveedor
JX05 local experiment. En este estado es oem3.inf; Windows puede renumerarlo.

```powershell
pnputil /delete-driver oem3.inf /uninstall
```

Si solicita reinicio, guardar el trabajo y pedir confirmación antes de reiniciar.
Comprobar después la pila BTHUSB + MTKBTFilterX64 sin Jx05Mtu. No eliminar oem4.inf
ni el filtro MediaTek. Para volver a 0.1.0.1 usar la exportación guardada y su
certificado, sabiendo que reaparecen los efectos táctiles y de volumen.

Tras retirar el filtro, eliminar solo los certificados de esta prueba anotados
en state.json de Root y TrustedPublisher. La copia antigua v0.1.0.0 ya se retiró.
No deducir los thumbprints de un archivo que se haya vuelto a firmar.
Para restaurar el BCD inicial sin testsigning:

```powershell
bcdedit /deletevalue '{current}' testsigning
```

Restaurar BCD también requiere preparar BitLocker y autorizar el reinicio;
no ejecutar ese comando mientras se dependa del filtro firmado para pruebas.
La clave de recuperación no se solicitó ni se extrajo.

## Fuentes

- [INF de extensión](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/using-an-extension-inf-file).
- [AddFilter](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/inf-addfilter-directive).
- [URB bulk/interrupt](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usb/ns-usb-_urb_bulk_or_interrupt_transfer).
- [Jieli HOGP](https://github.com/Jieli-Tech/fw-AC63_BT_SDK/blob/master/apps/hid/modules/bt/ble_hogp.c): hipótesis del fallo de lectura al final del mapa, no identificación inequívoca de firmware.
