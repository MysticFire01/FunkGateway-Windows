#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <comdef.h>
#include <fcntl.h>
#include <io.h>
#include <cstdio>
#include <cstdint>
#include <vector>

static void fail(const char* msg, HRESULT hr = S_OK) {
    if (FAILED(hr)) {
        std::fprintf(stderr, "%s (HRESULT 0x%08lx)\n", msg, static_cast<unsigned long>(hr));
    } else {
        std::fprintf(stderr, "%s\n", msg);
    }
}

int wmain() {
    _setmode(_fileno(stdout), _O_BINARY);
    std::setvbuf(stdout, nullptr, _IONBF, 0);

    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr)) {
        fail("CoInitializeEx failed", hr);
        return 2;
    }

    IMMDeviceEnumerator* enumerator = nullptr;
    IMMDevice* device = nullptr;
    IAudioClient* audioClient = nullptr;
    IAudioCaptureClient* captureClient = nullptr;

    hr = CoCreateInstance(
        __uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator),
        reinterpret_cast<void**>(&enumerator));
    if (FAILED(hr)) {
        fail("MMDeviceEnumerator failed", hr);
        CoUninitialize();
        return 3;
    }

    hr = enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &device);
    if (FAILED(hr)) {
        fail("No default Windows render endpoint", hr);
        enumerator->Release();
        CoUninitialize();
        return 4;
    }

    hr = device->Activate(
        __uuidof(IAudioClient), CLSCTX_ALL, nullptr,
        reinterpret_cast<void**>(&audioClient));
    if (FAILED(hr)) {
        fail("IAudioClient activation failed", hr);
        device->Release();
        enumerator->Release();
        CoUninitialize();
        return 5;
    }

    WAVEFORMATEX format{};
    format.wFormatTag = WAVE_FORMAT_PCM;
    format.nChannels = 2;
    format.nSamplesPerSec = 48000;
    format.wBitsPerSample = 16;
    format.nBlockAlign =
        static_cast<WORD>(format.nChannels * format.wBitsPerSample / 8);
    format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;
    format.cbSize = 0;

    const DWORD flags =
        AUDCLNT_STREAMFLAGS_LOOPBACK |
        AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
        AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;

    hr = audioClient->Initialize(
        AUDCLNT_SHAREMODE_SHARED, flags, 0, 0, &format, nullptr);
    if (FAILED(hr)) {
        fail("WASAPI loopback initialize failed", hr);
        audioClient->Release();
        device->Release();
        enumerator->Release();
        CoUninitialize();
        return 6;
    }

    hr = audioClient->GetService(
        __uuidof(IAudioCaptureClient),
        reinterpret_cast<void**>(&captureClient));
    if (FAILED(hr)) {
        fail("IAudioCaptureClient failed", hr);
        audioClient->Release();
        device->Release();
        enumerator->Release();
        CoUninitialize();
        return 7;
    }

    hr = audioClient->Start();
    if (FAILED(hr)) {
        fail("WASAPI loopback start failed", hr);
        captureClient->Release();
        audioClient->Release();
        device->Release();
        enumerator->Release();
        CoUninitialize();
        return 8;
    }

    std::vector<int16_t> silence;

    for (;;) {
        UINT32 packetFrames = 0;
        hr = captureClient->GetNextPacketSize(&packetFrames);
        if (FAILED(hr)) {
            fail("GetNextPacketSize failed", hr);
            break;
        }

        if (packetFrames == 0) {
            Sleep(5);
            continue;
        }

        while (packetFrames > 0) {
            BYTE* data = nullptr;
            UINT32 frames = 0;
            DWORD captureFlags = 0;
            UINT64 devicePosition = 0;
            UINT64 qpcPosition = 0;

            hr = captureClient->GetBuffer(
                &data, &frames, &captureFlags,
                &devicePosition, &qpcPosition);
            if (FAILED(hr)) {
                fail("GetBuffer failed", hr);
                break;
            }

            const size_t samples = static_cast<size_t>(frames) * 2;
            if (captureFlags & AUDCLNT_BUFFERFLAGS_SILENT) {
                silence.assign(samples, 0);
                std::fwrite(
                    silence.data(), sizeof(int16_t), samples, stdout);
            } else if (data && samples > 0) {
                std::fwrite(
                    data, sizeof(int16_t), samples, stdout);
            }

            captureClient->ReleaseBuffer(frames);

            hr = captureClient->GetNextPacketSize(&packetFrames);
            if (FAILED(hr)) {
                fail("GetNextPacketSize failed", hr);
                packetFrames = 0;
            }
        }
    }

    audioClient->Stop();
    captureClient->Release();
    audioClient->Release();
    device->Release();
    enumerator->Release();
    CoUninitialize();
    return 0;
}
