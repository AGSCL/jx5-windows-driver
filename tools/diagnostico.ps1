# Ejecutar en Windows PowerShell con el JX-05 emparejado.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = 'JX-05 - Diagnóstico de teclas'
$form.Size = New-Object System.Drawing.Size(780, 480)
$form.KeyPreview = $true
$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = 'Vertical'
$log.Dock = 'Fill'
$log.Font = New-Object System.Drawing.Font('Consolas', 10)
$form.Controls.Add($log)
$log.AppendText("Empareja el JX-05, selecciona esta ventana y pulsa cada botón.`r`nSolo se muestran eventos de teclado que Windows entrega a esta ventana.`r`nNo identifica el dispositivo de origen ni captura todos los eventos multimedia o gestos.`r`n`r`n")
$form.Add_KeyDown({ param($sender, $e) $log.AppendText(('{0:HH:mm:ss.fff} DOWN KeyCode={1} KeyValue={2} Modifiers={3}' -f (Get-Date), $e.KeyCode, $e.KeyValue, $e.Modifiers) + "`r`n") })
$form.Add_KeyUp({ param($sender, $e) $log.AppendText(('{0:HH:mm:ss.fff} UP   KeyCode={1} KeyValue={2} Modifiers={3}' -f (Get-Date), $e.KeyCode, $e.KeyValue, $e.Modifiers) + "`r`n") })
[void]$form.ShowDialog()
