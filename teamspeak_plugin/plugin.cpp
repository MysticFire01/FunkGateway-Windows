#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdint.h>
#include <algorithm>
#include <atomic>
#include <cstring>
#include <thread>
#include <vector>

#include "teamspeak/public_definitions.h"
#include "teamspeak/public_errors.h"
#include "ts3_functions.h"
#include "plugin.h"

#pragma comment(lib, "ws2_32.lib")

static constexpr int PLUGIN_API_VERSION = 26;
static constexpr uint16_t BRIDGE_PORT = 39582;
static constexpr uint32_t AUDIO_RATE = 48000;
static constexpr size_t RING_SAMPLES = AUDIO_RATE * 5;

static TS3Functions g_ts3{};
static std::atomic<bool> g_running{false};
static std::atomic<bool> g_pendingEnableCT{false};
static std::atomic<bool> g_pendingRestoreCT{false};
static std::atomic<uint64> g_activeServer{0};
static std::atomic<ULONGLONG> g_lastAudioTick{0};
static SOCKET g_socket = INVALID_SOCKET;
static std::thread g_thread;

static CRITICAL_SECTION g_ringLock;
static std::vector<short> g_ring(RING_SAMPLES);
static size_t g_ringRead = 0;
static size_t g_ringWrite = 0;
static size_t g_ringCount = 0;

enum TalkState {
    TALK_INVALID,
    TALK_PTT,
    TALK_PTT_VA,
    TALK_VOICE_ACTIVATION,
    TALK_CONTINUOUS
};
static TalkState g_previousTalkState = TALK_INVALID;
static bool g_ctActive = false;

#pragma pack(push, 1)
struct PacketHeader {
    char magic[4];       // FGT1
    uint8_t type;        // 1 audio, 2 start, 3 stop, 4 ping
    uint32_t sequence;
    uint16_t samples;    // mono int16, 48 kHz
};
#pragma pack(pop)

static void clearRing() {
    EnterCriticalSection(&g_ringLock);
    g_ringRead = g_ringWrite = g_ringCount = 0;
    LeaveCriticalSection(&g_ringLock);
}

static void pushAudio(const short* samples, size_t count) {
    EnterCriticalSection(&g_ringLock);
    for (size_t i = 0; i < count; ++i) {
        if (g_ringCount == RING_SAMPLES) {
            g_ringRead = (g_ringRead + 1) % RING_SAMPLES;
            --g_ringCount;
        }
        g_ring[g_ringWrite] = samples[i];
        g_ringWrite = (g_ringWrite + 1) % RING_SAMPLES;
        ++g_ringCount;
    }
    LeaveCriticalSection(&g_ringLock);
}

static size_t popAudio(short* out, size_t count) {
    size_t done = 0;
    EnterCriticalSection(&g_ringLock);
    while (done < count && g_ringCount > 0) {
        out[done++] = g_ring[g_ringRead];
        g_ringRead = (g_ringRead + 1) % RING_SAMPLES;
        --g_ringCount;
    }
    LeaveCriticalSection(&g_ringLock);
    return done;
}

static size_t ringCount() {
    EnterCriticalSection(&g_ringLock);
    size_t count = g_ringCount;
    LeaveCriticalSection(&g_ringLock);
    return count;
}

static TalkState getTalkState(uint64 server) {
    if (!server) return TALK_INVALID;

    char* vadString = nullptr;
    if (g_ts3.getPreProcessorConfigValue(server, "vad", &vadString) != ERROR_ok)
        return TALK_INVALID;

    bool vad = vadString && std::strcmp(vadString, "true") == 0;
    if (vadString) g_ts3.freeMemory(vadString);

    int inputState = 0;
    if (g_ts3.getClientSelfVariableAsInt(
            server, CLIENT_INPUT_DEACTIVATED, &inputState) != ERROR_ok)
        return TALK_INVALID;

    bool ptt = inputState == INPUT_DEACTIVATED;
    if (ptt) return vad ? TALK_PTT_VA : TALK_PTT;
    return vad ? TALK_VOICE_ACTIVATION : TALK_CONTINUOUS;
}

static bool setTalkState(uint64 server, TalkState state) {
    if (!server || state == TALK_INVALID) return false;

    bool vad = state == TALK_PTT_VA || state == TALK_VOICE_ACTIVATION;
    bool inputActive =
        state == TALK_CONTINUOUS || state == TALK_VOICE_ACTIVATION;

    g_ts3.setPreProcessorConfigValue(server, "vad", vad ? "true" : "false");
    g_ts3.setClientSelfVariableAsInt(
        server, CLIENT_INPUT_DEACTIVATED,
        inputActive ? INPUT_ACTIVE : INPUT_DEACTIVATED);
    g_ts3.flushClientSelfUpdates(server, nullptr);
    return true;
}

static void processTalkState(uint64 server) {
    if (g_pendingEnableCT.exchange(false)) {
        if (!g_ctActive && server) {
            TalkState current = getTalkState(server);
            if (current != TALK_INVALID) {
                g_previousTalkState = current;
                if (current != TALK_CONTINUOUS)
                    setTalkState(server, TALK_CONTINUOUS);
                g_ctActive = true;
            }
        }
    }

    if (g_pendingRestoreCT.exchange(false)) {
        if (g_ctActive && server) {
            if (g_previousTalkState != TALK_INVALID)
                setTalkState(server, g_previousTalkState);
        }
        g_previousTalkState = TALK_INVALID;
        g_ctActive = false;
    }
}

static void receiverLoop() {
    std::vector<char> packet(4096);
    while (g_running.load()) {
        sockaddr_in from{};
        int fromLen = sizeof(from);
        int got = recvfrom(
            g_socket, packet.data(), static_cast<int>(packet.size()), 0,
            reinterpret_cast<sockaddr*>(&from), &fromLen);

        if (got == SOCKET_ERROR) {
            int err = WSAGetLastError();
            if (!g_running.load()) break;
            if (err == WSAETIMEDOUT || err == WSAEWOULDBLOCK) continue;
            Sleep(10);
            continue;
        }

        // Accept localhost traffic only.
        if (ntohl(from.sin_addr.s_addr) != INADDR_LOOPBACK) continue;
        if (got < static_cast<int>(sizeof(PacketHeader))) continue;

        const auto* hdr = reinterpret_cast<const PacketHeader*>(packet.data());
        if (std::memcmp(hdr->magic, "FGT1", 4) != 0) continue;

        if (hdr->type == 1) {
            size_t count = hdr->samples;
            size_t bytesNeeded = sizeof(PacketHeader) + count * sizeof(short);
            if (count == 0 || count > 1920 || bytesNeeded > static_cast<size_t>(got))
                continue;

            const short* pcm = reinterpret_cast<const short*>(
                packet.data() + sizeof(PacketHeader));
            pushAudio(pcm, count);
            g_lastAudioTick.store(GetTickCount64());
            g_pendingEnableCT.store(true);
        } else if (hdr->type == 2) {
            g_pendingEnableCT.store(true);
        } else if (hdr->type == 3) {
            clearRing();
            g_pendingRestoreCT.store(true);
        }
    }
}

const char* ts3plugin_name() { return "FunkGateway Audio Bridge"; }
const char* ts3plugin_version() { return "0.1.0"; }
int ts3plugin_apiVersion() { return PLUGIN_API_VERSION; }
const char* ts3plugin_author() { return "MysticFire01"; }
const char* ts3plugin_description() {
    return "Direkte Audio-Bruecke zwischen FunkGateway und TeamSpeak 3 ohne virtuelles Audiokabel.";
}
void ts3plugin_setFunctionPointers(const TS3Functions funcs) { g_ts3 = funcs; }
int ts3plugin_requestAutoload() { return 1; }

int ts3plugin_init() {
    InitializeCriticalSection(&g_ringLock);

    WSADATA wsa{};
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        return 1;

    g_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (g_socket == INVALID_SOCKET) {
        WSACleanup();
        return 1;
    }

    DWORD timeout = 200;
    setsockopt(
        g_socket, SOL_SOCKET, SO_RCVTIMEO,
        reinterpret_cast<const char*>(&timeout), sizeof(timeout));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(BRIDGE_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (bind(g_socket, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == SOCKET_ERROR) {
        closesocket(g_socket);
        g_socket = INVALID_SOCKET;
        WSACleanup();
        return 1;
    }

    g_running.store(true);
    g_thread = std::thread(receiverLoop);
    return 0;
}

void ts3plugin_shutdown() {
    g_running.store(false);
    if (g_socket != INVALID_SOCKET) {
        closesocket(g_socket);
        g_socket = INVALID_SOCKET;
    }
    if (g_thread.joinable()) g_thread.join();

    uint64 server = g_activeServer.load();
    if (g_ctActive && server && g_previousTalkState != TALK_INVALID)
        setTalkState(server, g_previousTalkState);

    clearRing();
    DeleteCriticalSection(&g_ringLock);
    WSACleanup();
}

void ts3plugin_onConnectStatusChangeEvent(
    uint64 serverConnectionHandlerID, int newStatus, unsigned int) {
    if (newStatus == STATUS_CONNECTION_ESTABLISHED) {
        g_activeServer.store(serverConnectionHandlerID);
    } else if (g_activeServer.load() == serverConnectionHandlerID &&
               newStatus == STATUS_DISCONNECTED) {
        g_pendingRestoreCT.store(true);
        g_activeServer.store(0);
    }
}

void ts3plugin_onEditCapturedVoiceDataEvent(
    uint64 serverConnectionHandlerID, short* samples, int sampleCount,
    int channels, int* edited) {

    if (!samples || sampleCount <= 0 || channels <= 0 || !edited)
        return;

    if (!g_activeServer.load())
        g_activeServer.store(serverConnectionHandlerID);

    processTalkState(serverConnectionHandlerID);

    std::vector<short> mono(static_cast<size_t>(sampleCount));
    size_t got = popAudio(mono.data(), mono.size());

    if (got > 0) {
        for (int frame = 0; frame < sampleCount; ++frame) {
            short injected = frame < static_cast<int>(got) ? mono[frame] : 0;
            for (int ch = 0; ch < channels; ++ch) {
                size_t idx = static_cast<size_t>(frame) * channels + ch;
                int mixed = static_cast<int>(samples[idx]) + static_cast<int>(injected);
                mixed = std::max(-32768, std::min(32767, mixed));
                samples[idx] = static_cast<short>(mixed);
            }
        }
        *edited |= 1;
    }

    ULONGLONG last = g_lastAudioTick.load();
    if (g_ctActive && ringCount() == 0 && last &&
        GetTickCount64() - last > 350) {
        g_pendingRestoreCT.store(true);
        processTalkState(serverConnectionHandlerID);
    }
}
