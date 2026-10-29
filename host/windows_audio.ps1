# List Windows' connected Bluetooth speakers and switch the default output between them.
# Called by speaker_helper.py through WSL interop; prints JSON.
#   windows_audio.ps1 list
#   windows_audio.ps1 set <endpoint-id>
#   windows_audio.ps1 default
param([Parameter(Mandatory)][ValidateSet("list", "set", "default")][string]$Command, [string]$EndpointId)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace LunaVibia {
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}

    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
        [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
    }

    [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDevice {
        int Activate(ref Guid iid, int context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object result);
        int OpenPropertyStore(int access, out IntPtr store);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
    }

    [ComImport, Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")] class PolicyConfigClient {}

    // Undocumented but stable since Windows 7; only SetDefaultEndpoint is called.
    [Guid("F8679F50-850A-41CF-9C72-430F290290C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPolicyConfig {
        int GetMixFormat(); int GetDeviceFormat(); int ResetDeviceFormat(); int SetDeviceFormat();
        int GetProcessingPeriod(); int SetProcessingPeriod(); int GetShareMode(); int SetShareMode();
        int GetPropertyValue(); int SetPropertyValue();
        [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, int role);
    }

    public static class Audio {
        public static string DefaultOutput() {
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumerator();
            IMMDevice device;
            if (enumerator.GetDefaultAudioEndpoint(0, 1, out device) != 0) return null;  // eRender, eMultimedia
            string id;
            device.GetId(out id);
            return id;
        }

        public static void SetDefaultOutput(string id) {
            var policy = (IPolicyConfig)new PolicyConfigClient();
            for (int role = 0; role < 3; role++) {  // console, multimedia, communications
                int result = policy.SetDefaultEndpoint(id, role);
                if (result != 0) Marshal.ThrowExceptionForHR(result);
            }
        }
    }
}
"@

function Get-BluetoothSpeakers {
    $bluetooth = @(Get-PnpDevice -Class Bluetooth | Where-Object { $_.InstanceId -match '^BTH(ENUM|LE)' } | ForEach-Object {
        (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_ContainerId).Data.ToString()
    })
    $default = [LunaVibia.Audio]::DefaultOutput()
    # Connected (status OK) render endpoints ({0.0.0...}) of Bluetooth devices; the
    # low-quality hands-free profile is left out.
    Get-PnpDevice -Class AudioEndpoint -Status OK | Where-Object {
        $_.InstanceId -like 'SWD\MMDEVAPI\{0.0.0.*' -and $_.FriendlyName -notmatch 'Hands-Free'
    } | ForEach-Object {
        $container = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_ContainerId).Data.ToString()
        if ($bluetooth -contains $container) {
            $id = $_.InstanceId.Substring('SWD\MMDEVAPI\'.Length).ToLower()
            $device = if ($_.FriendlyName -match '\((.+)\)$') { $Matches[1] } else { $_.FriendlyName }
            [pscustomobject]@{ id = $id; name = $device; description = $_.FriendlyName; default = ($id -eq $default) }
        }
    }
}

switch ($Command) {
    "list" { ConvertTo-Json -Compress -InputObject @(Get-BluetoothSpeakers) }
    # The current default output, whatever kind it is; one device lookup, not a listing.
    "default" {
        $id = [LunaVibia.Audio]::DefaultOutput()
        $endpoint = if ($id) { Get-PnpDevice -InstanceId "SWD\MMDEVAPI\$id" -ErrorAction SilentlyContinue }
        $description = if ($endpoint) { $endpoint.FriendlyName } else { "" }
        $device = if ($description -match '\((.+)\)$') { $Matches[1] } else { $description }
        ConvertTo-Json -Compress -InputObject @{ id = $id; name = $device; description = $description }
    }
    # speaker_helper.py only passes IDs that "list" returned, so this skips the slow listing.
    "set" {
        [LunaVibia.Audio]::SetDefaultOutput($EndpointId.ToLower())
        ConvertTo-Json -Compress -InputObject @{ id = [LunaVibia.Audio]::DefaultOutput() }
    }
}
