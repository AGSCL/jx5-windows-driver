#include <ntddk.h>
#include <wdf.h>
#include <usb.h>
#include <usbioctl.h>
#include <evntrace.h>
#include "mtu.h"

typedef struct DEVICE_CONTEXT {
    WDFSPINLOCK lock;
    USBD_PIPE_HANDLE events, acl_in, acl_out;
    JX05_LINK link;
} DEVICE_CONTEXT;
WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(DEVICE_CONTEXT, Context)

static REGHANDLE trace;
static const GUID provider = {0x671c3451, 0xd89a, 0x47c8, {0xb2,0xdd,0x8b,0xd5,0xf0,0xa1,0x49,0xc3}};
DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD DeviceAdd;
EVT_WDF_DRIVER_UNLOAD DriverUnload;
EVT_WDF_IO_QUEUE_IO_INTERNAL_DEVICE_CONTROL InternalControl;
EVT_WDF_REQUEST_COMPLETION_ROUTINE Complete;
EVT_WDF_DEVICE_D0_EXIT D0Exit;

static void Log(USHORT id, ULONG value)
{
    EVENT_DESCRIPTOR event = {0};
    EVENT_DATA_DESCRIPTOR data;
    if (!trace) return;
    event.Id = id;
    event.Level = 4;
    EventDataDescCreate(&data, &value, sizeof(value));
    (void)EtwWrite(trace, &event, NULL, 1, &data);
}

static void Reset(DEVICE_CONTEXT *ctx)
{
    WdfSpinLockAcquire(ctx->lock);
    ctx->events = ctx->acl_in = ctx->acl_out = NULL;
    Jx05Reset(&ctx->link);
    WdfSpinLockRelease(ctx->lock);
}

static void LearnInterface(DEVICE_CONTEXT *ctx, PUSBD_INTERFACE_INFORMATION info, size_t available)
{
    ULONG i;
    size_t header = FIELD_OFFSET(USBD_INTERFACE_INFORMATION, Pipes);
    if (available < header || info->Length < header || info->Length > available ||
        info->NumberOfPipes > (info->Length - header) / sizeof(USBD_PIPE_INFORMATION) ||
        info->InterfaceNumber != 0 || info->Class != 0xe0 ||
        info->SubClass != 1 || info->Protocol != 1) return;
    for (i = 0; i < info->NumberOfPipes; ++i) {
        PUSBD_PIPE_INFORMATION p = &info->Pipes[i];
        if (p->PipeType == UsbdPipeTypeInterrupt && (p->EndpointAddress & 0x80)) ctx->events = p->PipeHandle;
        if (p->PipeType == UsbdPipeTypeBulk) {
            if (p->EndpointAddress & 0x80) ctx->acl_in = p->PipeHandle;
            else ctx->acl_out = p->PipeHandle;
        }
    }
}

static PUCHAR TransferBuffer(struct _URB_BULK_OR_INTERRUPT_TRANSFER *urb)
{
    if (urb->TransferBuffer) return (PUCHAR)urb->TransferBuffer;
    if (!urb->TransferBufferMDL || urb->TransferBufferMDL->Next ||
        MmGetMdlByteCount(urb->TransferBufferMDL) < urb->TransferBufferLength) return NULL;
    return (PUCHAR)MmGetSystemAddressForMdlSafe(urb->TransferBufferMDL, NormalPagePriority | MdlMappingNoExecute);
}

static void Inspect(DEVICE_CONTEXT *ctx, PURB urb, BOOLEAN incoming)
{
    struct _URB_BULK_OR_INTERRUPT_TRANSFER *transfer = &urb->UrbBulkOrInterruptTransfer;
    PUCHAR buffer;
    unsigned changed = 0;
    unsigned short before, after;
    ULONG patchesBefore, patchesAfter;
    if (urb->UrbHeader.Length < sizeof(*transfer) ||
        !!(transfer->TransferFlags & USBD_TRANSFER_DIRECTION_IN) != !!incoming) return;
    buffer = TransferBuffer(transfer);
    WdfSpinLockAcquire(ctx->lock);
    before = ctx->link.active ? ctx->link.handle : 0xffff;
    patchesBefore = ctx->link.map_patches;
    if (incoming && transfer->PipeHandle == ctx->events && ctx->events) {
        if (buffer && transfer->TransferBufferLength && transfer->TransferBufferLength <= 4096)
            Jx05Events(&ctx->link, buffer, transfer->TransferBufferLength);
        else Jx05Reset(&ctx->link);
    } else if (buffer && transfer->PipeHandle &&
               transfer->PipeHandle == (incoming ? ctx->acl_in : ctx->acl_out)) {
        changed = Jx05Acl(&ctx->link, buffer, transfer->TransferBufferLength, incoming);
    }
    after = ctx->link.active ? ctx->link.handle : 0xffff;
    patchesAfter = ctx->link.map_patches;
    WdfSpinLockRelease(ctx->lock);
    if (before != after) Log(2, after);
    if (changed) Log(incoming ? 4 : 3, changed);
    if (patchesAfter > patchesBefore) Log(5, patchesAfter);
}

void Complete(WDFREQUEST request, WDFIOTARGET target, PWDF_REQUEST_COMPLETION_PARAMS params, WDFCONTEXT context)
{
    PURB urb = (PURB)context;
    DEVICE_CONTEXT *ctx = Context(WdfIoTargetGetDevice(target));
    if (NT_SUCCESS(params->IoStatus.Status) && USBD_SUCCESS(urb->UrbHeader.Status)) {
        if (urb->UrbHeader.Function == URB_FUNCTION_SELECT_CONFIGURATION) {
            size_t offset = FIELD_OFFSET(struct _URB_SELECT_CONFIGURATION, Interface);
            WdfSpinLockAcquire(ctx->lock);
            while (offset + FIELD_OFFSET(USBD_INTERFACE_INFORMATION, Pipes) <= urb->UrbHeader.Length) {
                PUSBD_INTERFACE_INFORMATION info = (PUSBD_INTERFACE_INFORMATION)((PUCHAR)urb + offset);
                size_t left = urb->UrbHeader.Length - offset;
                if (info->Length < FIELD_OFFSET(USBD_INTERFACE_INFORMATION, Pipes) || info->Length > left) break;
                LearnInterface(ctx, info, left);
                offset += info->Length;
            }
            WdfSpinLockRelease(ctx->lock);
            Log(1, 1);
        } else if (urb->UrbHeader.Function == URB_FUNCTION_SELECT_INTERFACE) {
            size_t offset = FIELD_OFFSET(struct _URB_SELECT_INTERFACE, Interface);
            if (urb->UrbHeader.Length >= offset) {
                WdfSpinLockAcquire(ctx->lock);
                LearnInterface(ctx, &urb->UrbSelectInterface.Interface, urb->UrbHeader.Length - offset);
                WdfSpinLockRelease(ctx->lock);
            }
        } else if (urb->UrbHeader.Function == URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER) {
            Inspect(ctx, urb, TRUE);
        }
    } else {
        /* A failed transfer can hide a disconnect; disable correction until a new connection. */
        WdfSpinLockAcquire(ctx->lock);
        Jx05Reset(&ctx->link);
        WdfSpinLockRelease(ctx->lock);
    }
    WdfRequestCompleteWithInformation(request, params->IoStatus.Status, params->IoStatus.Information);
}

void InternalControl(WDFQUEUE queue, WDFREQUEST request, size_t outputSize, size_t inputSize, ULONG code)
{
    WDFDEVICE device = WdfIoQueueGetDevice(queue);
    DEVICE_CONTEXT *ctx = Context(device);
    PURB urb = NULL;
    WDF_REQUEST_SEND_OPTIONS options;
    UNREFERENCED_PARAMETER(outputSize);
    UNREFERENCED_PARAMETER(inputSize);
    if (code == IOCTL_INTERNAL_USB_SUBMIT_URB) {
        PIO_STACK_LOCATION stack = IoGetCurrentIrpStackLocation(WdfRequestWdmGetIrp(request));
        urb = (PURB)stack->Parameters.Others.Argument1;
        if (urb && urb->UrbHeader.Length >= sizeof(struct _URB_HEADER)) {
            if (urb->UrbHeader.Function == URB_FUNCTION_SELECT_CONFIGURATION) Reset(ctx);
            else if (urb->UrbHeader.Function == URB_FUNCTION_SELECT_INTERFACE &&
                     urb->UrbHeader.Length >= FIELD_OFFSET(struct _URB_SELECT_INTERFACE, Interface) +
                     FIELD_OFFSET(USBD_INTERFACE_INFORMATION, Pipes) &&
                     urb->UrbSelectInterface.Interface.InterfaceNumber == 0) Reset(ctx);
            else if (urb->UrbHeader.Function == URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER) Inspect(ctx, urb, FALSE);
        } else urb = NULL;
    }
    WdfRequestFormatRequestUsingCurrentType(request);
    WDF_REQUEST_SEND_OPTIONS_INIT(&options, urb ? 0 : WDF_REQUEST_SEND_OPTION_SEND_AND_FORGET);
    if (urb) WdfRequestSetCompletionRoutine(request, Complete, urb);
    if (!WdfRequestSend(request, WdfDeviceGetIoTarget(device), &options)) {
        WdfSpinLockAcquire(ctx->lock);
        Jx05Reset(&ctx->link);
        WdfSpinLockRelease(ctx->lock);
        WdfRequestComplete(request, WdfRequestGetStatus(request));
    }
}

NTSTATUS D0Exit(WDFDEVICE device, WDF_POWER_DEVICE_STATE state)
{
    DEVICE_CONTEXT *ctx = Context(device);
    UNREFERENCED_PARAMETER(state);
    WdfSpinLockAcquire(ctx->lock);
    Jx05Reset(&ctx->link);
    WdfSpinLockRelease(ctx->lock);
    return STATUS_SUCCESS;
}

NTSTATUS DeviceAdd(WDFDRIVER driver, PWDFDEVICE_INIT init)
{
    WDFDEVICE device;
    WDF_OBJECT_ATTRIBUTES attributes;
    WDF_IO_QUEUE_CONFIG queue;
    WDF_PNPPOWER_EVENT_CALLBACKS power;
    NTSTATUS status;
    UNREFERENCED_PARAMETER(driver);
    WdfFdoInitSetFilter(init);
    WDF_PNPPOWER_EVENT_CALLBACKS_INIT(&power);
    power.EvtDeviceD0Exit = D0Exit;
    WdfDeviceInitSetPnpPowerEventCallbacks(init, &power);
    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&attributes, DEVICE_CONTEXT);
    status = WdfDeviceCreate(&init, &attributes, &device);
    if (!NT_SUCCESS(status)) return status;
    WDF_OBJECT_ATTRIBUTES_INIT(&attributes);
    attributes.ParentObject = device;
    status = WdfSpinLockCreate(&attributes, &Context(device)->lock);
    if (!NT_SUCCESS(status)) return status;
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queue, WdfIoQueueDispatchParallel);
    queue.PowerManaged = WdfFalse;
    queue.EvtIoInternalDeviceControl = InternalControl;
    return WdfIoQueueCreate(device, &queue, WDF_NO_OBJECT_ATTRIBUTES, WDF_NO_HANDLE);
}

void DriverUnload(WDFDRIVER driver)
{
    UNREFERENCED_PARAMETER(driver);
    if (trace) (void)EtwUnregister(trace);
}

NTSTATUS DriverEntry(PDRIVER_OBJECT driver, PUNICODE_STRING path)
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;
    WDF_DRIVER_CONFIG_INIT(&config, DeviceAdd);
    config.EvtDriverUnload = DriverUnload;
    (void)EtwRegister(&provider, NULL, NULL, &trace);
    status = WdfDriverCreate(driver, path, WDF_NO_OBJECT_ATTRIBUTES, &config, WDF_NO_HANDLE);
    if (!NT_SUCCESS(status) && trace) { (void)EtwUnregister(trace); trace = 0; }
    return status;
}
