# List Windows' connected Bluetooth speakers, switch the default output between them,
# and read or change the default output's volume.
# Called by speaker_helper.py through WSL interop; prints JSON.
#   windows_audio.ps1 list
#   windows_audio.ps1 set <endpoint-id>
#   windows_audio.ps1 default
#   windows_audio.ps1 volume
#   windows_audio.ps1 set-volume <0-100>
#   windows_audio.ps1 set-mute <true|false>
param(
    [Parameter(Mandatory)][ValidateSet("list", "set", "default", "volume", "set-volume", "set-mute")][string]$Command,
    [string]$EndpointId
)

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
        [PreserveSig] int Activate(ref Guid iid, int context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object result);
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

    // The output's master volume, as the Windows volume slider shows it. Methods are
    // listed in vtable order; only the master scalar and mute ones are called.
    [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioEndpointVolume {
        int RegisterControlChangeNotify(IntPtr notify);
        int UnregisterControlChangeNotify(IntPtr notify);
        int GetChannelCount(out uint count);
        int SetMasterVolumeLevel(float levelDb, ref Guid context);
        [PreserveSig] int SetMasterVolumeLevelScalar(float level, ref Guid context);
        int GetMasterVolumeLevel(out float levelDb);
        [PreserveSig] int GetMasterVolumeLevelScalar(out float level);
        int SetChannelVolumeLevel(uint channel, float levelDb, ref Guid context);
        int SetChannelVolumeLevelScalar(uint channel, float level, ref Guid context);
        int GetChannelVolumeLevel(uint channel, out float levelDb);
        int GetChannelVolumeLevelScalar(uint channel, out float level);
        [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, ref Guid context);
        [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool mute);
    }

    public static class Audio {
        static void Check(int result) {
            if (result != 0) Marshal.ThrowExceptionForHR(result);
        }

        static IAudioEndpointVolume DefaultVolume() {
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumerator();
            IMMDevice device;
            Check(enumerator.GetDefaultAudioEndpoint(0, 1, out device));  // eRender, eMultimedia
            Guid iid = typeof(IAudioEndpointVolume).GUID;
            object volume;
            Check(device.Activate(ref iid, 23, IntPtr.Zero, out volume));  // CLSCTX_ALL
            return (IAudioEndpointVolume)volume;
        }

        public static int Volume() {
            float level;
            Check(DefaultVolume().GetMasterVolumeLevelScalar(out level));
            return (int)Math.Round(level * 100);
        }

        public static bool Muted() {
            bool muted;
            Check(DefaultVolume().GetMute(out muted));
            return muted;
        }

        public static void SetVolume(int percent) {
            Guid context = Guid.Empty;
            Check(DefaultVolume().SetMasterVolumeLevelScalar(Math.Max(0, Math.Min(100, percent)) / 100f, ref context));
        }

        public static void SetMute(bool mute) {
            Guid context = Guid.Empty;
            Check(DefaultVolume().SetMute(mute, ref context));
        }

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
    # The default output's volume (0-100) and mute; set-* change it, then report it.
    { $_ -in "volume", "set-volume", "set-mute" } {
        if ($Command -eq "set-volume") { [LunaVibia.Audio]::SetVolume([int]$EndpointId) }
        if ($Command -eq "set-mute") { [LunaVibia.Audio]::SetMute($EndpointId -eq "true") }
        ConvertTo-Json -Compress -InputObject @{
            id = [LunaVibia.Audio]::DefaultOutput(); volume = [LunaVibia.Audio]::Volume(); muted = [LunaVibia.Audio]::Muted()
        }
    }
    # speaker_helper.py only passes IDs that "list" returned, so this skips the slow listing.
    "set" {
        [LunaVibia.Audio]::SetDefaultOutput($EndpointId.ToLower())
        ConvertTo-Json -Compress -InputObject @{ id = [LunaVibia.Audio]::DefaultOutput() }
    }
}
